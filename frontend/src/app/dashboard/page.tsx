'use client';

import React, { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  Zap, AlertTriangle,
  ArrowRight, RefreshCw,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { SignalTable, DensityToggle, type Density } from '@/components/signals/SignalTable';
import {
  fetchActiveSignals, fetchPerformanceSummary, fetchSignalHistoryStats,
  fetchGlobalMarket, fetchFearGreed,
  type ApiSignal, type PerformanceSummary, type SignalHistoryStats,
  type GlobalMarketData, type FearGreedData,
} from '@/lib/api';
import { ACTIVE_SIGNAL_PARAMS } from '@/lib/active-signal';
import { formatLargeNumber, formatPercentage, cn } from '@/lib/utils';
import { PAYMENTS_ENABLED } from '@/lib/config';
import { InvestmentDisclaimer } from '@/components/legal/InvestmentDisclaimer';
import { useLivePrices } from '@/hooks/useLivePrices';
import { useTierLimits } from '@/hooks/useTierLimits';
import { useAuth } from '@/lib/auth-context';
import { EmptyState } from '@/components/ui/EmptyState';
import OnboardingChecklist from '@/components/dashboard/OnboardingChecklist';
import CoachmarkTour from '@/components/dashboard/CoachmarkTour';
import { DurumBandi } from '@/components/dashboard/DurumBandi';
import { LifecycleHealth } from '@/components/dashboard/LifecycleHealth';
import { Sicil } from '@/components/dashboard/Sicil';
import { Crown, Lock } from 'lucide-react';
import { chartColor } from '@/lib/chartColors';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fngLabel(v: number): string {
  if (v >= 75) return 'AŞIRI AÇGÖZLÜLÜK';
  if (v >= 55) return 'AÇGÖZLÜLÜK (GREED)';
  if (v >= 45) return 'NÖTR';
  if (v >= 25) return 'KORKU (FEAR)';
  return 'AŞIRI KORKU';
}

// Owned semantik (P9.7): greed=bull · nötr/korku=amber · aşırı-korku=bear;
// extreme/greed ayrımı label'da (tek owned-hex; #34D399/#F59E0B/#EF4444 emekli).
function fngColor(v: number): string {
  if (v >= 75) return chartColor('bull');
  if (v >= 55) return chartColor('bull');
  if (v >= 45) return chartColor('amber');
  if (v >= 25) return chartColor('amber');
  return chartColor('bear');
}

function LiveClock() {
  const [time, setTime] = useState('');
  useEffect(() => {
    const update = () => {
      const now = new Date();
      setTime(now.toLocaleString('tr-TR', {
        timeZone: 'Europe/Istanbul',
        day: '2-digit', month: 'long', year: 'numeric',
        hour: '2-digit', minute: '2-digit', second: '2-digit',
      }));
    };
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, []);
  return <span className="text-sm text-text-muted font-mono">{time}</span>;
}

// ---------------------------------------------------------------------------
// Main Dashboard
// ---------------------------------------------------------------------------

export default function DashboardPage() {
  const [timeRange, setTimeRange] = useState<'24s' | '7g' | '30g'>('24s');
  const [density, setDensity] = useState<Density>('compact');
  const router = useRouter();

  const [signals, setSignals] = useState<ApiSignal[]>([]);
  const [perf, setPerf] = useState<PerformanceSummary | null>(null);
  const [global, setGlobal] = useState<GlobalMarketData | null>(null);
  const [fng, setFng] = useState<FearGreedData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  // CoinGecko's free API rate-limits (503) under repeated calls — when that
  // happens we keep showing the last successfully fetched values (if any)
  // instead of wiping them, and surface a clear message instead of leaving
  // the cards stuck on "—" / "Yükleniyor..." forever with no explanation.
  const [globalError, setGlobalError] = useState(false);
  // Core platform data (signals + performance) unreachable — surface an honest
  // error + retry instead of rendering misleading zeros as if they were real.
  const [dataError, setDataError] = useState(false);
  // CP-7 tek sayı sözlüğü (lib/active-signal.ts): sayaç, tablo, lifecycle-census
  // ve AI-Görüşü/Risk agregaları AYNI actionable fetch'inden beslenir —
  // kart-tablo-sayaç aynı sayıyı söyler; Sinyal Merkezi default'uyla birebir
  // (süperset kuralı). perf.active_count HOLD içerir → kullanıcı-yüzeyinde yok.
  const [actionableActiveCount, setActionableActiveCount] = useState(0);
  // Closed trades within the selected 24s/7g/30g window — replaces the old
  // "Toplam Sinyal" (all-time, ignored the period selector entirely).
  const [periodStats, setPeriodStats] = useState<SignalHistoryStats | null>(null);

  const signalSymbols = [...new Set(signals.map((s) => s.asset?.symbol ?? '').filter(Boolean))];
  const livePrices = useLivePrices(signalSymbols);
  const limits = useTierLimits();
  const isFreeTier = !limits.loading && limits.tier === 'free';
  const { user } = useAuth();
  const firstName = user?.full_name?.trim().split(/\s+/)[0] ?? '';

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);

    const periodHours = timeRange === '24s' ? 24 : timeRange === '7g' ? 24 * 7 : 24 * 30;
    const dateFrom = new Date(Date.now() - periodHours * 3600_000).toISOString();

    const [signalsRes, perfRes, periodRes, globalRes, fngRes] = await Promise.allSettled([
      fetchActiveSignals({ ...ACTIVE_SIGNAL_PARAMS, page_size: 100 }),
      fetchPerformanceSummary(),
      fetchSignalHistoryStats({ date_from: dateFrom }),
      fetchGlobalMarket(),
      fetchFearGreed(),
    ]);

    // Tek response = tek evren: satırlar (items) + sayaç (total) aynı fetch'ten.
    if (signalsRes.status === 'fulfilled') {
      setSignals(signalsRes.value.items);
      setActionableActiveCount(signalsRes.value.total);
    }
    if (perfRes.status === 'fulfilled') setPerf(perfRes.value);
    if (periodRes.status === 'fulfilled') setPeriodStats(periodRes.value);
    if (globalRes.status === 'fulfilled') {
      const g = globalRes.value;
      setGlobal(g);
      setGlobalError(false);
    } else {
      setGlobalError(true);
    }
    if (fngRes.status === 'fulfilled') setFng(fngRes.value);

    // Both core platform fetches failing = backend unreachable, not "0 signals".
    setDataError(signalsRes.status === 'rejected' && perfRes.status === 'rejected');

    setLoading(false);
    setRefreshing(false);
  }, [timeRange]);

  useEffect(() => {
    load();
    // Signal counts churn continuously in the background (scheduler regen +
    // live TP/SL/reversal resolution every few minutes) — without this the
    // stat cards go stale within minutes of opening the page.
    const id = setInterval(() => load(true), 30_000);
    return () => clearInterval(id);
  }, [load]);

  useEffect(() => {
    const saved = window.localStorage.getItem('tm.dashboard.density');
    if (saved === 'compact' || saved === 'comfortable') setDensity(saved);
  }, []);

  const changeDensity = (d: Density) => {
    setDensity(d);
    try { window.localStorage.setItem('tm.dashboard.density', d); } catch {}
  };

  // CP-DASH-C2: Dashboard = executive overview → sinyal detayı inline AÇILMAZ
  // (sorumluluk-sınırı: derin analiz Signal Center/Symbol'ün). Satır seçimi ilgili
  // sembol analiz sayfasına yönlendirir; symbol/tf eksikse sessiz kırılma yerine
  // /signals fallback.
  const handleSignalSelect = (sig: ApiSignal) => {
    const symbol = sig.asset?.symbol;
    if (!symbol) { router.push('/signals'); return; }
    const tf = sig.timeframe ? `?tf=${encodeURIComponent(sig.timeframe)}` : '';
    router.push(`/markets/${encodeURIComponent(symbol)}${tf}`);
  };

  // Derived stats
  const activeCount = actionableActiveCount;
  const winRate = perf?.win_rate ?? 0;
  const avgReturn = perf?.average_return ?? 0;
  const fngValue = fng?.value ?? 50;
  const periodPhrase = timeRange === '24s' ? '24 saatte' : timeRange === '7g' ? '7 günde' : '30 günde';
  const periodClosedCount = periodStats?.closed_count ?? 0;
  const periodLabel = timeRange === '24s' ? 'son 24 saat' : timeRange === '7g' ? 'son 7 gün' : 'son 30 gün';
  // Lifecycle-health census over ALL active signals (not just the recent 6) —
  // client-derived from the already-fetched list, no endpoint.
  const lifecycleCounts = signals.reduce<Record<string, number>>((acc, s) => {
    if (s.live_status) acc[s.live_status] = (acc[s.live_status] ?? 0) + 1;
    return acc;
  }, {});
  // AI Görüşü + Risk Dağılımı aggregates — client-derived from active signals.
  const longCount = signals.filter((s) => String(s.direction ?? '').toLowerCase().includes('bull')).length;
  const shortCount = signals.filter((s) => String(s.direction ?? '').toLowerCase().includes('bear')).length;
  const avgConfidence = signals.length
    ? Math.round(signals.reduce((a, s) => a + (s.confidence_score || 0), 0) / signals.length)
    : 0;
  // Real compounded total return from the backend's resolved-trade equity
  // curve (10000 starting capital), instead of avgReturn * totalSignals —
  // that multiplication produces a meaningless number once totalSignals is
  // in the thousands (e.g. "+12214%").
  const equityCurve = perf?.historical_equity_curve ?? [];
  const totalReturnPct = equityCurve.length > 1
    ? ((equityCurve[equityCurve.length - 1].capital - equityCurve[0].capital) / equityCurve[0].capital) * 100
    : 0;

  // CP-DASH-B: Dönem Net Getiri (Seçenek B) — equity-curve'ü seçili dönem/dateFrom
  // penceresiyle dilimle → gerçek dönem bileşik net getiri. Anchor = pencere
  // başındaki (windowStart'a ≤ son) sermaye; kapanışsız dönemde end==anchor →
  // dürüst %0 (veri uydurma YOK; avgReturn×count anlamsız-çarpımı KULLANILMAZ).
  // totalReturnPct (tüm-zaman) yalnız Sicil'de; hero dönem-bazlıdır.
  const periodHoursB = timeRange === '24s' ? 24 : timeRange === '7g' ? 24 * 7 : 24 * 30;
  const windowStartMs = Date.now() - periodHoursB * 3600_000;
  const periodReturnPct = (() => {
    if (equityCurve.length < 1) return 0;
    const t = (p: { time: string }) => new Date(p.time).getTime();
    let anchor = equityCurve[0].capital;
    for (const p of equityCurve) { if (t(p) <= windowStartMs) anchor = p.capital; else break; }
    const end = equityCurve[equityCurve.length - 1].capital;
    return anchor > 0 ? ((end - anchor) / anchor) * 100 : 0;
  })();
  const periodWinRate = periodStats?.win_rate ?? 0;

  return (
    <div className="space-y-5">
      {/* First-run onboarding checklist + welcome tour (frontend-only, localStorage) */}
      <OnboardingChecklist />
      <CoachmarkTour />

      {/* Free tier banner — hidden in beta while the payment funnel is disabled */}
      {isFreeTier && PAYMENTS_ENABLED && (
        <Link
          href="/pricing"
          className="block bg-gradient-to-r from-amber/15 via-accent-primary/15 to-amber/15 border border-amber/30 rounded-2xl p-4 hover:border-amber/50 transition-all"
        >
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-amber/20 flex items-center justify-center flex-shrink-0">
                <Lock className="w-5 h-5 text-amber" />
              </div>
              <div>
                <p className="text-sm font-display text-text-primary">
                  Ücretsiz plandasın — günde {limits.daily_signal_limit} sinyal görüntülüyorsun.
                </p>
                <p className="text-micro text-text-secondary mt-0.5">
                  Sınırsız sinyal, Telegram bildirimleri, backtest ve daha fazlası için Pro plana yükselt.
                </p>
              </div>
            </div>
            <span className="flex items-center gap-1.5 text-xs font-display text-amber whitespace-nowrap bg-amber/10 border border-amber/30 px-3 py-1.5 rounded-xl">
              <Crown className="w-3.5 h-3.5" /> Yükselt
            </span>
          </div>
        </Link>
      )}

      {/* ── Title Row ── */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-3">
        <div>
          <h1 className="text-h2 font-display text-text-primary">
            {firstName ? `Hoş geldin, ${firstName}` : 'Gösterge Paneli'}
          </h1>
          <p className="text-sm text-text-secondary mt-0.5">Piyasaları yapay zekâ ile analiz edin, avantaj yakalayın.</p>
        </div>
        <div className="flex items-center gap-3">
          <LiveClock />
          <div className="flex bg-bg-secondary border border-border-subtle p-0.5 rounded-lg">
            {(['24s', '7g', '30g'] as const).map((r) => (
              <button
                key={r}
                onClick={() => setTimeRange(r)}
                className={`px-3 py-1 text-xs font-display rounded-md transition-all ${
                  timeRange === r ? 'bg-bg-tertiary text-text-primary' : 'text-text-muted hover:text-text-primary'
                }`}
              >
                {r === '24s' ? '24 Saat' : r === '7g' ? '7 Gün' : '30 Gün'}
              </button>
            ))}
          </div>
          <button
            onClick={() => load(true)}
            disabled={refreshing}
            className="p-2 rounded-lg bg-bg-secondary border border-border-subtle text-text-muted hover:text-text-primary transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <InvestmentDisclaimer variant="inline" />

      {/* ── Durum Bandı — 3-saniye "Şu an" özeti (DE-1, additif, mevcut veriden) ── */}
      <DurumBandi
        periodPhrase={periodPhrase}
        closedCount={periodClosedCount}
        winRate={winRate}
        avgReturn={avgReturn}
        activeCount={activeCount}
        longCount={longCount}
        shortCount={shortCount}
        avgConfidence={avgConfidence}
        loading={loading}
        hasData={!!perf && !dataError}
      />

      {/* ── Kahraman metrik + 3 ikincil (CP-DASH-B · §03 dash-widget-taşıma-kilidi:
          "5 eşit stat-kart → 1 kahraman [Dönem Net Getiri + makbuz] + 3 ikincil
          [Aktif · Kapanan · Win-Rate]"). Fear&Greed stat-kartı KALKTI → kompakt
          Piyasa Bağlamı satırına indi (gauge SVG yok). Ortalama Getiri kartı KALKTI
          (avgReturn DurumBandı'nda kalır). Vurgu-bütçesi ≤2: tek parlak kahraman-
          rakam; 3 ikincil sessiz. İkon/gauge/pie/svg EKLENMEDİ (number-led). ── */}
      {loading ? (
        <div className="space-y-3">
          <GlassCard>
            <div className="h-2.5 w-32 rounded bg-white/[0.06]" />
            <div className="h-11 w-40 mt-2 rounded bg-white/[0.06]" />
            <div className="h-2 w-52 mt-2 rounded bg-white/[0.04]" />
          </GlassCard>
          <div className="grid grid-cols-3 gap-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <GlassCard key={i} dense>
                <div className="h-2.5 w-16 rounded bg-white/[0.06]" />
                <div className="h-7 w-14 mt-2 rounded bg-white/[0.06]" />
              </GlassCard>
            ))}
          </div>
        </div>
      ) : dataError && !perf ? (
        <GlassCard className="flex flex-col items-center justify-center text-center gap-3 py-8">
          <AlertTriangle className="w-6 h-6 text-bearish" />
          <div>
            <p className="text-sm font-display text-text-primary">Veriler şu an yüklenemiyor</p>
            <p className="text-xs text-text-muted mt-0.5">Sunucuya ulaşılamıyor olabilir. Lütfen tekrar deneyin.</p>
          </div>
          <button
            onClick={() => load(true)}
            disabled={refreshing}
            className="text-xs font-display text-text-primary bg-white/[0.06] hover:bg-e-2 border border-border-medium px-4 py-2 rounded-lg transition-colors disabled:opacity-50"
          >
            Tekrar dene
          </button>
        </GlassCard>
      ) : (
        <div className="space-y-3">
          {/* Kahraman-rakam — Dönem Net Getiri (40–56px owned-numeral, count-up YOK,
              vanity-counter YOK). §01-K craft-kahraman-rakam + zorunlu makbuz. */}
          <GlassCard>
            <span className="text-micro font-medium text-text-muted uppercase">Dönem Net Getiri</span>
            <div className="flex items-baseline gap-2 mt-1">
              <span className={cn(
                'num font-num-560 tabular-nums leading-none text-[44px]',
                periodReturnPct >= 0 ? 'text-bullish' : 'text-bearish'
              )}>
                {formatPercentage(periodReturnPct)}
              </span>
              <span className="text-sm text-text-muted">{periodLabel}</span>
            </div>
            {/* Makbuz (craft-makbuz-grameri): n işlem · dönem · win-rate — dönem-tutarlı */}
            <p className="text-micro text-text-muted tabular-nums mt-1.5">
              {periodClosedCount} işlem · {periodLabel} · {formatPercentage(periodWinRate, 0, false)} başarı
            </p>
          </GlassCard>

          {/* 3 ikincil — sessiz, eşit; kahraman-rakamla vurgu yarıştırmaz. */}
          <div className="grid grid-cols-3 gap-3">
            <GlassCard dense>
              <span className="text-micro font-medium text-text-muted uppercase">Aktif</span>
              <p className="text-h2 num font-num-560 mt-1 text-text-primary">{activeCount}</p>
              <span className="text-micro text-text-muted font-medium mt-0.5 block">işlem fırsatı</span>
            </GlassCard>
            <GlassCard dense>
              <span className="text-micro font-medium text-text-muted uppercase">Kapanan</span>
              <p className="text-h2 num font-num-560 mt-1 text-text-primary">{periodClosedCount}</p>
              <span className="text-micro text-text-muted font-medium mt-0.5 block">{periodLabel}</span>
            </GlassCard>
            <GlassCard dense>
              <span className="text-micro font-medium text-text-muted uppercase">Başarı</span>
              <p className="text-h2 num font-num-560 mt-1 text-text-primary">{formatPercentage(periodWinRate, 0, false)}</p>
              <span className="text-micro text-text-muted font-medium mt-0.5 block">{periodLabel}</span>
            </GlassCard>
          </div>
        </div>
      )}

      {/* CP-DASH-C1: AI Görüşü kartı Nabız Bandı'nın "sistem sesi" cümlesine
          FOLD edildi (Bible §03 dash-nabız-bandı + widget-taşıma-kilidi) →
          ayrı kart kalktı; veri (long/short/avgConfidence) DurumBandi'ye geçti.
          AIGorusu.tsx dosyası korunur (kullanım kaldırıldı, ölü). */}

      {/* ── Şu an — aktif sinyaller tam-genişlik tablo (DE-5c) ── */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-display text-text-primary flex items-center gap-2">
            <Zap className="w-4 h-4 text-accent-primary" />
            Aktif Sinyaller
          </h2>
          <div className="flex items-center gap-3">
            <DensityToggle value={density} onChange={changeDensity} />
            <Link href="/signals" className="text-xs text-accent-primary hover:text-accent-ui flex items-center gap-1">
              Tümünü Gör <ArrowRight className="w-3 h-3" />
            </Link>
          </div>
        </div>
        <LifecycleHealth counts={lifecycleCounts} />
        {/* CP-DASH-C2: top-N glance (ilk 6) — tam liste Signal Center'da ("Tümünü
            Gör" köprüsü). Satır seçimi inline açmaz, /markets/{symbol} route'una gider. */}
        <SignalTable
          rows={signals.slice(0, 6)}
          livePrices={livePrices}
          onSelect={handleSignalSelect}
          loading={loading}
          showEmpty={!loading && signals.length === 0}
          emptyState={
            <EmptyState
              icon={<Zap className="w-6 h-6 text-accent-primary" />}
              title="Henüz sinyal yok"
              description="AI motorları piyasayı 7/24 tarıyor. Tüm aktif AL/SAT sinyallerini Sinyal Merkezi'nde incele."
              action={
                <Link
                  href="/signals"
                  className="focus-ring inline-flex items-center gap-1.5 text-xs font-display bg-accent-primary hover:bg-accent-hover text-white px-4 py-2 rounded-xl transition-colors"
                >
                  Sinyal Merkezi&apos;ne git <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              }
              className="my-2"
            />
          }
          density={density}
        />
      </div>

      {/* ── Sicil — dönem performansı + gerçekleşmiş sonuçlar (DE-5f) ── */}
      <Sicil
        totalReturn={totalReturnPct}
        profitFactor={periodStats?.profit_factor ?? null}
        maxDrawdown={perf?.drawdown_analysis?.max_drawdown ?? 0}
        tpHitRate={periodStats?.tp_hit_rate ?? 0}
        slRate={periodStats?.sl_rate ?? 0}
        bestSignal={periodStats?.best_signal ?? null}
        worstSignal={periodStats?.worst_signal ?? null}
        periodLabel={periodLabel}
        loading={loading}
        hasData={!!perf && !!periodStats && !dataError}
      />

      {/* ── Piyasa Bağlamı — tek kompakt satır (CP-DASH-A · §03 widget-taşıma-kilidi).
          BTC canlı grafik (TradingView) + Varlık Dağılımı (pie) + En Çok Kazananlar
          KALDIRILDI: piyasa-tarama/enstrüman evi = /markets · Signal Center
          filtre-sayaçları (guardrail-7). Global makro yalnız sade bağlam-satırında
          kalır — pie/gauge/grafik/gömülü-enstrüman YOK. ── */}
      {(global || fng) ? (
        <GlassCard dense className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <span className="text-micro text-text-muted uppercase font-medium">Piyasa Bağlamı</span>
          {global && (
            <>
              <span className="flex items-baseline gap-1.5">
                <span className="text-micro text-text-muted uppercase">Piyasa Değeri</span>
                <span className="text-sm num font-num-520 text-text-primary">{formatLargeNumber(global.total_market_cap_usd)}</span>
                <span className={cn('text-micro font-medium', (global.market_cap_change_24h ?? 0) >= 0 ? 'text-bullish' : 'text-bearish')}>
                  {formatPercentage(global.market_cap_change_24h)}
                </span>
              </span>
              <span className="flex items-baseline gap-1.5">
                <span className="text-micro text-text-muted uppercase">24s Hacim</span>
                <span className="text-sm num font-num-520 text-text-primary">{formatLargeNumber(global.total_volume_usd)}</span>
              </span>
              <span className="flex items-baseline gap-1.5">
                <span className="text-micro text-text-muted uppercase">BTC Dom</span>
                <span className="text-sm num font-num-520 text-text-primary">{formatPercentage(global.btc_dominance, 2, false)}</span>
              </span>
              <span className="flex items-baseline gap-1.5">
                <span className="text-micro text-text-muted uppercase">ETH Dom</span>
                <span className="text-sm num font-num-520 text-text-primary">{formatPercentage(global.eth_dominance, 2, false)}</span>
              </span>
            </>
          )}
          {/* CP-DASH-B: Fear&Greed stat-kartından indi → sade renkli sayı+etiket
              (gauge SVG YOK). fng bağımsız fetch → global fail olsa da görünür. */}
          {fng && (
            <span className="flex items-baseline gap-1.5">
              <span className="text-micro text-text-muted uppercase">Greed</span>
              <span className="text-sm num font-num-520" style={{ color: fngColor(fngValue) }}>{fngValue}</span>
              <span className="text-micro font-medium" style={{ color: fngColor(fngValue) }}>{fngLabel(fngValue)}</span>
            </span>
          )}
          <Link href="/markets" className="ml-auto text-xs text-accent-primary hover:text-accent-ui flex items-center gap-1">
            Piyasalar <ArrowRight className="w-3 h-3" />
          </Link>
        </GlassCard>
      ) : globalError ? (
        <p className="text-micro text-amber bg-amber/10 border border-amber/20 rounded-lg px-3 py-2">
          Piyasa verisi şu an alınamıyor (kaynak geçici sınırladı) — otomatik tekrar denenecek.
        </p>
      ) : null}
    </div>
  );
}
