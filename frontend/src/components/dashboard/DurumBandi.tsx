import React from 'react';
import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { LIVE_STATUS_META } from '@/components/ui/LiveStatusBadge';
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
  /** CP-DASH-C1: AI Görüşü kartından fold edilen "sistem sesi" verisi — aktif
   *  sinyallerin LONG/SHORT dengesi + ortalama güven (client-türetme, endpoint yok). */
  longCount: number;
  shortCount: number;
  avgConfidence: number;
  /** Lifecycle-health census over the active signals (client-derived) — folded into
   *  the system voice; the standalone LifecycleHealth row was removed from Dashboard. */
  lifecycleCounts?: Record<string, number>;
  /** Active signals generated today (product TR day boundary), client-derived. */
  bornTodayCount?: number;
  loading?: boolean;
  /** False → performance summary unreachable; show an honest fallback, not zeros. */
  hasData?: boolean;
}

const winColor = (w: number) => (w >= 55 ? 'text-bullish' : w <= 45 ? 'text-bearish' : 'text-text-primary');

/**
 * Nabız Bandı (CP-DASH-C1 · Bible §03 dash-nabız-bandı) — Dashboard üstündeki tek
 * yaşayan-hero: üstte AI "sistem sesi" cümlesi (AI ne düşünüyor?), altta dönem
 * durumu (çözüm-fotonları) + canlı aktif-sinyal köprüsü. Tümü dashboard'ın zaten
 * çektiği veriden client-türetilir — yeni endpoint yok, motion yok, atmosfer-ışık
 * yok, ≤~120px. Rejim verisi mevcut olmadığından omit edilir (uydurma yok).
 * DurumBandı'nın (DE-1) terfisi; AI Görüşü kartı (DE-3) buraya fold edildi.
 */
export function DurumBandi({
  periodPhrase,
  closedCount,
  winRate,
  avgReturn,
  activeCount,
  longCount,
  shortCount,
  avgConfidence,
  lifecycleCounts,
  bornTodayCount = 0,
  loading,
  hasData = true,
}: DurumBandiProps) {
  if (loading) {
    // Hairline-iskelet (§03-K pv-yükleme): statik, sabit-boyut, --hl10 tek-aile.
    return (
      <GlassCard dense>
        <div className="h-4 w-2/3 rounded bg-[var(--hl10)]" />
        <div className="h-3.5 w-1/2 mt-2 rounded bg-[var(--hl10)]" />
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

  const total = longCount + shortCount;
  const longShare = total ? longCount / total : 0.5;
  const stance =
    longShare >= 0.6 ? { label: 'LONG eğilimli', cls: 'text-bullish' }
    : longShare <= 0.4 ? { label: 'SHORT eğilimli', cls: 'text-bearish' }
    : { label: 'dengeli', cls: 'text-text-primary' };

  // Attention-phase census — folds the removed LifecycleHealth row into the
  // voice. "active" is intentionally excluded (activeCount is already shown in
  // the bridge below → would duplicate); only non-zero phases render, labels
  // come from the single LIVE_STATUS_META source (no invented status).
  const census = (['approaching_tp', 'weakening', 'invalidating'] as const)
    .map((k) => ({ k, n: lifecycleCounts?.[k] ?? 0, meta: LIVE_STATUS_META[k] }))
    .filter((c) => c.n > 0);

  return (
    <GlassCard dense>
      <div className="space-y-1.5">
        {/* AI "sistem sesi" cümlesi — "AI ne düşünüyor?" (AIGorusu fold, client-türetme).
            text-xs sm:text-sm: dar ekranda band ≤~120px kalsın (sarma satırları kısalır). */}
        <p className="text-xs sm:text-sm leading-snug text-text-secondary">
          <span className="text-micro text-text-muted uppercase font-medium mr-1.5">AI Nabzı</span>
          {total > 0 ? (
            <>
              şu an <span className={cn('font-display', stance.cls)}>{stance.label}</span>
              <span className="text-text-muted"> · </span>
              <span className="text-bullish tabular-nums font-medium">{longCount}</span> LONG
              {' / '}
              <span className="text-bearish tabular-nums font-medium">{shortCount}</span> SHORT
              {/* ort. güven — dar ekranda gizle (band ≤120px); ≥sm'de görünür */}
              <span className="hidden sm:inline">
                <span className="text-text-muted"> · ort. güven </span>
                <span className="text-text-primary tabular-nums font-medium">%{avgConfidence}</span>
              </span>
            </>
          ) : (
            <span>şu an aktif AL/SAT sinyali taşımıyor.</span>
          )}
          {/* "Bugün doğan N" — kısa, her ekranda görünür (gerçek generated_at türevi) */}
          {total > 0 && bornTodayCount > 0 && (
            <span> · bugün <span className="text-text-primary tabular-nums font-medium">{bornTodayCount}</span> yeni</span>
          )}
          {/* Lifecycle-census (dikkat-fazları) — band ≤~120px için ≥sm'de görünür;
              dar ekranda kritik-olmayan detay gizlenir (bilgi Signal Center'da tam). */}
          {total > 0 && census.length > 0 && (
            <span className="hidden sm:inline">
              {census.map((c) => (
                <React.Fragment key={c.k}>
                  <span className="text-text-muted"> · </span>
                  <span className={cn('tabular-nums font-medium', c.meta.cls)}>{c.n}</span>{' '}
                  {c.meta.label}
                </React.Fragment>
              ))}
            </span>
          )}
        </p>

        {/* Dönem durumu (çözüm-fotonları) + canlı aktif köprüsü */}
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
          <p className="text-xs sm:text-sm leading-snug text-text-secondary">
            Son {periodPhrase}{' '}
            <span className="font-display text-text-primary tabular-nums">{closedCount}</span> işlem kapandı
            <span className="text-text-muted"> · </span>
            genel başarı{' '}
            <span className={cn('font-display tabular-nums', winColor(winRate))}>
              {formatPercentage(winRate, 0, false)}
            </span>
            {/* ort. getiri — dar ekranda gizle (band ≤120px); ≥sm'de görünür */}
            <span className="hidden sm:inline">
              <span className="text-text-muted"> · </span>
              ort.{' '}
              <span className={cn('font-display tabular-nums', avgReturn >= 0 ? 'text-bullish' : 'text-bearish')}>
                {formatPercentage(avgReturn)}
              </span>
            </span>
          </p>

          <Link
            href="/signals"
            className="flex items-center gap-1.5 text-xs sm:text-sm font-display text-accent-primary hover:text-accent-hover flex-shrink-0"
          >
            <span className="tabular-nums">{activeCount}</span> aktif sinyal
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </div>
    </GlassCard>
  );
}
