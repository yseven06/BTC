import React from 'react';
import { cn } from '@/lib/utils';
import { LIVE_STATUS_META } from '@/components/ui/LiveStatusBadge';

// Solid dot per phase (LIVE_STATUS_META carries the /10 pill tint; the census
// wants the solid token). Single source for labels stays LIVE_STATUS_META.
const DOT: Record<string, string> = {
  active: 'bg-bullish',
  approaching_tp: 'bg-accent-primary',
  weakening: 'bg-amber',
  invalidating: 'bg-bearish',
};

// Attention-first: the phases that may need action lead the glance.
const ORDER = ['approaching_tp', 'weakening', 'invalidating', 'active'];

/**
 * Lifecycle-health census — a compact phase breakdown of the active signals
 * ("N zayıflıyor · M TP'ye yaklaşıyor …"). Client-derived from the list the
 * dashboard already fetches — no endpoint. Only non-zero phases render; nothing
 * when there is no data. Static (no motion).
 */
export function LifecycleHealth({ counts }: { counts: Record<string, number> }) {
  const shown = ORDER.filter((k) => (counts[k] ?? 0) > 0);
  if (shown.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mb-3 text-micro text-text-secondary">
      {shown.map((k) => (
        <span key={k} className="inline-flex items-center gap-1.5">
          <span className={cn('w-1.5 h-1.5 rounded-full flex-shrink-0', DOT[k] ?? 'bg-text-muted')} />
          <span className="tabular-nums text-text-primary font-medium">{counts[k]}</span>
          <span>{LIVE_STATUS_META[k]?.label ?? k}</span>
        </span>
      ))}
    </div>
  );
}
