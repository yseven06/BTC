import Link from 'next/link';
import { Info, AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  DISCLAIMER_SHORT,
  DISCLAIMER_FULL,
  DISCLAIMER_BACKTEST_EXTRA,
  DISCLAIMER_AUTOTRADE_EXTRA,
  DISCLAIMER_LINK,
} from '@/lib/legal/disclaimer';

/**
 * The ONE disclaimer component used everywhere (footer, signal detail, pricing,
 * backtest/performance, strategy lab, future Auto Trade). All wording comes from
 * `@/lib/legal/disclaimer` — this component only controls placement/visual
 * intensity, so a single text edit propagates across the whole app and the
 * variants never drift apart.
 *
 * Visibility scales with the page's risk level:
 *  - `footer` / `compact` : muted one-liner (low-risk / chrome).
 *  - `inline`             : bordered note box for decision surfaces
 *                           (signal detail, pricing).
 *  - `backtest`           : `inline` + hypothetical-results sentence
 *                           (backtest, performance, strategy lab).
 *  - `warning`            : strongest, amber alert — for (future) Auto Trade.
 */
export type DisclaimerVariant = 'footer' | 'compact' | 'inline' | 'backtest' | 'warning';

export function InvestmentDisclaimer({
  variant = 'inline',
  className = '',
}: {
  variant?: DisclaimerVariant;
  className?: string;
}) {
  const body =
    variant === 'warning'
      ? `${DISCLAIMER_FULL} ${DISCLAIMER_AUTOTRADE_EXTRA}`
      : variant === 'backtest'
        ? `${DISCLAIMER_FULL} ${DISCLAIMER_BACKTEST_EXTRA}`
        : variant === 'inline'
          ? DISCLAIMER_FULL
          : DISCLAIMER_SHORT;

  // Low-intensity: plain muted line (footer / compact).
  if (variant === 'footer' || variant === 'compact') {
    return (
      <p className={cn('text-xs leading-relaxed text-text-muted', className)}>
        {body}{' '}
        <Link href={DISCLAIMER_LINK} className="text-accent-primary hover:underline">
          Risk Bildirimi
        </Link>
      </p>
    );
  }

  // Bordered note (inline / backtest) or strong amber alert (warning).
  const isWarning = variant === 'warning';
  const Icon = isWarning ? AlertTriangle : Info;

  return (
    <aside
      role={isWarning ? 'alert' : 'note'}
      className={cn(
        'flex gap-2 rounded-lg border px-3 py-2 text-xs leading-relaxed',
        isWarning
          ? 'border-yellow-500/40 bg-yellow-500/10 text-yellow-100'
          : 'border-white/10 bg-bg-secondary/60 text-text-muted',
        className,
      )}
    >
      <Icon
        className={cn('mt-0.5 h-3.5 w-3.5 shrink-0', isWarning ? 'text-yellow-400' : 'text-text-muted')}
        aria-hidden
      />
      <span>
        {body}{' '}
        <Link href={DISCLAIMER_LINK} className="text-accent-primary hover:underline">
          Ayrıntılı bilgi
        </Link>
      </span>
    </aside>
  );
}
