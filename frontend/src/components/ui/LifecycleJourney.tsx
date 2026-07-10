'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { History, ChevronDown, ChevronUp, Repeat } from 'lucide-react';
import { cn } from '@/lib/utils';
import { fetchSignalTransitions, type SignalTransition } from '@/lib/api';
import { buildJourney, humanizeDelta, type JourneyNode } from '@/lib/lifecycle-journey';
import { LIVE_STATUS_META } from './LiveStatusBadge';

// Resolution rows carry to_status="closed" (NOT a live phase) — render them from
// the outcome instead of LIVE_STATUS_META so a "closed" event never falls back
// to "Aktif".
const OUTCOME_META: Record<string, { label: string; text: string; dot: string }> = {
  win:        { label: 'Kazandı',   text: 'text-bullish',    dot: 'bg-bullish' },
  loss:       { label: 'Patladı',   text: 'text-bearish',    dot: 'bg-bearish' },
  breakeven:  { label: 'Berabere',  text: 'text-amber',      dot: 'bg-amber' },
  expired:    { label: 'Süre doldu', text: 'text-text-muted', dot: 'bg-text-muted' },
  invalidated:{ label: 'İptal',     text: 'text-text-muted', dot: 'bg-text-muted' },
};

// Solid dot colour per live phase (LIVE_STATUS_META carries the /10 tint used for
// pills; the timeline wants the solid token).
const PHASE_DOT: Record<string, string> = {
  active: 'bg-bullish',
  approaching_tp: 'bg-accent-primary',
  weakening: 'bg-amber',
  invalidating: 'bg-bearish',
};

const phaseLabel = (s: string) => LIVE_STATUS_META[s]?.label ?? s;
const phaseText = (s: string) => LIVE_STATUS_META[s]?.cls ?? 'text-text-secondary';
const asPct = (v: number | null) => (v == null ? null : `%${Math.round(v * 100)}`);

function oscillationLabel(states: string[], count: number): string {
  const named = states.filter((s) => LIVE_STATUS_META[s]).map((s) => LIVE_STATUS_META[s].label);
  if (named.length === 2) return `${count}× ${named[0]}↔${named[1]} salınımı`;
  return `${count} ara faz değişimi`;
}

function TimelineRow({ node, bornAt, last }: { node: JourneyNode; bornAt: string; last: boolean }) {
  // ── Collapsed oscillation chip ──
  if (node.kind === 'oscillation') {
    return (
      <li className="flex gap-3">
        <div className="flex flex-col items-center flex-shrink-0">
          <Repeat className="w-3 h-3 text-text-muted mt-1" />
          {!last && <span className="w-px flex-1 bg-border-subtle mt-1" />}
        </div>
        <div className="min-w-0 pb-3">
          <span className="text-micro text-text-muted italic">
            {oscillationLabel(node.states, node.count)}
          </span>
        </div>
      </li>
    );
  }

  // ── Milestone event ──
  const e = node.event;
  const isResolution = e.kind === 'resolution';
  const oc = isResolution ? OUTCOME_META[e.outcome ?? ''] : undefined;

  const dot = isResolution ? (oc?.dot ?? 'bg-text-muted') : (PHASE_DOT[e.to_status] ?? 'bg-text-muted');
  const textCls = isResolution ? (oc?.text ?? 'text-text-secondary') : phaseText(e.to_status);
  const label = isResolution
    ? `Sonuç: ${oc?.label ?? 'Kapandı'}`
    : e.kind === 'birth'
      ? `Doğuş — ${phaseLabel(e.to_status)}`
      : phaseLabel(e.to_status);

  const detail: string[] = [];
  if (typeof e.progress_to_tp === 'number' && e.progress_to_tp > 0) detail.push(`TP %${Math.round(e.progress_to_tp * 100)}`);
  if (typeof e.retrace_to_sl === 'number' && e.retrace_to_sl > 0) detail.push(`SL %${Math.round(e.retrace_to_sl * 100)}`);

  return (
    <li className="flex gap-3">
      <div className="flex flex-col items-center flex-shrink-0">
        <span className={cn('w-2 h-2 rounded-full mt-1.5', dot)} />
        {!last && <span className="w-px flex-1 bg-border-subtle mt-1" />}
      </div>
      <div className="min-w-0 flex-1 pb-3">
        <div className="flex items-baseline justify-between gap-2">
          <span className={cn('text-xs font-medium', textCls)}>{label}</span>
          <span className="text-micro text-text-muted flex-shrink-0">{humanizeDelta(bornAt, e.created_at)}</span>
        </div>
        {e.reason && <p className="text-micro text-text-secondary mt-0.5 break-words">{e.reason}</p>}
        {detail.length > 0 && <p className="text-micro text-text-muted mt-0.5">{detail.join(' · ')}</p>}
      </div>
    </li>
  );
}

interface Props {
  signalId: string;
}

/**
 * "Bu sinyal buraya nasıl geldi?" — collapsed journey summary that expands into a
 * milestone-only vertical timeline. Oscillation noise is collapsed; the raw event
 * log is never shown. Static by design — motion/glow is deferred to Premium.
 */
export function LifecycleJourney({ signalId }: Props) {
  const [events, setEvents] = useState<SignalTransition[] | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchSignalTransitions(signalId)
      .then((d) => { if (!cancelled) setEvents(d); })
      .catch(() => { if (!cancelled) setEvents([]); });
    return () => { cancelled = true; };
  }, [signalId]);

  const journey = useMemo(() => (events ? buildJourney(events) : null), [events]);

  // Supplementary panel: stay invisible until there's a real journey to tell
  // (loading, fetch failure, or a lone birth event → render nothing).
  if (!journey || !journey.hasHistory) return null;

  const { summary, nodes } = journey;
  const bestTp = asPct(summary.maxProgressToTp);
  const worstSl = asPct(summary.maxRetraceToSl);

  return (
    <div className="mb-4 rounded-xl border border-border-subtle bg-bg-tertiary/30 overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left"
        aria-expanded={expanded}
      >
        <History className="w-3.5 h-3.5 text-text-muted flex-shrink-0" />
        <span className="text-micro text-text-secondary min-w-0 flex-1">
          <span className="text-text-primary font-medium">Yolculuk</span>
          {` · ${summary.phaseChanges} faz değişimi`}
          {bestTp && ` · en iyi TP ${bestTp}`}
          {worstSl && ` · SL ${worstSl}`}
        </span>
        <span className="text-micro text-text-muted flex items-center gap-0.5 flex-shrink-0">
          {expanded ? 'Gizle' : 'Geçmişi gör'}
          {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </span>
      </button>

      {expanded && (
        <ol className="px-3 pt-1 pb-1 border-t border-border-subtle">
          {nodes.map((node, i) => (
            <TimelineRow key={i} node={node} bornAt={summary.bornAt} last={i === nodes.length - 1} />
          ))}
        </ol>
      )}
    </div>
  );
}
