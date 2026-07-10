import React from 'react';
import { ShieldAlert } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { cn } from '@/lib/utils';

// Fixed low→high order; labels + colours are the canonical risk semantics.
const RISK = [
  { key: 'low', label: 'Düşük', cls: 'text-bullish', bar: 'bg-bullish' },
  { key: 'medium', label: 'Orta', cls: 'text-amber', bar: 'bg-amber' },
  { key: 'high', label: 'Yüksek', cls: 'text-bearish', bar: 'bg-bearish' },
] as const;

/**
 * "Risk Dağılımı" — how the active signals split across risk levels, so the
 * current book's risk posture reads in one glance. Client-derived from the
 * active-signal list — no endpoint. Static (no motion).
 */
export function RiskDagilimi({ counts }: { counts: Record<string, number> }) {
  const total = RISK.reduce((a, r) => a + (counts[r.key] ?? 0), 0);

  return (
    <GlassCard dense>
      <div className="flex items-center gap-1.5 text-micro text-text-muted uppercase font-medium mb-2">
        <ShieldAlert className="w-3.5 h-3.5 text-accent-primary" /> Risk Dağılımı
      </div>

      {/* Stacked risk bar — static */}
      <div className="h-1.5 rounded-full overflow-hidden flex bg-bg-tertiary mb-2">
        {RISK.map((r) => {
          const w = total ? ((counts[r.key] ?? 0) / total) * 100 : 0;
          return w > 0 ? <div key={r.key} className={cn('h-full', r.bar)} style={{ width: `${w}%` }} /> : null;
        })}
      </div>

      <div className="flex flex-wrap gap-x-3 gap-y-1 text-micro text-text-secondary">
        {RISK.map((r) => (
          <span key={r.key} className="inline-flex items-center gap-1">
            <span className={cn('tabular-nums font-medium', r.cls)}>{counts[r.key] ?? 0}</span>
            {r.label}
          </span>
        ))}
      </div>
    </GlassCard>
  );
}
