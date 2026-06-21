'use client';

import React, { useState, useEffect } from 'react';
import { BarChart3, TrendingUp, TrendingDown, Search } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { CoinIcon } from '@/components/ui/CoinIcon';
import { LockedOverlay } from '@/components/ui/LockedOverlay';
import { useTierLimits } from '@/hooks/useTierLimits';
import { fetchSymbolAnalysis } from '@/lib/api';
import { cn } from '@/lib/utils';

interface SymbolData {
  symbol: string; name: string; asset_type: string;
  total: number; wins: number; losses: number; breakeven: number; active: number;
  win_rate: number; avg_confidence: number; quality_score: number;
  directions: Record<string, number>;
  htf_types: Record<string, number>;
}
interface AnalysisData { symbols: SymbolData[]; total_symbols: number; }

function QualityBar({ score }: { score: number }) {
  const safeScore = Number.isFinite(Number(score)) ? Number(score) : 0;
  const color = safeScore >= 8 ? 'bg-bullish' : safeScore >= 6 ? 'bg-yellow-400' : safeScore >= 4 ? 'bg-orange-400' : 'bg-bearish';
  const text  = safeScore >= 8 ? 'text-bullish' : safeScore >= 6 ? 'text-yellow-400' : safeScore >= 4 ? 'text-orange-400' : 'text-bearish';
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-bg-tertiary rounded-full overflow-hidden">
        <div className={cn('h-full rounded-full', color)} style={{ width: `${safeScore * 10}%` }} />
      </div>
      <span className={cn('text-xs font-bold font-mono', text)}>{safeScore.toFixed(1)}/10</span>
    </div>
  );
}

function HtfSplit({ types }: { types: Record<string, number> }) {
  const ob    = types['OB'] ?? 0;
  const fvg   = types['FVG'] ?? 0;
  const total = ob + fvg || 1;
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-bg-tertiary rounded-full overflow-hidden flex">
        <div className="h-full bg-accent-primary/70 rounded-l-full" style={{ width: `${ob / total * 100}%` }} />
        <div className="h-full bg-purple-400/70 rounded-r-full" style={{ width: `${fvg / total * 100}%` }} />
      </div>
      <div className="flex gap-2 text-[10px] whitespace-nowrap">
        <span className="text-accent-primary font-bold">OB {ob}</span>
        <span className="text-purple-400 font-bold">FVG {fvg}</span>
      </div>
    </div>
  );
}

function DirectionSplit({ directions, total }: { directions: Record<string, number>; total: number }) {
  const bull = directions['bullish'] ?? 0;
  const bear = directions['bearish'] ?? 0;
  const pct  = total > 0 ? Math.round(bull / total * 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <TrendingUp className="w-3 h-3 text-bullish flex-shrink-0" />
      <div className="flex-1 h-1.5 bg-bearish/30 rounded-full overflow-hidden">
        <div className="h-full bg-bullish/70 rounded-full" style={{ width: `${pct}%` }} />
      </div>
      <TrendingDown className="w-3 h-3 text-bearish flex-shrink-0" />
      <span className="text-[10px] text-text-muted whitespace-nowrap">{bull}L / {bear}S</span>
    </div>
  );
}

