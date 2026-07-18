'use client';

// CP-DASH-IA-A · Dashboard "Aktif Sinyaller" bridge-glance (executive overview).
// Read-only top-N teaser: symbol · direction · live-phase · live price (+24s Δ ≥sm).
// CP-PREMIUM-VISUAL-B: 'güven N' kaldırıldı — SQF forensic'te confidence_score
// sonuç-ayrıştırıcı değil (non-predictive); §03-K satır-grameri = sembol+yön+faz+fiyat.
// The FULL working table (density/filter/entry-SL-TP/quality/risk/Dock/detail) is
// Signal Center's responsibility — this only answers "aktif sinyal var mı, hangileri
// önemli?" in 3 seconds and bridges to /signals. Shares the app's native atoms
// (LiveStatusBadge · owned-numeral · livePrices); the shared SignalTable is untouched.
import { LiveStatusBadge } from '@/components/ui/LiveStatusBadge';
import { formatPrice, formatPercentage, cn } from '@/lib/utils';
import type { ApiSignal } from '@/lib/api';
import type { LivePrice } from '@/hooks/useLivePrices';

interface ActiveSignalGlanceProps {
  signals: ApiSignal[];
  livePrices: Record<string, LivePrice>;
  /** Route-only select (Dashboard never opens inline detail — see handleSignalSelect). */
  onSelect: (sig: ApiSignal) => void;
  loading?: boolean;
  /** Max rows shown (glance, not the full book). */
  limit?: number;
}

export function ActiveSignalGlance({
  signals,
  livePrices,
  onSelect,
  loading = false,
  limit = 4,
}: ActiveSignalGlanceProps) {
  if (loading) {
    // Hairline-iskelet (§03-K pv-yükleme): statik, sabit-boyut, --hl10 tek-aile.
    return (
      <div className="rounded-card border border-border-subtle divide-y divide-border-subtle overflow-hidden">
        {Array.from({ length: limit }).map((_, i) => (
          <div key={i} className="flex items-center gap-3 px-4 py-3">
            <div className="h-3 w-20 rounded bg-[var(--hl10)]" />
            <div className="h-3 w-14 rounded bg-[var(--hl10)] ml-auto" />
          </div>
        ))}
      </div>
    );
  }

  const rows = signals.slice(0, limit);

  return (
    <div className="rounded-card border border-border-subtle divide-y divide-border-subtle overflow-hidden">
      {rows.map((sig) => {
        const symbol = sig.asset?.symbol ?? '—';
        const isLong = String(sig.direction ?? '').toLowerCase().includes('bull');
        const lp = livePrices[symbol];
        return (
          <button
            key={sig.id}
            type="button"
            onClick={() => onSelect(sig)}
            className="focus-ring w-full flex items-center gap-3 px-4 py-3 text-left transition-colors duration-warm hover:bg-e-2/50"
          >
            <span className="flex items-center gap-2 min-w-0">
              <span className="text-sm font-display text-text-primary truncate">{symbol}</span>
              {/* twMerge özel text-micro'yu renk sınıflarıyla düşürebiliyor → düz birleştirme */}
              <span className={'text-micro font-medium uppercase ' + (isLong ? 'text-bullish' : 'text-bearish')}>
                {isLong ? 'LONG' : 'SHORT'}
              </span>
            </span>

            {sig.live_status && (
              <LiveStatusBadge
                status={sig.live_status}
                since={sig.live_status_since}
                reason={sig.status_reason}
              />
            )}

            <span className="ml-auto flex items-center gap-3 tabular-nums">
              {lp && (
                <span className="text-sm num text-text-primary">{formatPrice(lp.price)}</span>
              )}
              {lp && (
                <span className={cn(
                  'hidden sm:inline text-micro font-medium',
                  lp.changePct24h >= 0 ? 'text-bullish' : 'text-bearish',
                )}>
                  {formatPercentage(lp.changePct24h)}
                </span>
              )}
            </span>
          </button>
        );
      })}
    </div>
  );
}
