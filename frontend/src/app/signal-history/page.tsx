'use client';

import React, { useEffect, useState } from 'react';
import {
  History, CheckCircle, XCircle, Trophy, TrendingDown, TrendingUp,
  Target, Percent, Filter, Inbox, LineChart,
} from 'lucide-react';
import {
  ResponsiveContainer, PieChart, Pie, Cell, Tooltip, Legend,
  BarChart, Bar, XAxis, YAxis, AreaChart, Area,
} from 'recharts';
import { GlassCard } from '@/components/ui/GlassCard';
import { InvestmentDisclaimer } from '@/components/legal/InvestmentDisclaimer';
import { ClosedSignalChartModal } from '@/components/ui/ClosedSignalChartModal';
import { cn, formatAbsoluteTimeTR } from '@/lib/utils';
import {
  fetchSignalHistory, fetchSignalHistoryStats,
  type ApiSignal, type SignalHistoryStats, type SignalHistoryFilters,
} from '@/lib/api';

// ─── Helpers ─────────────────────────────────────────────────────────────────

function qualityScore(confidence: number): number {
  return Math.round(confidence / 10);
}

const OUTCOME_LABEL: Record<string, string> = {
  win: 'TP — Kazandı',
  loss: 'Stop Oldu',
  breakeven: 'Başabaş',
  expired: 'Süresi Doldu (48sa)',
  invalidated: 'İptal Edildi (Tersine Sinyal)',
  active: 'Hâlâ Aktif',
};

const OUTCOME_COLOR: Record<string, string> = {
  win: 'text-bullish bg-bullish/10 border-bullish/20',
  loss: 'text-bearish bg-bearish/10 border-bearish/20',
  breakeven: 'text-yellow-400 bg-yellow-400/10 border-yellow-400/20',
  expired: 'text-text-muted bg-bg-tertiary border-border-subtle',
  invalidated: 'text-orange-400 bg-orange-400/10 border-orange-400/20',
  active: 'text-accent-primary bg-accent-primary/10 border-accent-primary/20',
};

function outcomeDetail(s: ApiSignal): string {
  if (s.outcome === 'win') {
    if (s.hit_tp3) return 'TP3 Vuruldu';
    if (s.hit_tp2) return 'TP2 Vuruldu';
    if (s.hit_tp1) return 'TP1 Vuruldu';
    return 'TP — Kazandı';
  }
  return OUTCOME_LABEL[s.outcome ?? 'active'] ?? s.outcome ?? '-';
}

// A signal can partially close at TP1/TP2 (engine takes 50%/30% of the
// position off the table at each level — see backend tracker.py) and *then*
// have the remainder cut short by a reversal/SL/expiry. Showing only the
// final outcome ("İptal Edildi") hid the fact that some profit had already
// been locked in before that — this surfaces the partial fill as its own
// line above the final outcome.
function partialFillDetail(s: ApiSignal): string | null {
  if (s.outcome === 'win' || s.outcome === 'active') return null; // already fully reflected above, or nothing closed yet
  if (s.hit_tp2) return 'TP1+TP2 alındı (%80)';
  if (s.hit_tp1) return 'TP1 alındı (%50)';
  return null;
}

function formatDuration(ms: number): string {
  if (ms <= 0) return '-';
  const minutes = ms / 60000;
  if (minutes < 60) return `${Math.round(minutes)} dk`;
  const hours = ms / 3600000;
  if (hours < 24) return `${hours.toFixed(1)} saat`;
  return `${(hours / 24).toFixed(1)} gün`;
}

function timeToOutcome(s: ApiSignal): string {
  if (!s.closed_at) return '-';
  const ms = new Date(s.closed_at).getTime() - new Date(s.generated_at).getTime();
  return formatDuration(ms);
}

/** Per-target "sinyal verildikten kaç dakika/saat sonra TP geldi" breakdown.
 * Distinct from timeToOutcome() — closed_at marks full resolution, which for
 * a scaled exit (TP1 hit, then rides to TP2/TP3/SL) lands well after TP1
 * actually triggered. Each tpN_hit_at is the real moment that target crossed. */