export default function SymbolAnalysisPage() {
  const limits = useTierLimits();
  const [data, setData]     = useState<AnalysisData | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery]   = useState('');
  const [sort, setSort]     = useState<'total' | 'win_rate' | 'quality_score'>('total');
  const isLocked = !limits.loading && !limits.can_view_symbol_analysis;

  useEffect(() => {
    fetchSymbolAnalysis()
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const filtered = (data?.symbols ?? [])
    .filter((s) => s.symbol.toLowerCase().includes(query.toLowerCase()) || s.name.toLowerCase().includes(query.toLowerCase()))
    .sort((a, b) => b[sort] - a[sort]);

  const totalWins  = filtered.reduce((s, x) => s + x.wins, 0);
  const totalSigs  = filtered.reduce((s, x) => s + x.total, 0);
  const totalLoss  = filtered.reduce((s, x) => s + x.losses, 0);
  const globalWR   = totalSigs > 0 ? ((totalWins / (totalWins + totalLoss || 1)) * 100).toFixed(1) : '—';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-extrabold text-text-primary flex items-center gap-2">
          <BarChart3 className="w-6 h-6 text-accent-primary" /> Sembol Analizi
        </h1>
        <p className="text-sm text-text-secondary mt-1">
          Çift bazlı kazanma oranı · OB vs FVG karşılaştırma · kalite skoru
        </p>
      </div>

      <div className="relative space-y-6">
        {isLocked && (
          <LockedOverlay
            title="Sembol Analizi — Pro Özellik"
            description="Coin başına kazanma oranları ve OB vs FVG karşılaştırma için Pro plana yükselt."
          />
        )}
      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-3">
        <GlassCard className="text-center py-4">
          <p className="text-3xl font-extrabold font-mono text-text-primary">{data?.total_symbols ?? '—'}</p>
          <p className="text-xs text-text-muted mt-1">İzlenen Sembol</p>
        </GlassCard>
        <GlassCard className="text-center py-4">
          <p className="text-3xl font-extrabold font-mono text-text-primary">{totalSigs}</p>
          <p className="text-xs text-text-muted mt-1">Toplam Sinyal</p>
        </GlassCard>
        <GlassCard className="text-center py-4">
          <p className="text-3xl font-extrabold font-mono text-bullish">{globalWR}%</p>
          <p className="text-xs text-text-muted mt-1">Genel Kazanma Oranı</p>
        </GlassCard>
      </div>

      {/* Controls */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-muted" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Sembol ara..."
            className="w-full pl-9 pr-4 py-2 text-sm bg-bg-secondary border border-border-subtle rounded-xl text-text-primary placeholder-text-muted outline-none focus:border-accent-primary/40 transition-colors"
          />
        </div>
        <div className="flex gap-1 p-1 bg-bg-secondary border border-border-subtle rounded-xl">
          {(['total', 'win_rate', 'quality_score'] as const).map((s) => (
            <button
              key={s}
              onClick={() => setSort(s)}
              className={cn(
                'px-3 py-1 text-xs font-semibold rounded-lg transition-all',
                sort === s ? 'bg-accent-primary text-white' : 'text-text-muted hover:text-text-primary'
              )}
            >
              {s === 'total' ? 'Sinyal' : s === 'win_rate' ? 'Kazanma %' : 'Kalite'}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="glass-panel border border-border-subtle rounded-2xl overflow-hidden">
        {/* Head */}
        <div className="grid grid-cols-[2fr_1fr_1.5fr_1.5fr_1.5fr_1.5fr] gap-4 px-5 py-3 border-b border-border-subtle bg-bg-secondary/30">
          {['SEMBOL', 'TOPLAM', 'KALİTE SKORU', 'KAZANMA ORANI', 'HTF TİPİ (OB/FVG)', 'YÖN DAĞILIMI'].map((h) => (
            <span key={h} className="text-[10px] font-bold text-text-muted uppercase tracking-wider">{h}</span>
          ))}
        </div>

        {loading && (
          <div className="flex justify-center py-16">
            <div className="w-7 h-7 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {!loading && filtered.length === 0 && (
          <p className="text-center text-text-muted text-sm py-16">
            {query ? 'Eşleşen sembol yok.' : 'Henüz sinyal verisi yok.'}
          </p>
        )}

        <div className="divide-y divide-border-subtle">
          {filtered.map((sym) => {
            const resolved = sym.wins + sym.losses + sym.breakeven;
            const wrColor  = sym.win_rate >= 60 ? 'text-bullish' : sym.win_rate >= 45 ? 'text-yellow-400' : 'text-bearish';

            return (
              <div
                key={sym.symbol}
                className="grid grid-cols-[2fr_1fr_1.5fr_1.5fr_1.5fr_1.5fr] gap-4 items-center px-5 py-4 hover:bg-white/[0.02] transition-colors"
              >
                {/* Symbol */}
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-xl bg-bg-tertiary border border-border-subtle flex items-center justify-center font-bold font-mono text-xs text-accent-primary flex-shrink-0 overflow-hidden">
                    <CoinIcon symbol={sym.symbol} assetType={sym.asset_type} />
                  </div>
                  <div>
                    <p className="text-sm font-bold text-text-primary">{sym.symbol}</p>
                    <p className="text-[10px] text-text-muted">{sym.name}</p>
                  </div>
                </div>

                {/* Total */}
                <div>
                  <p className="text-sm font-bold font-mono text-text-primary">{sym.total}</p>
                  <p className="text-[10px] text-text-muted">
                    {sym.active > 0 && <span className="text-accent-primary">{sym.active} aktif · </span>}
                    {resolved > 0 ? `${resolved} kapandı` : 'kapanmadı'}
                  </p>
                </div>

                {/* Quality */}
                <QualityBar score={sym.quality_score} />

                {/* Win Rate */}
                <div>
                  <p className={cn('text-sm font-bold font-mono', wrColor)}>
                    {resolved > 0 ? `${sym.win_rate}%` : '—'}
                  </p>
                  {resolved > 0 && (
                    <p className="text-[10px] text-text-muted">
                      {sym.wins}K / {sym.losses}K / {sym.breakeven}BE
                    </p>
                  )}
                </div>

                {/* HTF Type */}
                <HtfSplit types={sym.htf_types} />

                {/* Direction */}
                <DirectionSplit directions={sym.directions} total={sym.total} />
              </div>
            );
          })}
        </div>
      </div>
      </div>
    </div>
  );
}
