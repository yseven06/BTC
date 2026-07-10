import type { SignalTransition } from './api';

// ─── Lifecycle journey (SL-b) ───────────────────────────────────────────────
// Turns the raw, oscillation-heavy transition log into a compact "journey":
//   • summary — a handful of aggregates for the always-visible collapsed row
//   • nodes   — a milestone-only timeline where repeat oscillations collapse
// Real data is noisy: ~74% of transitions are active↔weakening / active↔
// approaching_tp chatter (median 7, max 102 events per signal). The raw log is
// never shown — this module distils it. Pure + deterministic (no I/O, no Date
// at module scope) so it stays trivially testable.

export interface JourneySummary {
  bornAt: string;
  /** Count of real phase transitions (excludes birth + resolution). */
  phaseChanges: number;
  /** Best approach toward TP over the whole life, as a 0..1 fraction (null if never positive). */
  maxProgressToTp: number | null;
  /** Worst retrace toward SL over the whole life, as a 0..1 fraction (null if never positive). */
  maxRetraceToSl: number | null;
  resolved: boolean;
  /** win / loss / breakeven / … when resolved, else null. */
  outcome: string | null;
  /** Last live phase when still active, else null. */
  currentStatus: string | null;
}

export type JourneyNode =
  | { kind: 'event'; event: SignalTransition }
  | { kind: 'oscillation'; count: number; states: string[] };

export interface Journey {
  summary: JourneySummary;
  nodes: JourneyNode[];
  /** False when there is nothing worth showing (loading, error, or a lone birth event). */
  hasHistory: boolean;
}

/** Human offset from birth, e.g. "başlangıç" / "+18 dk" / "+3 sa" / "+2 gün". */
export function humanizeDelta(fromIso: string, toIso: string): string {
  const a = Date.parse(fromIso);
  const b = Date.parse(toIso);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return '';
  const secs = Math.max(0, Math.round((b - a) / 1000));
  const mins = Math.floor(secs / 60);
  if (mins < 1) return 'başlangıç';
  if (mins < 60) return `+${mins} dk`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `+${hours} sa`;
  return `+${Math.floor(hours / 24)} gün`;
}

export function buildJourney(events: readonly SignalTransition[]): Journey {
  const evs = (Array.isArray(events) ? events : []).filter(Boolean);

  // ── Summary aggregates ──
  let maxProgress: number | null = null;
  let maxRetrace: number | null = null;
  let phaseChanges = 0;
  for (const e of evs) {
    if (e.kind === 'transition') phaseChanges++;
    if (typeof e.progress_to_tp === 'number' && (maxProgress === null || e.progress_to_tp > maxProgress)) {
      maxProgress = e.progress_to_tp;
    }
    if (typeof e.retrace_to_sl === 'number' && (maxRetrace === null || e.retrace_to_sl > maxRetrace)) {
      maxRetrace = e.retrace_to_sl;
    }
  }
  const last = evs.length > 0 ? evs[evs.length - 1] : undefined;
  const resolved = last?.kind === 'resolution';
  const summary: JourneySummary = {
    bornAt: evs[0]?.created_at ?? '',
    phaseChanges,
    maxProgressToTp: maxProgress !== null && maxProgress > 0 ? maxProgress : null,
    maxRetraceToSl: maxRetrace !== null && maxRetrace > 0 ? maxRetrace : null,
    resolved,
    outcome: resolved ? (last?.outcome ?? null) : null,
    currentStatus: resolved ? null : (last?.to_status ?? null),
  };

  // ── Milestone extraction with oscillation collapse ──
  // A transition is a milestone when it is the birth, the resolution, or the
  // FIRST time the signal reaches a given phase. Everything after that (repeats
  // of already-seen phases = oscillation) collapses into a single chip.
  const nodes: JourneyNode[] = [];
  const seen = new Set<string>();
  let osc: SignalTransition[] = [];
  const flush = () => {
    if (osc.length === 0) return;
    const states: string[] = [];
    for (const e of osc) {
      for (const s of [e.from_status, e.to_status]) {
        if (s && !states.includes(s)) states.push(s);
      }
    }
    nodes.push({ kind: 'oscillation', count: osc.length, states });
    osc = [];
  };
  for (const e of evs) {
    const isMilestone = e.kind === 'birth' || e.kind === 'resolution' || !seen.has(e.to_status);
    if (isMilestone) {
      flush();
      nodes.push({ kind: 'event', event: e });
      seen.add(e.to_status);
    } else {
      osc.push(e);
    }
  }
  flush();

  return { summary, nodes, hasHistory: evs.length >= 2 };
}
