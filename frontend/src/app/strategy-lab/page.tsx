'use client';

import React, { useState, useEffect } from 'react';
import { FlaskConical, Clock, Calendar, TrendingUp, Shield } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { LockedOverlay } from '@/components/ui/LockedOverlay';
import { useTierLimits } from '@/hooks/useTierLimits';
import { fetchStrategyLab } from '@/lib/api';
import { cn } from '@/lib/utils';

interface HourData {
  hour: number; label: string; total: number;
  wins: number; losses: number; win_rate: number; avg_confidence: number;
}
interface DayData {
  day: number; label: string; total: number;
  wins: number; losses: number; win_rate: number; avg_confidence: number;
}
interface DirectionData { direction: string; total: number; wins: number; win_rate: number; avg_confidence: number; }
interface RiskData { risk_level: string; total: number; wins: number; win_rate: number; }
interface LabData {
  by_hour: HourData[]; by_day: DayData[];
  by_direction: DirectionData[]; by_risk: RiskData[];
  total_signals: number;
}

// ── Color helpers ─────────────────────────────────────────────────────────────
function heatColor(winRate: number, total: number): string {
  if (total === 0) return 'bg-bg-tertiary/40';
  if (winRate >= 70) return 'bg-bullish/80';
  if (winRate >= 55) return 'bg-bullish/40';
  if (winRate >= 45) return 'bg-yellow-500/40';
  if (winRate >= 30) return 'bg-orange-500/40';
  return 'bg-bearish/40';
}
function heatText(winRate: number, total: number): string {
  if (total === 0) return 'text-text-muted';
  if (winRate >= 55) return 'text-bullish';
  if (winRate >= 45) return 'text-yellow-400';
  return 'text-bearish';
}

// ── Hour Heatmap ──────────────────────────────────────────────────────────────
function HourHeatmap({ data }: { data: HourData[] }) {
  const [hovered, setHovered] = useState<HourData | null>(null);

  return (
    <div className="space-y-3">
      <div className="flex gap-1 flex-wrap">
        {data.map((h) => (
          <div
            key={h.hour}
            className={cn(
              'relative flex flex-col items-center justify-center rounded-lg cursor-default transition-all',
              'w-10 h-10 border border-border-subtle',
              heatColor(h.win_rate, h.total),
              hovered?.hour === h.hour && 'ring-1 ring-accent-primary scale-110'
            )}
            onMouseEnter={() => setHovered(h)}
            onMouseLeave={() => setHovered(null)}
          >
            <span className="text-[9px] font-bold text-text-muted">{h.hour.toString().padStart(2, '0')}</span>
            {h.total > 0 && (
              <span className={cn('text-[8px] font-mono font-bold', heatText(h.win_rate, h.total))}>
                {h.win_rate > 0 ? `${h.win_rate.toFixed(0)}%` : '—'}
              </span>
            )}
          </div>
        ))}
      </div>
      {hovered && (
        <div className="text-xs text-text-secondary bg-bg-secondary/80 border border-border-subtle rounded-xl px-4 py-2 inline-flex gap-4">
          <span className="font-bold text-text-primary">{hovered.label}</span>
          <span>Toplam: <b className="text-text-primary">{hovered.total}</b></span>
          <span>Kazanılan: <b className="text-bullish">{hovered.wins}</b></span>
          <span>Kazanma: <b className={heatText(hovered.win_rate, hovered.total)}>{hovered.win_rate}%</b></span>
          <span>Ort. Güven: <b className="text-accent-primary">{hovered.avg_confidence}%</b></span>
        </div>
      )}

      {/* Legend */}
      <div className="flex items-center gap-3 text-[10px] text-text-muted">
        <span>Düşük</span>
        {['bg-bearish/40','bg-orange-500/40','bg-yellow-500/40','bg-bullish/40','bg-bullish/80'].map((c, i) => (
          <span key={i} className={cn('w-5 h-3 rounded', c)} />
        ))}
        <span>Yüksek kazanma oranı</span>
      </div>
    </div>
  );
}

// ── Day Heatmap ───────────────────────────────────────────────────────────────
function DayHeatmap({ data }: { data: DayData[] }) {
  return (
    <div className="grid grid-cols-7 gap-2">
      {data.map((d) => (
        <div key={d.day} className={cn(
          'flex flex-col items-center gap-1 p-3 rounded-xl border border-border-subtle transition-all hover:scale-105',
          heatColor(d.win_rate, d.total)
        )}>
          <span className="text-[10px] font-bold text-text-muted">{d.label.slice(0, 3)}</span>
          <span className={cn('text-lg font-extrabold font-mono', heatText(d.win_rate, d.total))}>
            {d.total > 0 ? `${d.win_rate.toFixed(0)}%` : '—'}
          </span>
          <span className="text-[9px] text-text-muted">{d.total} sinyal</span>
        </div>
      ))}
    </div>
  );
}

