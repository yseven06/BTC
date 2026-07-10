import React from 'react';
import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { cn, formatPercentage } from '@/lib/utils';

interface DurumBandiProps {
  /** Period phrase for the closed-count, e.g. "24 saatte" / "7 günde" / "30 günde". */
  periodPhrase: string;
  /** Closed trades within the selected period. */
  closedCount: number;
  /** All-time win rate % — labelled "genel" so it is never read as period-scoped. */
  winRate: number;
  /** All-time average return %. */
  avgReturn: number;
  /** Current actionable (non-HOLD) active signal count. */
  activeCount: number;
  loading?: boolean;
  /** False → performance summary unreachable; show an honest fallback, not zeros. */
  hasData?: boolean;
}

const winColor = (w: number) => (w >= 55 ? 'text-bullish' : w <= 45 ? 'text-bearish' : 'text-text-primary');

/**
 * "Durum bandı" — the 3-second "Şu an" headline: what happened over the period
 * (retrospective) on the left, what's live to act on now (link) on the right.
 * Static, derived entirely from data the dashboard already fetches — no motion,
 * no new endpoint.
 */
export function DurumBandi({
  periodPhrase,
  closedCount,
  winRate,
  avgReturn,
  activeCount,
  loading,
  hasData = true,
}: DurumBandiProps) {
  if (loading) {
    return (
      <GlassCard dense>
        <div className="h-4 w-2/3 rounded bg-white/[0.06]" />
      </GlassCard>
    );
  }

  if (!hasData) {
    return (
      <GlassCard dense>
        <p className="text-sm text-text-muted">Özet verisi şu an yüklenemiyor.</p>
      </GlassCard>
    );
  }

  return (
    <GlassCard dense>
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        {/* Retrospective — what happened over the selected period */}
        <p className="text-sm text-text-secondary">
          Son {periodPhrase}{' '}
          <span className="font-display text-text-primary tabular-nums">{closedCount}</span> işlem kapandı
          <span className="text-text-muted"> · </span>
          genel başarı{' '}
          <span className={cn('font-display tabular-nums', winColor(winRate))}>
            {formatPercentage(winRate, 0, false)}
          </span>
          <span className="text-text-muted"> · </span>
          ort.{' '}
          <span className={cn('font-display tabular-nums', avgReturn >= 0 ? 'text-bullish' : 'text-bearish')}>
            {formatPercentage(avgReturn)}
          </span>
        </p>

        {/* Actionable — what's live to act on right now */}
        <Link
          href="/signals"
          className="flex items-center gap-1.5 text-sm font-display text-accent-primary hover:text-accent-hover flex-shrink-0"
        >
          <span className="tabular-nums">{activeCount}</span> aktif sinyal
          <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </div>
    </GlassCard>
  );
}
