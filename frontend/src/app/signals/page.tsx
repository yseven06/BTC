'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { Zap, RefreshCw, TrendingUp, TrendingDown, Eye, LineChart, FileDown } from 'lucide-react';
import { fetchActiveSignals, triggerBatchGeneration, downloadSignalPdf, type ApiSignal } from '@/lib/api';
import { useLivePrices } from '@/hooks/useLivePrices';
import { SignalType } from '@/types';
import { cn } from '@/lib/utils';

// ─── Helpers ─────────────────────────────────────────────────────────────────

function qualityScore(confidence: number): number {
  return Math.round(confidence / 10);
}

function qualityColor(score: number): string {
  if (score >= 8) return 'bg-bullish';
  if (score >= 6) return 'bg-yellow-400';
  if (score >= 4) return 'bg-orange-400';
  return 'bg-bearish';
}

function qualityTextColor(score: number): string {
  if (score >= 8) return 'text-bullish';
  if (score >= 6) return 'text-yellow-400';
  if (score >= 4) return 'text-orange-400';
  return 'text-bearish';
}

/** Derive HTF Alignment label from engine_results JSON */
function getHtfAlignment(enginesData: any): { label: string; type: 'ob' | 'fvg' | 'neutral'; bullish: boolean } {
  if (!enginesData) return { label: 'NÖTR', type: 'neutral', bullish: true };

  const smc = enginesData?.smart_money_concepts;
  const smcBias: string = smc?.bias ?? 'NEUTRAL';
  const findings: string[] = smc?.key_findings ?? [];
  const isBullish = smcBias === 'BULLISH';

  const hasOB  = findings.some((f: string) => f.toLowerCase().includes('order block'));
  const hasFVG = findings.some((f: string) => f.toLowerCase().includes('fair value') || f.toLowerCase().includes('fvg'));

  if (hasOB)  return { label: isBullish ? 'BULLISH OB'  : 'BEARISH OB',  type: 'ob',  bullish: isBullish };
  if (hasFVG) return { label: isBullish ? 'BULLISH FVG' : 'BEARISH FVG', type: 'fvg', bullish: isBullish };

  // Fallback to direction bias
  if (smcBias === 'BULLISH') return { label: 'BULLISH', type: 'neutral', bullish: true };
  if (smcBias === 'BEARISH') return { label: 'BEARISH', type: 'neutral', bullish: false };
  return { label: 'NÖTR', type: 'neutral', bullish: true };
}

/** Derive Purge Type from CRT engine */
function getPurgeType(enginesData: any): { label: string; low: boolean } | null {
  if (!enginesData) return null;
  const crt = enginesData?.candle_range_theory;
  if (!crt) return null;

  const dir: string | null = crt?.supporting_data?.latest_signal_direction ?? null;
  const sweeps: number = crt?.supporting_data?.sweeps_count ?? 0;

  if (sweeps === 0) return null;
  if (dir === 'long')  return { label: 'LOW',  low: true };
  if (dir === 'short') return { label: 'HIGH', low: false };

  // fallback: range position zone
  const zone: string = crt?.supporting_data?.range_position?.zone ?? '';
  if (zone === 'discount') return { label: 'LOW',  low: true };
  if (zone === 'premium')  return { label: 'HIGH', low: false };
  return null;
}

function directionLabel(sig: ApiSignal): { label: string; long: boolean } {
  const d = sig.direction ?? sig.signal_type ?? '';
  const isLong = d === 'bullish' || d === 'STRONG_BUY' || d === 'BUY';
  return { label: isLong ? 'LONG' : 'SHORT', long: isLong };
}

interface OnchainInfo {
  fearGreed: number | null;
  fearGreedClass: string | null;
  athDistance: number | null;
  hashRate: number | null;
  fastFee: number | null;
  devScore: number | null;
  rank: number | null;
  findings: string[];
  applicable: boolean;
}