// ── Direction Breakdown ───────────────────────────────────────────────────────
function DirectionBreakdown({ data }: { data: DirectionData[] }) {
  const total = data.reduce((s, d) => s + d.total, 0);
  const labels: Record<string, string> = { bullish: 'LONG', bearish: 'SHORT', neutral: 'NÖTR' };
  const colors: Record<string, string> = { bullish: 'bg-bullish', bearish: 'bg-bearish', neutral: 'bg-text-muted' };
  const textColors: Record<string, string> = { bullish: 'text-bullish', bearish: 'text-bearish', neutral: 'text-text-muted' };

  return (
    <div className="space-y-3">
      {data.map((d) => (
        <div key={d.direction} className="space-y-1">
          <div className="flex justify-between text-xs">
            <span className={cn('font-bold', textColors[d.direction])}>{labels[d.direction] ?? d.direction}</span>
            <div className="flex gap-3 text-text-muted">
              <span>{d.total} sinyal</span>
              <span className={cn('font-bold', heatText(d.win_rate, d.total))}>{d.win_rate}% kazanma</span>
              <span className="text-accent-primary">{d.avg_confidence}% güven</span>
            </div>
          </div>
          <div className="h-2 bg-bg-tertiary rounded-full overflow-hidden">
            <div
              className={cn('h-full rounded-full transition-all', colors[d.direction])}
              style={{ width: total > 0 ? `${d.total / total * 100}%` : '0%', opacity: 0.7 }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Risk Breakdown ────────────────────────────────────────────────────────────
function RiskBreakdown({ data }: { data: RiskData[] }) {
  const order = ['low', 'medium', 'high', 'very_high'];
  const labels: Record<string, string> = { low: 'Düşük', medium: 'Orta', high: 'Yüksek', very_high: 'Çok Yüksek' };
  const colors: Record<string, string> = { low: 'text-bullish', medium: 'text-yellow-400', high: 'text-orange-400', very_high: 'text-bearish' };
  const sorted = [...data].sort((a, b) => order.indexOf(a.risk_level) - order.indexOf(b.risk_level));

  return (
    <div className="grid grid-cols-2 gap-3">
      {sorted.map((r) => (
        <div key={r.risk_level} className="bg-bg-secondary/50 rounded-xl p-3 border border-border-subtle">
          <p className={cn('text-xs font-bold mb-1', colors[r.risk_level])}>{labels[r.risk_level] ?? r.risk_level}</p>
          <p className="text-2xl font-extrabold font-mono text-text-primary">{r.total}</p>
          <p className="text-[10px] text-text-muted mt-1">sinyal · {r.win_rate}% kazanma</p>
        </div>
      ))}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function StrategyLabPage() {
  const limits = useTierLimits();
  const [data, setData]       = useState<LabData | null>(null);
  const [loading, setLoading] = useState(true);
  const isLocked = !limits.loading && !limits.can_view_strategy_lab;

  useEffect(() => {
    fetchStrategyLab()
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-extrabold text-text-primary flex items-center gap-2">
          <FlaskConical className="w-6 h-6 text-accent-primary" /> Strategy Lab
        </h1>
        <p className="text-sm text-text-secondary mt-1">
          Saat, gün ve volatilite bazlı performans ısı haritaları
        </p>
      </div>

      {loading && (
        <div className="flex justify-center py-20">
          <div className="w-8 h-8 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      {!loading && data && (
        <div className="space-y-5 relative">
          {isLocked && (
            <LockedOverlay
              title="Strategy Lab — Pro Özellik"
              description="Saat ve gün bazlı performans ısı haritalarına erişim için Pro plana yükselt."
            />
          )}
          {/* Summary stat */}
          <div className="flex gap-3">
            <GlassCard className="flex-1 text-center py-4">
              <p className="text-3xl font-extrabold font-mono text-text-primary">{data.total_signals}</p>
              <p className="text-xs text-text-muted mt-1">Toplam Sinyal</p>
            </GlassCard>
            <GlassCard className="flex-1 text-center py-4">
              <p className="text-3xl font-extrabold font-mono text-bullish">
                {data.by_direction.find(d => d.direction === 'bullish')?.win_rate ?? 0}%
              </p>
              <p className="text-xs text-text-muted mt-1">LONG Kazanma</p>
            </GlassCard>
            <GlassCard className="flex-1 text-center py-4">
              <p className="text-3xl font-extrabold font-mono text-bearish">
                {data.by_direction.find(d => d.direction === 'bearish')?.win_rate ?? 0}%
              </p>
              <p className="text-xs text-text-muted mt-1">SHORT Kazanma</p>
            </GlassCard>
          </div>

          {/* Hour heatmap */}
          <GlassCard>
            <h2 className="text-base font-bold text-text-primary flex items-center gap-2 mb-4">
              <Clock className="w-4 h-4 text-accent-primary" /> Saate Göre Performans
            </h2>
            <HourHeatmap data={data.by_hour} />
          </GlassCard>

          {/* Day heatmap */}
          <GlassCard>
            <h2 className="text-base font-bold text-text-primary flex items-center gap-2 mb-4">
              <Calendar className="w-4 h-4 text-accent-primary" /> Güne Göre Performans
            </h2>
            <DayHeatmap data={data.by_day} />
          </GlassCard>

          {/* Bottom 2-col */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <GlassCard>
              <h2 className="text-base font-bold text-text-primary flex items-center gap-2 mb-4">
                <TrendingUp className="w-4 h-4 text-accent-primary" /> Yön Analizi
              </h2>
              {data.by_direction.length > 0
                ? <DirectionBreakdown data={data.by_direction} />
                : <p className="text-xs text-text-muted text-center py-6">Henüz kapanmış işlem yok</p>
              }
            </GlassCard>

            <GlassCard>
              <h2 className="text-base font-bold text-text-primary flex items-center gap-2 mb-4">
                <Shield className="w-4 h-4 text-accent-primary" /> Risk Seviyesi
              </h2>
              {data.by_risk.length > 0
                ? <RiskBreakdown data={data.by_risk} />
                : <p className="text-xs text-text-muted text-center py-6">Henüz kapanmış işlem yok</p>
              }
            </GlassCard>
          </div>

          {data.total_signals === 0 && (
            <GlassCard>
              <p className="text-sm text-text-muted text-center py-8">
                Henüz kapanmış işlem verisi yok. Sinyaller kapandıkça ısı haritaları dolacak.
              </p>
            </GlassCard>
          )}
        </div>
      )}
    </div>
  );
}
