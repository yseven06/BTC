'use client';

import React from 'react';
import { Eye, TrendingUp, TrendingDown } from 'lucide-react';
import { type ApiSignal } from '@/lib/api';
import { type LivePrice } from '@/hooks/useLivePrices';
import { cn, formatAbsoluteTimeTR, formatPrice, formatPercentage } from '@/lib/utils';
import { PriceSkeleton } from '@/components/ui/PriceSkeleton';
import { Karot } from '@/components/signals/Karot';
import { signalToKarotConfs } from '@/lib/karot-adapter';
import { LiveStatusBadge } from '@/components/ui/LiveStatusBadge';

// ─── Column template ──────────────────────────────────────────────────────────
// Single source for the 7-column grid so the header and every row stay aligned.
// Both Dashboard ("Şu an") and Sinyal Merkezi mount this ONE table — no duplication.
const GRID_COLS = 'grid-cols-[2fr_1fr_1.2fr_1.5fr_1.3fr_1.5fr_auto]';
const COLUMNS = ['SEMBOL · TF', 'YÖN', 'ANLIK FİYAT', 'KALİTE SKORU', 'DURUM', 'ÜRETİLDİ', 'ANALİZ'] as const;

// ─── Density ──────────────────────────────────────────────────────────────────
// User-controlled row density. Drives the per-row vertical padding via the
// inherited `--row-h` custom property. 'comfortable' = 0.875rem = the historical
// py-3.5 (byte-identical default); 'compact' = 0.5rem for more rows per screen.
export type Density = 'comfortable' | 'compact';
const ROW_H: Record<Density, string> = { comfortable: '0.875rem', compact: '0.5rem' };

// ─── Quality helpers ──────────────────────────────────────────────────────────
export function qualityScore(confidence: number): number {
  return Math.round(confidence / 10);
}

export function qualityColor(score: number): string {
  if (score >= 8) return 'bg-bullish';
  if (score >= 6) return 'bg-amber';
  if (score >= 4) return 'bg-amber/70';
  return 'bg-bearish';
}

export function qualityTextColor(score: number): string {
  if (score >= 8) return 'text-bullish';
  if (score >= 6) return 'text-amber';
  if (score >= 4) return 'text-amber/80';
  return 'text-bearish';
}

export type DirState = 'long' | 'short' | 'wait';
export function directionLabel(sig: ApiSignal): { label: string; state: DirState } {
  const d = (sig.direction ?? '').toLowerCase();
  const t = (sig.signal_type ?? '').toLowerCase();
  if (d === 'bullish' || t === 'buy' || t === 'strong_buy')
    return { label: 'LONG',  state: 'long' };
  if (d === 'bearish' || t === 'sell' || t === 'strong_sell')
    return { label: 'SHORT', state: 'short' };
  return { label: 'BEKLE', state: 'wait' };
}

// ─── Cell primitives ──────────────────────────────────────────────────────────
export function QualityBar({ score }: { score: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-1.5 bg-bg-tertiary rounded-full overflow-hidden">
        <div
          className={cn('h-full rounded-full transition-all', qualityColor(score))}
          style={{ width: `${score * 10}%` }}
        />
      </div>
      <span className={cn('text-xs num font-num-520', qualityTextColor(score))}>
        {score}/10
      </span>
    </div>
  );
}

export function OutcomeBadge({ outcome }: { outcome: string }) {
  const config: Record<string, { label: string; cls: string }> = {
    active:    { label: 'AKTİF',     cls: 'bg-accent-primary/15 text-accent-primary border-accent-primary/30' },
    win:       { label: 'KAZANDI ✓', cls: 'bg-bullish/15 text-bullish border-bullish/30' },
    loss:      { label: 'PATLADI ✗', cls: 'bg-bearish/15 text-bearish border-bearish/30' },
    breakeven: { label: 'BERABERE',  cls: 'bg-amber/15 text-amber border-amber/30' },
    expired:   { label: 'GEÇERSİZ',  cls: 'bg-text-muted/15 text-text-muted border-text-muted/30' },
    invalidated: { label: 'İPTAL EDİLDİ', cls: 'bg-accent-ui/15 text-accent-ui border-accent-ui/30' },
  };
  const c = config[outcome] ?? config.active;
  return (
    <span className={cn(
      'inline-flex items-center px-2 py-0.5 rounded text-micro font-medium border',
      c.cls
    )}>
      {c.label}
    </span>
  );
}