function tpTimings(s: ApiSignal): { label: string; ms: number }[] {
  const gen = new Date(s.generated_at).getTime();
  const out: { label: string; ms: number }[] = [];
  if (s.tp1_hit_at) out.push({ label: 'TP1', ms: new Date(s.tp1_hit_at).getTime() - gen });
  if (s.tp2_hit_at) out.push({ label: 'TP2', ms: new Date(s.tp2_hit_at).getTime() - gen });
  if (s.tp3_hit_at) out.push({ label: 'TP3', ms: new Date(s.tp3_hit_at).getTime() - gen });
  return out;
}

const TIME_PERIODS = [
  { id: 'all', label: 'Tümü', days: null },
  { id: '7d', label: '7 Gün', days: 7 },
  { id: '30d', label: '30 Gün', days: 30 },
  { id: '90d', label: '90 Gün', days: 90 },
] as const;

const PIE_COLORS = { win: '#10B981', loss: '#EF4444', breakeven: '#F59E0B', expired: '#64748b', invalidated: '#A78BFA' };

export default function SignalHistoryPage() {
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<SignalHistoryStats | null>(null);
  const [signals, setSignals] = useState<ApiSignal[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 25;
  const [chartSignal, setChartSignal] = useState<ApiSignal | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  // Filters
  const [market, setMarket] = useState<'all' | 'crypto' | 'stock'>('all');
  const [outcome, setOutcome] = useState<'all' | 'win' | 'loss' | 'breakeven' | 'expired' | 'invalidated'>('all');
  const [signalType, setSignalType] = useState<'all' | string>('all');
  const [period, setPeriod] = useState<typeof TIME_PERIODS[number]['id']>('all');
  const [minConfidence, setMinConfidence] = useState(0);

  const dateFrom = (() => {
    const p = TIME_PERIODS.find((t) => t.id === period);
    if (!p?.days) return undefined;
    const d = new Date();
    d.setDate(d.getDate() - p.days);
    return d.toISOString();
  })();

  useEffect(() => {
    // Guards against React's dev-mode double-effect-invoke (and any other
    // overlapping request): without this, an earlier in-flight request that
    // resolves AFTER a newer one can overwrite good data with a stale/empty
    // result — exactly what caused data to flash and then disappear.
    let cancelled = false;

    const load = async () => {
      setLoading(true);
      setLoadError(null);
      try {
        const filters: SignalHistoryFilters = {
          only_resolved: true,
          page,
          page_size: pageSize,
          min_confidence: minConfidence > 0 ? minConfidence : undefined,
          date_from: dateFrom,
        };
        if (market !== 'all') filters.market = market;
        if (outcome !== 'all') filters.outcome = outcome;
        if (signalType !== 'all') filters.signal_type = signalType;

        const [histRes, statsRes] = await Promise.all([
          fetchSignalHistory(filters),
          fetchSignalHistoryStats({
            market: market !== 'all' ? market : undefined,
            date_from: dateFrom,
          }),
        ]);
        if (cancelled) return;
        setSignals(histRes.items);
        setTotal(histRes.total);
        setStats(statsRes);
      } catch (e: any) {
        if (cancelled) return;
        // Previously swallowed silently — a slow/timed-out request looked
        // identical to "genuinely zero signals", which is exactly what made
        // a real backend hiccup undiagnosable from the UI alone.
        setLoadError(e?.message ?? 'Sinyal geçmişi yüklenemedi.');
        setSignals([]);
        setTotal(0);
        setStats(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    load();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [market, outcome, signalType, period, minConfidence, page, reloadKey]);

  const pieData = stats
    ? [
        { name: 'TP — Kazandı', value: stats.win_count, key: 'win' },
        { name: 'Stop Oldu', value: stats.loss_count, key: 'loss' },
        { name: 'Başabaş', value: stats.breakeven_count, key: 'breakeven' },
        { name: 'Süresi Doldu', value: stats.expired_count, key: 'expired' },
        { name: 'İptal Edildi', value: stats.invalidated_count, key: 'invalidated' },
      ].filter((d) => d.value > 0)
    : [];

  const tpVsSlData = stats
    ? [
        { name: 'TP Vuran', value: stats.win_count, fill: '#10B981' },
        { name: 'SL Olan', value: stats.loss_count, fill: '#EF4444' },
        { name: 'Başabaş', value: stats.breakeven_count, fill: '#F59E0B' },
        { name: 'Süresi Dolan', value: stats.expired_count, fill: '#64748b' },
        { name: 'İptal Edilen', value: stats.invalidated_count, fill: '#FB923C' },
      ]
    : [];

  // Equity curve built from closed signals in current filtered view (chronological)
  const equityCurve = (() => {
    const closed = signals
      .filter((s) => s.actual_return !== null && s.actual_return !== undefined && s.closed_at)
      .slice()
      .sort((a, b) => new Date(a.closed_at!).getTime() - new Date(b.closed_at!).getTime());
    let capital = 10000;
    const points = [{ time: 'Başlangıç', capital }];
    for (const s of closed) {
      capital += capital * 0.1 * ((s.actual_return ?? 0) / 100);
      points.push({ time: formatAbsoluteTimeTR(s.closed_at!, false), capital: Math.round(capital) });
    }
    return points;
  })();

  const hasAnyHistory = total > 0 || (stats?.total_signals ?? 0) > 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight text-text-primary flex items-center gap-2">
          <History className="w-6 h-6 text-accent-primary" /> Sinyal Geçmişi
        </h1>
        <p className="text-sm text-text-secondary">
          Geçmişte verilen sinyallerin TP / Stop Loss / Başabaş sonuçları — platform performansını burada değerlendirebilirsiniz
        </p>
      </div>

      {/* Prensip 4: geçmiş/simüle performans yüzeyi — belirgin uyarı (tek kaynak) */}
      <InvestmentDisclaimer variant="backtest" />

      {loading ? (
        <div className="flex flex-col items-center justify-center p-20 space-y-4">
          <div className="w-10 h-10 border-4 border-accent-primary border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-text-secondary">Yükleniyor...</p>
        </div>
      ) : loadError ? (
        <GlassCard className="flex flex-col items-center justify-center p-20 text-center">
          <XCircle className="w-14 h-14 text-bearish mb-4" />
          <h3 className="text-base font-bold text-text-secondary mb-1">Sinyal geçmişi yüklenemedi</h3>
          <p className="text-sm text-text-muted max-w-md mb-4">{loadError}</p>
          <button
            onClick={() => setReloadKey((k) => k + 1)}
            className="px-4 py-2 text-xs font-bold rounded-lg bg-accent-primary/15 text-accent-primary border border-accent-primary/30 hover:bg-accent-primary/25"
          >
            Tekrar Dene
          </button>
        </GlassCard>
      ) : !hasAnyHistory ? (
        <GlassCard className="flex flex-col items-center justify-center p-20 text-center">
          <Inbox className="w-14 h-14 text-border-medium mb-4" />
          <h3 className="text-base font-bold text-text-secondary mb-1">Henüz tamamlanmış sinyal yok</h3>
          <p className="text-sm text-text-muted max-w-md">
            Sinyaller TP, SL, başabaş veya süre dolumuyla kapandığında burada görünecek.
          </p>
        </GlassCard>
      ) : (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
            <GlassCard className="p-4">
              <span className="text-[10px] font-bold text-text-muted uppercase">Toplam Kapanan Sinyal</span>
              <div className="text-2xl font-extrabold font-mono mt-1 text-text-primary">{stats?.closed_count ?? 0}</div>
            </GlassCard>
            <GlassCard className="p-4">
              <span className="text-[10px] font-bold text-text-muted uppercase">Başarı Oranı</span>
              <div className="text-2xl font-extrabold font-mono mt-1 text-bullish">{stats?.win_rate ?? 0}%</div>
            </GlassCard>
            <GlassCard className="p-4">
              <span className="text-[10px] font-bold text-text-muted uppercase">TP Vuruş Oranı</span>
              <div className="text-2xl font-extrabold font-mono mt-1 text-bullish">{stats?.tp_hit_rate ?? 0}%</div>
            </GlassCard>
            <GlassCard className="p-4">
              <span className="text-[10px] font-bold text-text-muted uppercase">Stop Oranı</span>
              <div className="text-2xl font-extrabold font-mono mt-1 text-bearish">{stats?.sl_rate ?? 0}%</div>
            </GlassCard>
            <GlassCard className="p-4">
              <span className="text-[10px] font-bold text-text-muted uppercase">Ort. Getiri</span>
              <div className={cn('text-2xl font-extrabold font-mono mt-1', (stats?.average_return ?? 0) >= 0 ? 'text-bullish' : 'text-bearish')}>
                {stats?.average_return != null ? `${stats.average_return > 0 ? '+' : ''}${stats.average_return}%` : '-'}
              </div>
            </GlassCard>
            <GlassCard className="p-4">
              <span className="text-[10px] font-bold text-text-muted uppercase">Kâr Faktörü</span>
              <div className="text-2xl font-extrabold font-mono mt-1 text-accent-primary">{stats?.profit_factor ?? '-'}</div>
            </GlassCard>
            <GlassCard className="p-4">
              <span className="text-[10px] font-bold text-text-muted uppercase">En İyi / En Kötü</span>
              <div className="mt-1 space-y-0.5">
                <div className="text-xs font-bold text-bullish font-mono">
                  {stats?.best_signal ? `${stats.best_signal.symbol} +${stats.best_signal.return}%` : '-'}
                </div>
                <div className="text-xs font-bold text-bearish font-mono">
                  {stats?.worst_signal ? `${stats.worst_signal.symbol} ${stats.worst_signal.return}%` : '-'}
                </div>
              </div>
            </GlassCard>
          </div>

          {/* Filters */}
          <GlassCard className="p-4 flex flex-wrap items-center gap-3">
            <span className="flex items-center gap-1.5 text-xs font-bold text-text-muted uppercase">
              <Filter className="w-3.5 h-3.5" /> Filtreler
            </span>

            <select value={market} onChange={(e) => { setMarket(e.target.value as any); setPage(1); }}
              className="bg-bg-secondary border border-border-subtle rounded-lg px-3 py-1.5 text-xs text-text-primary">
              <option value="all">Tüm Piyasalar</option>
              <option value="crypto">Kripto</option>
              <option value="stock">BIST</option>
            </select>

            <select value={outcome} onChange={(e) => { setOutcome(e.target.value as any); setPage(1); }}
              className="bg-bg-secondary border border-border-subtle rounded-lg px-3 py-1.5 text-xs text-text-primary">
              <option value="all">Tüm Sonuçlar</option>
              <option value="win">TP — Kazandı</option>
              <option value="loss">Stop Oldu</option>
              <option value="breakeven">Başabaş</option>
              <option value="expired">Süresi Doldu (48sa)</option>
              <option value="invalidated">İptal Edildi (Tersine Sinyal)</option>
            </select>

            <select value={signalType} onChange={(e) => { setSignalType(e.target.value); setPage(1); }}
              className="bg-bg-secondary border border-border-subtle rounded-lg px-3 py-1.5 text-xs text-text-primary">
              <option value="all">Tüm Sinyal Tipleri</option>
              <option value="strong_buy">Strong Buy</option>
              <option value="buy">Buy</option>
              <option value="sell">Sell</option>
              <option value="strong_sell">Strong Sell</option>
            </select>

            <div className="flex bg-bg-secondary border border-border-subtle rounded-lg p-0.5">
              {TIME_PERIODS.map((p) => (
                <button key={p.id} onClick={() => { setPeriod(p.id); setPage(1); }}
                  className={cn('px-3 py-1 text-xs font-semibold rounded-md transition-all',
                    period === p.id ? 'bg-bg-tertiary text-text-primary' : 'text-text-muted hover:text-text-primary')}>
                  {p.label}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-2 ml-auto">
              <span className="text-[10px] text-text-muted font-bold uppercase">Min. Güven</span>
              <input type="range" min={0} max={100} step={5} value={minConfidence}
                onChange={(e) => { setMinConfidence(Number(e.target.value)); setPage(1); }}
                className="w-24 accent-accent-primary cursor-pointer" />
              <span className="text-xs font-bold font-mono min-w-[36px] text-center text-text-primary">{minConfidence}%</span>
            </div>
          </GlassCard>

          {/* Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <GlassCard className="p-5">
              <h3 className="text-sm font-bold text-text-primary mb-3">Kazanç / Kayıp Dağılımı</h3>
              <div className="h-56 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={pieData} dataKey="value" nameKey="name" innerRadius={45} outerRadius={75} paddingAngle={2}>
                      {pieData.map((d) => (
                        <Cell key={d.key} fill={(PIE_COLORS as any)[d.key]} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={{ backgroundColor: '#071126', borderColor: 'rgba(148,163,184,0.1)', borderRadius: 8 }} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </GlassCard>

            <GlassCard className="p-5">
              <h3 className="text-sm font-bold text-text-primary mb-3">TP vs SL Dağılımı</h3>
              <div className="h-56 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={tpVsSlData}>
                    <XAxis dataKey="name" stroke="#64748b" fontSize={10} tickLine={false} />
                    <YAxis stroke="#64748b" fontSize={10} tickLine={false} allowDecimals={false} />
                    <Tooltip contentStyle={{ backgroundColor: '#071126', borderColor: 'rgba(148,163,184,0.1)', borderRadius: 8 }} />
                    <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                      {tpVsSlData.map((d, i) => <Cell key={i} fill={d.fill} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </GlassCard>

            <GlassCard className="p-5">
              <h3 className="text-sm font-bold text-text-primary mb-3">Sermaye Eğrisi (Bu Görünüm)</h3>
              <div className="h-56 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={equityCurve} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                    <defs>
                      <linearGradient id="colorHistEquity" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.4} />
                        <stop offset="95%" stopColor="#3B82F6" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <XAxis dataKey="time" stroke="#64748b" fontSize={9} tickLine={false} />
                    <YAxis stroke="#64748b" fontSize={10} tickLine={false} domain={['dataMin - 200', 'dataMax + 200']} />
                    <Tooltip contentStyle={{ backgroundColor: '#071126', borderColor: 'rgba(148,163,184,0.1)', borderRadius: 8 }} />
                    <Area type="monotone" dataKey="capital" stroke="#3B82F6" strokeWidth={2} fillOpacity={1} fill="url(#colorHistEquity)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </GlassCard>
          </div>

          {/* Closed signals table */}
          <GlassCard className="p-0 overflow-hidden">
            <div className="px-5 py-3 border-b border-border-subtle bg-bg-secondary/30">
              <h3 className="text-sm font-bold text-text-primary">Kapanan Sinyaller ({total})</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-border-subtle text-text-muted uppercase">
                    <th className="py-2.5 px-4">Sembol</th>
                    <th className="py-2.5 px-3">Tip</th>
                    <th className="py-2.5 px-3">Yön</th>
                    <th className="py-2.5 px-3">Üretim Zamanı</th>
                    <th className="py-2.5 px-3">Kapanma Zamanı</th>
                    <th className="py-2.5 px-3 text-right">Giriş</th>
                    <th className="py-2.5 px-3 text-right">SL</th>
                    <th className="py-2.5 px-3 text-right">TP1/TP2/TP3</th>
                    <th className="py-2.5 px-3">Sonuç</th>
                    <th className="py-2.5 px-3 text-right">P/L %</th>
                    <th className="py-2.5 px-3 text-right">Güven</th>
                    <th className="py-2.5 px-3 text-right">Risk</th>
                    <th className="py-2.5 px-3 text-right">Süre</th>
                    <th className="py-2.5 px-3 text-center">Grafik</th>
                  </tr>
                </thead>
                <tbody>
                  {signals.map((s) => (
                    <tr key={s.id} className="border-b border-border-subtle/60 last:border-none hover:bg-bg-secondary/30 transition-colors">
                      <td className="py-2.5 px-4 font-bold text-text-primary">{s.asset?.symbol}</td>
                      <td className="py-2.5 px-3 font-semibold uppercase text-text-secondary">{s.signal_type.replace('_', ' ')}</td>
                      <td className="py-2.5 px-3">
                        <span className={cn('font-semibold', s.direction === 'bullish' ? 'text-bullish' : 'text-bearish')}>
                          {s.direction === 'bullish' ? 'LONG' : s.direction === 'bearish' ? 'SHORT' : 'NEUTRAL'}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 font-mono text-text-muted">{formatAbsoluteTimeTR(s.generated_at)}</td>
                      <td className="py-2.5 px-3 font-mono text-text-muted">{s.closed_at ? formatAbsoluteTimeTR(s.closed_at) : '-'}</td>
                      <td className="py-2.5 px-3 text-right font-mono text-text-primary">{s.entry_zone_low?.toFixed?.(4) ?? s.entry_zone_low}</td>
                      <td className="py-2.5 px-3 text-right font-mono text-bearish">{s.stop_loss}</td>
                      <td className="py-2.5 px-3 text-right font-mono text-text-muted">
                        {s.tp1} / {s.tp2} / {s.tp3}
                      </td>
                      <td className="py-2.5 px-3">
                        <div className="flex flex-col gap-1 items-start">
                          {partialFillDetail(s) && (
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold border text-bullish bg-bullish/10 border-bullish/20">
                              {partialFillDetail(s)}
                            </span>
                          )}
                          <span className={cn('px-2 py-0.5 rounded text-[10px] font-bold border', OUTCOME_COLOR[s.outcome ?? 'active'])}>
                            {partialFillDetail(s) ? `Kalan: ${outcomeDetail(s)}` : outcomeDetail(s)}
                          </span>
                        </div>
                      </td>
                      <td className={cn('py-2.5 px-3 text-right font-bold font-mono',
                        (s.actual_return ?? 0) > 0 ? 'text-bullish' : (s.actual_return ?? 0) < 0 ? 'text-bearish' : 'text-text-muted')}>
                        {s.actual_return != null ? `${s.actual_return > 0 ? '+' : ''}${s.actual_return.toFixed(2)}%` : '-'}
                      </td>
                      <td className="py-2.5 px-3 text-right font-mono text-text-primary">{qualityScore(s.confidence_score)}/10</td>
                      <td className="py-2.5 px-3 text-right uppercase text-text-muted">{s.risk_level}</td>
                      <td className="py-2.5 px-3 text-right font-mono text-text-muted min-w-[110px]">
                        <div>{timeToOutcome(s)}</div>
                        {tpTimings(s).length > 0 && (
                          <div className="flex flex-col items-end text-[10px] text-bullish/80 normal-case font-sans leading-tight mt-0.5">
                            {tpTimings(s).map((t) => (
                              <span key={t.label} className="whitespace-nowrap">{t.label}: {formatDuration(t.ms)}</span>
                            ))}
                          </div>
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-center">
                        <button
                          onClick={() => setChartSignal(s)}
                          title="Kapanma anındaki grafiği gör"
                          className="p-1.5 rounded-lg text-text-muted hover:text-accent-primary hover:bg-accent-primary/10 transition-colors"
                        >
                          <LineChart className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between px-4 py-3 border-t border-border-subtle text-xs text-text-muted">
                <span>Sayfa {page} / {totalPages}</span>
                <div className="flex gap-2">
                  <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}
                    className="px-3 py-1.5 rounded-lg border border-border-subtle disabled:opacity-40 hover:border-accent-primary/40">Önceki</button>
                  <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}
                    className="px-3 py-1.5 rounded-lg border border-border-subtle disabled:opacity-40 hover:border-accent-primary/40">Sonraki</button>
                </div>
              </div>
            )}
          </GlassCard>
        </>
      )}
      {chartSignal && (
        <ClosedSignalChartModal signal={chartSignal} onClose={() => setChartSignal(null)} />
      )}
    </div>
  );
}
