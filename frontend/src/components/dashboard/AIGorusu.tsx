import React from 'react';
import { Brain } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { cn } from '@/lib/utils';

interface AIGorusuProps {
  /** Active signals the AI is currently LONG on (bullish direction). */
  longCount: number;
  /** Active signals the AI is currently SHORT on (bearish direction). */
  shortCount: number;
  /** Mean confidence score (0-100) across active signals. */
  avgConfidence: number;
}

/**
 * "AI Görüşü" — the system's aggregate stance right now: net direction bias
 * (LONG vs SHORT of the active signals) + average conviction. Client-derived
 * from the active-signal list — no endpoint. Answers "AI ne düşünüyor?" in one
 * glance; deliberately terse. Static (no motion).
 */
export function AIGorusu({ longCount, shortCount, avgConfidence }: AIGorusuProps) {
  const total = longCount + shortCount;
  const longShare = total ? longCount / total : 0.5;

  const stance =
    longShare >= 0.6 ? { label: 'LONG eğilimli', cls: 'text-bullish' }
    : longShare <= 0.4 ? { label: 'SHORT eğilimli', cls: 'text-bearish' }
    : { label: 'Dengeli', cls: 'text-text-primary' };

  return (
    <GlassCard dense>
      <div className="flex items-center gap-1.5 text-micro text-text-muted uppercase font-medium mb-2">
        <Brain className="w-3.5 h-3.5 text-accent-primary" /> AI Görüşü
      </div>

      <div className={cn('font-display text-lg leading-tight', stance.cls)}>{stance.label}</div>

      <div className="text-micro text-text-secondary mt-1">
        <span className="text-bullish tabular-nums font-medium">{longCount}</span> LONG
        <span className="text-text-muted"> · </span>
        <span className="text-bearish tabular-nums font-medium">{shortCount}</span> SHORT
        <span className="text-text-muted"> · ort. güven </span>
        <span className="text-text-primary tabular-nums font-medium">%{avgConfidence}</span>
      </div>

      {/* LONG / SHORT split — static data bar */}
      <div className="mt-2 h-1.5 rounded-full overflow-hidden flex bg-bg-tertiary">
        {longCount > 0 && <div className="h-full bg-bullish" style={{ width: `${longShare * 100}%` }} />}
        {shortCount > 0 && <div className="h-full bg-bearish" style={{ width: `${(1 - longShare) * 100}%` }} />}
      </div>
    </GlassCard>
  );
}