function getOnchainInfo(enginesData: any): OnchainInfo | null {
  if (!enginesData) return null;
  const o = enginesData?.onchain_analysis;
  if (!o) return null;
  const sd = o.supporting_data ?? {};
  return {
    fearGreed:      sd.fear_greed_value ?? null,
    fearGreedClass: sd.fear_greed_classification ?? null,
    athDistance:    sd.ath_distance_pct ?? null,
    hashRate:       sd.btc_hash_rate_ths ?? null,
    fastFee:        sd.btc_fast_fee_sat_vb ?? null,
    devScore:       sd.developer_score ?? null,
    rank:           sd.market_cap_rank ?? null,
    findings:       o.key_findings ?? [],
    applicable:     sd.asset_type !== 'stock',
  };
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function QualityBar({ score }: { score: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-1.5 bg-bg-tertiary rounded-full overflow-hidden">
        <div
          className={cn('h-full rounded-full transition-all', qualityColor(score))}
          style={{ width: `${score * 10}%` }}
        />
      </div>
      <span className={cn('text-xs font-bold font-mono', qualityTextColor(score))}>
        {score}/10
      </span>
    </div>
  );
}

function HtfBadge({ label, bullish }: { label: string; bullish: boolean }) {
  return (
    <span className={cn(
      'inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold tracking-wide',
      bullish
        ? 'bg-bullish/15 text-bullish border border-bullish/30'
        : 'bg-bearish/15 text-bearish border border-bearish/30'
    )}>
      {label}
    </span>
  );
}

function PurgeBadge({ label, low }: { label: string; low: boolean }) {
  return (
    <span className={cn(
      'inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold tracking-wide',
      low
        ? 'bg-bullish/10 text-bullish'
        : 'bg-bearish/10 text-bearish'
    )}>
      {label}
    </span>
  );
}

function OutcomeBadge({ outcome }: { outcome: string }) {
  const config: Record<string, { label: string; cls: string }> = {
    active:    { label: 'AKTİF',     cls: 'bg-accent-primary/15 text-accent-primary border-accent-primary/30' },
    win:       { label: 'KAZANDI ✓', cls: 'bg-bullish/15 text-bullish border-bullish/30' },
    loss:      { label: 'PATLADI ✗', cls: 'bg-bearish/15 text-bearish border-bearish/30' },
    breakeven: { label: 'BERABERE',  cls: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30' },
    expired:   { label: 'GEÇERSİZ',  cls: 'bg-text-muted/15 text-text-muted border-text-muted/30' },
  };
  const c = config[outcome] ?? config.active;
  return (
    <span className={cn(
      'inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold tracking-wide border',
      c.cls
    )}>
      {c.label}
    </span>
  );
}

function DirectionBadge({ label, long }: { label: string; long: boolean }) {
  return (
    <span className={cn(
      'inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-[11px] font-bold',
      long
        ? 'bg-bullish text-black'
        : 'bg-bearish text-white'
    )}>
      {long ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
      {label}
    </span>
  );
}

// ─── Signal Detail Drawer ─────────────────────────────────────────────────────

function SignalDrawer({ sig, onClose }: { sig: ApiSignal; onClose: () => void }) {
  const htf     = getHtfAlignment(sig.engines_data);
  const purge   = getPurgeType(sig.engines_data);
  const dir     = directionLabel(sig);
  const qScore  = qualityScore(sig.confidence_score);
  const onchain = getOnchainInfo(sig.engines_data);

  return (
    <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={onClose}>
      <div
        className="w-full max-w-lg glass-panel border border-border-medium rounded-2xl p-6 space-y-5"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-bg-tertiary border border-border-subtle flex items-center justify-center font-bold font-mono text-sm text-accent-primary">
              {sig.asset?.symbol.slice(0, 2)}
            </div>
            <div>
              <h3 className="font-bold text-text-primary">{sig.asset?.symbol}
                <span className="ml-2 text-[10px] text-text-muted bg-bg-tertiary px-1.5 py-0.5 rounded">{sig.timeframe}</span>
              </h3>
              <p className="text-xs text-text-secondary">{sig.asset?.name}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-text-muted hover:text-text-primary text-lg leading-none">✕</button>
        </div>

        {/* Badges row */}
        <div className="flex flex-wrap gap-2">
          <DirectionBadge {...dir} />
          <HtfBadge {...htf} />
          {purge && <PurgeBadge {...purge} />}
        </div>

        {/* Levels grid */}
        <div className="grid grid-cols-2 gap-3">
          {[
            { label: 'Giriş Bölgesi',  value: `${sig.entry_zone_low?.toLocaleString('tr-TR')} – ${sig.entry_zone_high?.toLocaleString('tr-TR')}`, color: 'text-text-primary' },
            { label: 'Zarar Durdur',   value: sig.stop_loss?.toLocaleString('tr-TR') ?? '—', color: 'text-bearish' },
            { label: 'Hedef 1 (TP1)',  value: sig.tp1?.toLocaleString('tr-TR') ?? '—', color: 'text-bullish' },
            { label: 'Hedef 2 (TP2)',  value: sig.tp2?.toLocaleString('tr-TR') ?? '—', color: 'text-bullish' },
          ].map(({ label, value, color }) => (
            <div key={label} className="bg-bg-secondary/60 rounded-xl p-3 border border-border-subtle">
              <p className="text-[10px] text-text-muted uppercase font-semibold mb-1">{label}</p>
              <p className={cn('text-sm font-bold font-mono', color)}>{value}</p>
            </div>
          ))}
        </div>

        {/* Scores */}
        <div className="flex items-center justify-between bg-bg-secondary/60 rounded-xl p-3 border border-border-subtle">
          <div>
            <p className="text-[10px] text-text-muted uppercase font-semibold mb-1">Kalite Skoru</p>
            <QualityBar score={qScore} />
          </div>
          <div className="text-right">
            <p className="text-[10px] text-text-muted uppercase font-semibold mb-1">Olasılık</p>
            <p className="text-sm font-bold font-mono text-accent-primary">{sig.probability_score}%</p>
          </div>
          <div className="text-right">
            <p className="text-[10px] text-text-muted uppercase font-semibold mb-1">Risk</p>
            <p className="text-sm font-bold font-mono text-text-primary capitalize">{sig.risk_level}</p>
          </div>
        </div>

        {/* Explanation */}
        {sig.explanation_tr && (
          <p className="text-xs text-text-secondary leading-relaxed bg-bg-secondary/40 rounded-xl p-3 border border-border-subtle">
            {sig.explanation_tr}
          </p>
        )}

        {/* On-Chain Insights */}
        {onchain && onchain.applicable && (
          <div className="bg-bg-secondary/40 rounded-xl p-3 border border-border-subtle space-y-2">
            <p className="text-[10px] text-text-muted uppercase font-semibold flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-accent-secondary" />
              On-Chain & Sentiment
            </p>

            <div className="grid grid-cols-2 gap-2 text-xs">
              {onchain.fearGreed != null && (
                <div className="bg-bg-tertiary/60 rounded-lg p-2">
                  <p className="text-[10px] text-text-muted">Fear & Greed</p>
                  <p className={cn('font-bold font-mono',
                    onchain.fearGreed <= 25 ? 'text-bearish' :
                    onchain.fearGreed >= 75 ? 'text-bullish' : 'text-yellow-400')}>
                    {onchain.fearGreed} <span className="text-[10px] text-text-muted font-normal">{onchain.fearGreedClass ?? ''}</span>
                  </p>
                </div>
              )}
              {onchain.athDistance != null && (
                <div className="bg-bg-tertiary/60 rounded-lg p-2">
                  <p className="text-[10px] text-text-muted">ATH Mesafesi</p>
                  <p className={cn('font-bold font-mono', onchain.athDistance < -30 ? 'text-bullish' : onchain.athDistance > -10 ? 'text-bearish' : 'text-text-primary')}>
                    {onchain.athDistance.toFixed(1)}%
                  </p>
                </div>
              )}
              {onchain.rank != null && (
                <div className="bg-bg-tertiary/60 rounded-lg p-2">
                  <p className="text-[10px] text-text-muted">Piyasa Sırası</p>
                  <p className="font-bold font-mono text-text-primary">#{onchain.rank}</p>
                </div>
              )}
              {onchain.fastFee != null && (
                <div className="bg-bg-tertiary/60 rounded-lg p-2">
                  <p className="text-[10px] text-text-muted">BTC Ücret</p>
                  <p className="font-bold font-mono text-text-primary">{onchain.fastFee} sat/vB</p>
                </div>
              )}
            </div>

            {onchain.findings.length > 0 && (
              <ul className="space-y-1 mt-2">
                {onchain.findings.slice(0, 4).map((f, i) => (
                  <li key={i} className="text-[11px] text-text-secondary flex gap-1.5">
                    <span className="text-accent-secondary flex-shrink-0">•</span> {f}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={() => downloadSignalPdf(sig.id, sig.asset?.symbol ?? 'signal').catch(() =>
              alert('PDF indirilemedi. Pro/Premium aboneliği gerekir.'))}
            className="flex items-center justify-center gap-2 py-2.5 rounded-xl bg-bg-tertiary border border-border-medium hover:border-accent-primary/40 text-text-primary text-sm font-semibold transition-colors"
          >
            <FileDown className="w-4 h-4" /> PDF İndir
          </button>
          <Link
            href={`/markets/${encodeURIComponent(sig.asset?.symbol ?? '')}`}
            className="flex items-center justify-center gap-2 py-2.5 rounded-xl bg-accent-primary hover:bg-accent-secondary text-white text-sm font-semibold transition-colors"
          >
            <LineChart className="w-4 h-4" /> Grafiği Aç
          </Link>
        </div>
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

type TfFilter = 'all' | '1h' | '4h' | '1d';

export default function SignalsPage() {
  const [signals, setSignals]     = useState<ApiSignal[]>([]);
  const [total, setTotal]         = useState(0);
  const [loading, setLoading]     = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [selected, setSelected]   = useState<ApiSignal | null>(null);
  const [tfFilter, setTfFilter]   = useState<TfFilter>('all');

  const filtered = tfFilter === 'all' ? signals : signals.filter((s) => (s.timeframe ?? '').toLowerCase() === tfFilter);
  const symbols  = filtered.map((s) => s.asset?.symbol ?? '').filter(Boolean);
  const livePrices = useLivePrices(symbols);

  const load = async (showRefresh = false) => {
    if (showRefresh) setRefreshing(true); else setLoading(true);
    try {
      const res = await fetchActiveSignals({ page_size: 200 });
      setSignals(res.items);
      setTotal(res.total);
    } catch { /**/ } finally {
      setLoading(false); setRefreshing(false);
    }
  };

  const generateAll = async () => {
    setGenerating(true);
    try {
      await triggerBatchGeneration();
      for (let i = 0; i < 12; i++) {
        await new Promise((r) => setTimeout(r, 5000));
        const res = await fetchActiveSignals({ page_size: 100 });
        if (res.total > 0) { setSignals(res.items); setTotal(res.total); break; }
      }
    } catch { /**/ } finally { setGenerating(false); }
  };

  useEffect(() => { load(); }, []);

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-extrabold text-text-primary flex items-center gap-2">
            <Zap className="w-6 h-6 text-accent-primary" /> Sinyal Merkezi
          </h1>
          <p className="text-sm text-text-secondary mt-1">
            Canlı setup önceliklendiricisi · kurumsal kalite skoru · fiyatlar anlık
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm font-mono text-text-muted">{total} sinyal</span>
          <button
            onClick={generateAll}
            disabled={generating || refreshing}
            className="flex items-center gap-1.5 text-xs font-semibold text-accent-primary hover:text-accent-secondary border border-accent-primary/30 hover:border-accent-primary/60 px-3 py-1.5 rounded-lg transition-all disabled:opacity-50"
          >
            <Zap className={cn('w-3.5 h-3.5', generating && 'animate-pulse')} />
            {generating ? 'Üretiliyor...' : 'Sinyal Üret'}
          </button>
          <button
            onClick={() => load(true)}
            disabled={refreshing || generating}
            className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-primary transition-colors disabled:opacity-50 px-2 py-1.5"
          >
            <RefreshCw className={cn('w-3.5 h-3.5', refreshing && 'animate-spin')} />
          </button>
        </div>
      </div>

      {/* Timeframe filter */}
      <div className="flex items-center gap-1 p-1 bg-bg-secondary border border-border-subtle rounded-xl w-fit">
        {(['all', '1h', '4h', '1d'] as TfFilter[]).map((tf) => {
          const cnt = tf === 'all' ? signals.length : signals.filter((s) => s.timeframe?.toLowerCase() === tf).length;
          return (
            <button
              key={tf}
              onClick={() => setTfFilter(tf)}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold rounded-lg transition-all',
                tfFilter === tf
                  ? 'bg-accent-primary text-white shadow-glow-sm'
                  : 'text-text-muted hover:text-text-primary'
              )}
            >
              {tf === 'all' ? 'TÜMÜ' : tf.toUpperCase()}
              <span className={cn(
                'text-[10px] font-mono px-1.5 py-0.5 rounded',
                tfFilter === tf ? 'bg-white/20' : 'bg-bg-tertiary/60'
              )}>
                {cnt}
              </span>
            </button>
          );
        })}
      </div>

      {/* Table */}
      <div className="glass-panel border border-border-subtle rounded-2xl overflow-hidden">
        {/* Table head */}
        <div className="grid grid-cols-[2fr_1fr_1.2fr_1.5fr_1.3fr_1.5fr_auto] gap-4 px-5 py-3 border-b border-border-subtle bg-bg-secondary/30">
          {['SEMBOL · TF', 'YÖN', 'ANLIK FİYAT', 'KALİTE SKORU', 'DURUM', 'HTF / PURGE', 'ANALİZ'].map((h) => (
            <span key={h} className="text-[10px] font-bold text-text-muted uppercase tracking-wider">{h}</span>
          ))}
        </div>

        {loading && (
          <div className="flex justify-center py-16">
            <div className="w-7 h-7 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {!loading && signals.length === 0 && (
          <div className="py-16 text-center text-text-muted text-sm">
            Aktif sinyal bulunamadı. &nbsp;
            <button onClick={generateAll} disabled={generating} className="text-accent-primary hover:underline font-semibold">
              {generating ? 'Üretiliyor...' : 'Şimdi üret →'}
            </button>
          </div>
        )}

        <div className="divide-y divide-border-subtle">
          {filtered.map((sig) => {
            const sym    = sig.asset?.symbol ?? '';
            const live   = livePrices[sym];
            const qScore = qualityScore(sig.confidence_score);
            const htf    = getHtfAlignment(sig.engines_data);
            const purge  = getPurgeType(sig.engines_data);
            const dir    = directionLabel(sig);
            const up     = (live?.changePct24h ?? 0) >= 0;
            const outcome = sig.outcome ?? 'active';
            const invalid = outcome === 'loss';

            return (
              <div
                key={sig.id}
                className={cn(
                  "grid grid-cols-[2fr_1fr_1.2fr_1.5fr_1.3fr_1.5fr_auto] gap-4 items-center px-5 py-3.5 transition-colors",
                  invalid ? 'bg-bearish/[0.04] opacity-70' : 'hover:bg-white/[0.02]'
                )}
              >
                {/* Symbol + Timeframe */}
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-8 h-8 rounded-lg bg-bg-tertiary border border-border-subtle flex items-center justify-center font-bold font-mono text-xs text-accent-primary flex-shrink-0">
                    {sym.slice(0, 2)}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-bold text-text-primary truncate flex items-center gap-1.5">
                      {sym}
                      <span className="text-[9px] font-bold text-accent-primary bg-accent-primary/10 border border-accent-primary/30 px-1.5 py-0.5 rounded uppercase">
                        {sig.timeframe}
                      </span>
                    </p>
                    <p className="text-[10px] text-text-muted truncate">{sig.asset?.name}</p>
                  </div>
                </div>

                {/* Direction */}
                <div className={invalid ? 'line-through opacity-60' : ''}>
                  <DirectionBadge {...dir} />
                </div>

                {/* Live Price */}
                <div>
                  {live ? (
                    <div>
                      <p className={cn('text-sm font-bold font-mono', invalid ? 'text-text-muted line-through' : 'text-text-primary')}>
                        {live.price.toLocaleString('tr-TR', { maximumFractionDigits: 4 })}
                      </p>
                      <p className={cn('text-[10px] font-mono font-semibold', up ? 'text-bullish' : 'text-bearish')}>
                        {up ? '+' : ''}{live.changePct24h?.toFixed(2)}%
                      </p>
                    </div>
                  ) : (
                    <span className="text-xs text-text-muted animate-pulse">—</span>
                  )}
                </div>

                {/* Quality Score */}
                <div><QualityBar score={qScore} /></div>

                {/* Outcome status */}
                <div>
                  <OutcomeBadge outcome={outcome} />
                </div>

                {/* HTF + Purge stacked */}
                <div className="flex flex-col gap-1">
                  <HtfBadge {...htf} />
                  {purge && <PurgeBadge {...purge} />}
                </div>

                {/* Action */}
                <div>
                  <button
                    onClick={() => setSelected(sig)}
                    className="flex items-center gap-1 text-[11px] font-semibold text-text-muted hover:text-accent-primary border border-border-subtle hover:border-accent-primary/40 px-2.5 py-1 rounded-lg transition-all"
                  >
                    <Eye className="w-3 h-3" /> Analiz
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Detail Drawer */}
      {selected && <SignalDrawer sig={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
