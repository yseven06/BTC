'use client';

import React, { useEffect, useState } from 'react';
import { CheckCircle2, TrendingUp, Activity, AlertTriangle, Clock, HelpCircle } from 'lucide-react';
import { cn, formatRelativeTime } from '@/lib/utils';

export type StatusMeta = { label: string; cls: string; bg: string; Icon: React.ElementType };

// ─── Live lifecycle vocabulary (single source of truth) ──────────────────────
// The backend lifecycle state-machine (waiting_entry / active / approaching_tp /
// weakening / invalidating) is surfaced here as label + colour + icon. Consumed
// by the signals-table phase badge, the detail IntelligencePanel banner, the
// lifecycle timeline and the landing proof strip, so the surfaces never drift.
//
// `waiting_entry` is the published-but-not-yet-filled phase (CP-ENTRY-ACTIVATION
// -GATE). It is deliberately NEUTRAL, not green: nothing has been entered, so
// showing the bullish "Aktif" treatment asserted a position the user never had.
// The muted token trio is the one SignalTable already uses for its expired chip
// — no new visual language.
export const LIVE_STATUS_META: Record<string, StatusMeta> = {
  waiting_entry:  { label: 'Giriş Bekleniyor', cls: 'text-text-secondary', bg: 'bg-text-muted/15 border-text-muted/30',         Icon: Clock },
  active:         { label: 'Aktif',            cls: 'text-bullish',        bg: 'bg-bullish/10 border-bullish/30',               Icon: CheckCircle2 },
  approaching_tp: { label: "TP'ye Yaklaşıyor", cls: 'text-accent-primary', bg: 'bg-accent-primary/10 border-accent-primary/30', Icon: TrendingUp },
  weakening:      { label: 'Zayıflıyor',       cls: 'text-amber',          bg: 'bg-amber/10 border-amber/30',                   Icon: Activity },
  invalidating:   { label: 'Geçersizleşiyor',  cls: 'text-bearish',        bg: 'bg-bearish/10 border-bearish/30',               Icon: AlertTriangle },
};

// Unknown / missing phase. Every surface used to fall back to `active`, which is
// how a brand-new backend status (waiting_entry) rendered as a green "Aktif"
// across the product without a single error. A fallback must never claim a
// state; it must admit it does not know one.
export const UNKNOWN_STATUS_META: StatusMeta = {
  label: 'Durum bilinmiyor', cls: 'text-text-muted', bg: 'bg-text-muted/15 border-text-muted/30', Icon: HelpCircle,
};

/** Resolve a backend live_status to its presentation. The ONLY safe lookup —
 *  raw `LIVE_STATUS_META[x]` returns undefined for unknown values, and every
 *  caller that then reached for `.active` or printed the raw string is what
 *  this replaces. */
export function statusMeta(status?: string | null): StatusMeta {
  return (status && LIVE_STATUS_META[status]) || UNKNOWN_STATUS_META;
}

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

// Shared pill recipe — the current phase and the crossfading previous phase are
// byte-identical except for their status-driven colour classes.
const PILL = 'inline-flex items-center gap-1 px-2 py-0.5 rounded text-micro font-medium border whitespace-nowrap';

// Teardown safety net (see below). Chosen as --dur-state (180ms) + ~80ms margin
// rather than read from the CSS variable at runtime: reliably parsing its s/ms
// unit on every mount would add complexity for a value that only has to outlast
// the 180ms transition so the overlay is torn down when transitionend cannot
// fire (display:none mirror row / backgrounded tab).
const FADE_FALLBACK_MS = 260;

function PillBody({ meta, showIcon }: { meta: (typeof LIVE_STATUS_META)[string]; showIcon: boolean }) {
  const Icon = meta.Icon;
  return (
    <>
      {showIcon && <Icon className="w-3 h-3 flex-shrink-0" />}
      {meta.label}
    </>
  );
}

/**
 * Compact pill for a signal's live lifecycle phase. Colour + label carry the
 * phase at a glance; the tooltip adds entry-duration and the backend reason
 * when available.
 *
 * SL-b state crossfade: when the SAME mounted badge receives a *different*
 * live_status (e.g. active → approaching_tp on an in-place refetch/poll), the
 * two phases crossfade — the outgoing phase fades opacity 1→0 while the incoming
 * phase fades 0→1, both on one synchronised rAF frame. The previous phase is
 * derived during render (no effect → no new-value flash) and only for a genuine
 * value change; first mount, parent re-renders and repeated values never
 * animate. Purely opacity (property-explicit); no layout/transform/keyframe.
 * Reduced-motion collapses the fade to ~instant via the global
 * prefers-reduced-motion layer, so no information is lost.
 */
