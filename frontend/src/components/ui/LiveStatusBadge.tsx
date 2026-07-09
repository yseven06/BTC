import React from 'react';
import { CheckCircle2, TrendingUp, Activity, AlertTriangle } from 'lucide-react';
import { cn, formatRelativeTime } from '@/lib/utils';

// ─── Live lifecycle vocabulary (single source of truth) ──────────────────────
// The backend lifecycle state-machine (active / approaching_tp / weakening /
// invalidating) is surfaced here as label + colour + icon. Consumed by both the
// signals-table phase badge AND the detail IntelligencePanel banner so the two
// never drift. Unknown / missing states fall back to `active`.
export const LIVE_STATUS_META: Record<
  string,
  { label: string; cls: string; bg: string; Icon: React.ElementType }
> = {
  active:         { label: 'Aktif',            cls: 'text-bullish',        bg: 'bg-bullish/10 border-bullish/30',               Icon: CheckCircle2 },
  approaching_tp: { label: "TP'ye Yaklaşıyor", cls: 'text-accent-primary', bg: 'bg-accent-primary/10 border-accent-primary/30', Icon: TrendingUp },
  weakening:      { label: 'Zayıflıyor',       cls: 'text-amber',          bg: 'bg-amber/10 border-amber/30',                   Icon: Activity },
  invalidating:   { label: 'Geçersizleşiyor',  cls: 'text-bearish',        bg: 'bg-bearish/10 border-bearish/30',               Icon: AlertTriangle },
};

interface LiveStatusBadgeProps {
  /** Backend live_status value: active | approaching_tp | weakening | invalidating. */
  status: string;
  /** ISO timestamp the current state was entered — surfaces "X önce" in the tooltip. */
  since?: string | null;
  /** Backend Turkish reason string — surfaces in the tooltip when present. */
  reason?: string | null;
  /** Render the phase icon before the label. Default false (compact text-only pill). */
  showIcon?: boolean;
  className?: string;
}

/**
 * Compact pill for a signal's live lifecycle phase. Colour + label carry the
 * phase at a glance; the tooltip adds entry-duration and the backend reason
 * when available. Purely presentational — no hooks, SSR-safe.
 */
export function LiveStatusBadge({
  status,
  since,
  reason,
  showIcon = false,
  className,
}: LiveStatusBadgeProps) {
  const meta = LIVE_STATUS_META[status] ?? LIVE_STATUS_META.active;
  const Icon = meta.Icon;

  const tip = [meta.label];
  if (since) tip.push(formatRelativeTime(since));
  if (reason) tip.push(reason);

  return (
    <span
      title={tip.join(' · ')}
      data-live-status={status}
      className={cn(
        'inline-flex items-center gap-1 px-2 py-0.5 rounded text-micro font-medium border whitespace-nowrap',
        meta.cls,
        meta.bg,
        className,
      )}
    >
      {showIcon && <Icon className="w-3 h-3 flex-shrink-0" />}
      {meta.label}
    </span>
  );
}