export function DirectionBadge({ label, state }: { label: string; state: DirState }) {
  const config = {
    long:  { cls: 'bg-bullish text-black',     icon: <TrendingUp   className="w-3 h-3" /> },
    short: { cls: 'bg-bearish text-white',     icon: <TrendingDown className="w-3 h-3" /> },
    wait:  { cls: 'bg-text-muted/40 text-text-primary border border-text-muted/40', icon: <span className="w-3 h-3 inline-block">⏸</span> },
  } as const;
  const c = config[state];
  return (
    <span className={cn(
      'inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-micro font-medium',
      c.cls
    )}>
      {c.icon}
      {label}
    </span>
  );
}

// ─── Density toggle ───────────────────────────────────────────────────────────
const DENSITY_OPTS: { id: Density; label: string }[] = [
  { id: 'comfortable', label: 'Rahat' },
  { id: 'compact', label: 'Sıkışık' },
];

/**
 * Segmented Rahat/Sıkışık control. Purely a user preference — flips row density
 * instantly (no fetch, no motion). Shared so the Dashboard "Şu an" band reuses it.
 */
export function DensityToggle({ value, onChange }: { value: Density; onChange: (d: Density) => void }) {
  return (
    <div className="inline-flex items-center gap-0.5 p-0.5 bg-bg-secondary border border-border-subtle rounded-xl">
      {DENSITY_OPTS.map((o) => (
        <button
          key={o.id}
          onClick={() => onChange(o.id)}
          aria-pressed={value === o.id}
          title={o.id === 'compact' ? 'Sıkışık satırlar — ekranda daha çok sinyal' : 'Rahat satırlar'}
          className={cn(
            'px-2.5 py-1 text-micro font-medium rounded-lg transition-colors',
            value === o.id
              ? 'bg-accent-primary text-white'
              : 'text-text-muted hover:text-text-primary'
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// ─── Row ──────────────────────────────────────────────────────────────────────
export function SignalTableRow({
  sig,
  live,
  onSelect,
}: {
  sig: ApiSignal;
  live?: LivePrice;
  onSelect: (sig: ApiSignal) => void;
}) {
  const sym     = sig.asset?.symbol ?? '';
  const qScore  = qualityScore(sig.confidence_score);
  const dir     = directionLabel(sig);
  const up      = (live?.changePct24h ?? 0) >= 0;
  const outcome = sig.outcome ?? 'active';
  const invalid = outcome === 'loss';

  return (
    <div
      className={cn(
        'grid gap-4 items-center px-5 transition-colors',
        GRID_COLS,
        invalid ? 'bg-bearish/[0.04] opacity-70' : 'hover:bg-e-2'
      )}
      // Vertical padding is density-driven (inherited --row-h); default matches py-3.5.
      style={{ paddingTop: 'var(--row-h, 0.875rem)', paddingBottom: 'var(--row-h, 0.875rem)' }}
    >
      {/* Symbol + Timeframe */}
      <div className="flex items-center gap-3 min-w-0">
        <div className="w-8 h-8 rounded-lg bg-bg-tertiary border border-border-subtle flex items-center justify-center num font-num-520 text-xs text-accent-primary flex-shrink-0">
          {sym.slice(0, 2)}
        </div>
        <div className="min-w-0">
          <p className="text-sm font-display text-text-primary truncate flex items-center gap-1.5">
            {sym}
            <span className="text-micro font-medium text-accent-primary bg-accent-primary/10 border border-accent-primary/30 px-1.5 py-0.5 rounded uppercase">
              {sig.timeframe}
            </span>
          </p>
          <p className="text-micro text-text-muted truncate">{sig.asset?.name}</p>
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
            <p className={cn('text-sm num font-num-520', invalid ? 'text-text-muted line-through' : 'text-text-primary')}>
              {formatPrice(live.price)}
            </p>
            <p className={cn('text-micro font-mono font-medium', up ? 'text-bullish' : 'text-bearish')}>
              {formatPercentage(live.changePct24h ?? 0)}
            </p>
          </div>
        ) : (
          <PriceSkeleton />
        )}
      </div>

      {/* Konsensüs (Karot · additif) + Kalite Skoru */}
      <div className="flex items-center gap-2.5">
        <Karot
          confs={signalToKarotConfs(sig.engines_data)}
          size={18}
          title={`Motor konsensüsü — ${sym}`}
          className="flex-shrink-0"
        />
        <QualityBar score={qScore} />
      </div>

      {/* Durum — aktif sinyalde canli yasam-dongusu fazi; kapananlarda sonuc rozeti korunur */}
      <div>
        {outcome === 'active' && sig.live_status ? (
          <LiveStatusBadge
            status={sig.live_status}
            since={sig.live_status_since}
            reason={sig.status_reason}
          />
        ) : (
          <OutcomeBadge outcome={outcome} />
        )}
      </div>

      {/* Generation time (TR saati) */}
      <div className="text-micro font-mono text-text-muted">
        {formatAbsoluteTimeTR(sig.generated_at)}
      </div>

      {/* Action */}
      <div>
        <button
          onClick={() => onSelect(sig)}
          className="flex items-center gap-1 text-micro font-medium text-text-muted hover:text-accent-primary border border-border-subtle hover:border-accent-primary/40 px-2.5 py-1 rounded-lg transition-all"
        >
          <Eye className="w-3 h-3" /> Analiz
        </button>
      </div>
    </div>
  );
}

// ─── Table ────────────────────────────────────────────────────────────────────
interface SignalTableProps {
  /** Rows to render (already filtered/sorted by the caller). */
  rows: ApiSignal[];
  /** Live price map keyed by symbol (from useLivePrices). */
  livePrices: Record<string, LivePrice>;
  /** Opens the analysis view for a signal (drawer on Sinyal Merkezi, detail on Dashboard). */
  onSelect: (sig: ApiSignal) => void;
  /** Show the loading spinner instead of rows. */
  loading?: boolean;
  /** Render `emptyState` (when not loading) — caller decides the empty condition. */
  showEmpty?: boolean;
  /** Page-specific empty state node. */
  emptyState?: React.ReactNode;
  /** Row density; default 'comfortable' renders byte-identically to the legacy table. */
  density?: Density;
}

/**
 * Shared dense signal table — the ONE table component used by both the Dashboard
 * "Şu an" band and Sinyal Merkezi. Header + rows share a single column template
 * so they always stay aligned. Presentational only (no motion/glow — Premium).
 */
export function SignalTable({
  rows,
  livePrices,
  onSelect,
  loading = false,
  showEmpty = false,
  emptyState,
  density = 'comfortable',
}: SignalTableProps) {
  return (
    <div
      className="glass-panel border border-border-subtle rounded-2xl overflow-hidden"
      // --row-h cascades to every row's vertical padding (see SignalTableRow).
      style={{ ['--row-h' as string]: ROW_H[density] } as React.CSSProperties}
    >
      {/* Table head */}
      <div className={cn('grid gap-4 px-5 py-3 border-b border-border-subtle bg-bg-secondary/30', GRID_COLS)}>
        {COLUMNS.map((h) => (
          <span key={h} className="text-micro font-medium text-text-muted uppercase">{h}</span>
        ))}
      </div>

      {loading && (
        <div className="flex justify-center py-16">
          <div className="w-7 h-7 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      {!loading && showEmpty && emptyState}

      <div className="divide-y divide-border-subtle">
        {rows.map((sig) => (
          <SignalTableRow
            key={sig.id}
            sig={sig}
            live={livePrices[sig.asset?.symbol ?? '']}
            onSelect={onSelect}
          />
        ))}
      </div>
    </div>
  );
}