export function LiveStatusBadge({
  status,
  since,
  reason,
  showIcon = false,
  className,
}: LiveStatusBadgeProps) {
  // Two-layer symmetric crossfade. `current`/`outgoing` carry a generation id
  // used as the React key: the outgoing phase reuses the *previous current's*
  // element (already painted at opacity 1 → fades out with no jump), while the
  // incoming current mounts under a fresh key at opacity 0 → fades in. `entered`
  // flips both layers on the same rAF frame so the two fades stay in lock-step.
  // `current` initialises to `status`, so first mount / hydration is a no-op.
  const [current, setCurrent] = useState({ status, gen: 0 });
  const [outgoing, setOutgoing] = useState<{ status: string; gen: number } | null>(null);
  const [entered, setEntered] = useState(true);

  if (status !== current.status) {
    setOutgoing(current);                          // old phase keeps its element/key (opacity 1)
    setCurrent({ status, gen: current.gen + 1 });  // new phase, fresh key → mounts at opacity 0
    setEntered(false);                             // pre-transition: incoming 0, outgoing 1
  }

  // Flip both layers one frame after they paint in their pre-transition state,
  // so the property-explicit opacity transition runs (a synchronous flip would
  // skip it). entered stays true on first mount / repeat values → no animation.
  useEffect(() => {
    if (entered) return;
    const raf = requestAnimationFrame(() => setEntered(true));
    return () => cancelAnimationFrame(raf);
  }, [entered]);

  // Teardown. transitionend (below) is the fast path, but a display:none mirror
  // row — SignalTable renders the desktop table AND the mobile cards, one always
  // hidden — or a backgrounded tab never fires it, which would strand the
  // overlay. This timer guarantees removal; it is re-armed for every new
  // outgoing phase (older timer cancelled by the cleanup) and cleared on
  // unmount, so a stale timer can never tear down a newer transition and there
  // is no state update after unmount.
  useEffect(() => {
    if (!outgoing) return;
    const t = setTimeout(() => setOutgoing(null), FADE_FALLBACK_MS);
    return () => clearTimeout(t);
  }, [outgoing]);

  const meta = statusMeta(current.status);
  const outMeta = outgoing ? statusMeta(outgoing.status) : null;

  const tip = [meta.label];
  if (since) tip.push(formatRelativeTime(since));
  if (reason) tip.push(reason);

  return (
    <span className="inline-grid justify-items-start align-middle">
      {/* Outgoing phase — decorative, hidden from the a11y tree so the accessible
          name stays single. Reuses the previous current's element (opacity 1)
          and fades to 0; removed once its opacity transition reaches 0. Both
          layers share grid cell 1/1; justify-items-start keeps each sized to its
          own content (no stretch), so steady-state width equals the old single
          span and no neighbouring column geometry shifts. */}
      {outgoing && outMeta && (
        <span
          key={outgoing.gen}
          aria-hidden
          onTransitionEnd={(e) => {
            if (
              e.propertyName === 'opacity' &&
              parseFloat(getComputedStyle(e.currentTarget).opacity) === 0
            ) {
              setOutgoing(null);
            }
          }}
          className={cn(
            PILL,
            'col-start-1 row-start-1 transition-opacity duration-[var(--dur-state)] ease-signal',
            entered ? 'opacity-0' : 'opacity-100',
            outMeta.cls,
            outMeta.bg,
            className,
          )}
        >
          <PillBody meta={outMeta} showIcon={showIcon} />
        </span>
      )}

      {/* Current phase — the only accessible layer; mounts at opacity 0 on a real
          change (fresh key) and fades in to 1. First mount / steady state render
          at opacity 1 with no transition to run. */}
      <span
        key={current.gen}
        title={tip.join(' · ')}
        data-live-status={current.status}
        className={cn(
          PILL,
          'col-start-1 row-start-1 transition-opacity duration-[var(--dur-state)] ease-signal',
          entered ? 'opacity-100' : 'opacity-0',
          meta.cls,
          meta.bg,
          className,
        )}
      >
        <PillBody meta={meta} showIcon={showIcon} />
      </span>
    </span>
  );
}
