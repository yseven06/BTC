import Link from 'next/link';
import { Info } from 'lucide-react';
import {
  DISCLAIMER_SHORT,
  DISCLAIMER_FULL,
  DISCLAIMER_BACKTEST_EXTRA,
  DISCLAIMER_LINK,
} from '@/lib/legal/disclaimer';

/**
 * The ONE disclaimer component used everywhere (footer, signal detail, pricing,
 * backtest, strategy lab, future Auto Trade). All wording comes from
 * `@/lib/legal/disclaimer` — this component only handles placement/styling, so a
 * single text edit propagates across the whole app.
 *
 * Variants:
 *  - `footer`  : muted one-liner for the global footer.
 *  - `compact` : muted one-liner for tight spaces.
 *  - `inline`  : bordered note box for signal/decision surfaces.
 *  - `backtest`: like `inline` + the hypothetical-results sentence.
 */
export type DisclaimerVariant = 'footer' | 'compact' | 'inline' | 'backtest';

export function InvestmentDisclaimer({
  variant = 'inline',
  className = '',
}: {
  variant?: DisclaimerVariant;
  className?: string;
}) {
  const body =
    variant === 'backtest'
      ? `${DISCLAIMER_FULL} ${DISCLAIMER_BACKTEST_EXTRA}`
      : variant === 'inline'
        ? DISCLAIMER_FULL
        : DISCLAIMER_SHORT;

  if (variant === 'footer' || variant === 'compact') {
    return (
      <p className={`text-xs leading-relaxed text-text-muted ${className}`}>
        {body}{' '}
        <Link href={DISCLAIMER_LINK} className="text-accent-primary hover:underline">
          Risk Bildirimi
        </Link>
      </p>
    );
  }

  return (
    <aside
      role="note"
      className={`flex gap-2 rounded-lg border border-white/10 bg-bg-secondary/60 px-3 py-2 text-xs leading-relaxed text-text-muted ${className}`}
    >
      <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-text-muted" aria-hidden />
      <span>
        {body}{' '}
        <Link href={DISCLAIMER_LINK} className="text-accent-primary hover:underline">
          Ayrıntılı bilgi
        </Link>
      </span>
    </aside>
  );
}
