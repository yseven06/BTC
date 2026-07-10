'use client';

import React from 'react';
import Link from 'next/link';
import { BarChart3, ArrowRight, TrendingUp, TrendingDown } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { formatPercentage, cn } from '@/lib/utils';

interface SicilProps {
  profitFactor: number | null;
  maxDrawdown: number;
  tpHitRate: number;
  slRate: number;
  bestSignal: { symbol: string; return: number } | null;
  worstSignal: { symbol: string; return: number } | null;
  periodLabel: string;
  loading: boolean;
  hasData: boolean;
}

export function Sicil({
  profitFactor, maxDrawdown, tpHitRate, slRate,
  bestSignal, worstSignal, periodLabel, loading, hasData,
}: SicilProps) {
  if (loading || !hasData) return null;

  return (
    <GlassCard>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-base font-display text-text-primary flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-accent-primary" />
          Sicil
        </h2>
        <Link href="/signal-history" className="text-xs text-accent-primary hover:text-accent-ui flex items-center gap-1">
          Gecmise Git <ArrowRight className="w-3 h-3" />
        </Link>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="p-3 bg-bg-secondary/60 border border-border-subtle rounded-xl">
          <p className="text-micro text-text-muted uppercase font-medium">Kar Faktoru</p>
          <p className={cn(
            'text-xl num font-num-560 mt-1',
            profitFactor != null && profitFactor >= 1 ? 'text-bullish'
              : profitFactor != null ? 'text-bearish'
              : 'text-text-muted',
          )}>
            {profitFactor != null ? profitFactor.toFixed(2) : '—'}
          </p>
          <p className="text-micro text-text-muted mt-0.5">{periodLabel}</p>
        </div>

        <div className="p-3 bg-bg-secondary/60 border border-border-subtle rounded-xl">
          <p className="text-micro text-text-muted uppercase font-medium">Maks. Dusus</p>
          <p className="text-xl num font-num-560 mt-1 text-bearish">
            -{formatPercentage(maxDrawdown, 2, false)}
          </p>
          <p className="text-micro text-text-muted mt-0.5">tum zamanlar</p>
        </div>

        <div className="p-3 bg-bg-secondary/60 border border-border-subtle rounded-xl">
          <p className="text-micro text-text-muted uppercase font-medium">TP Vurma Orani</p>
          <p className="text-xl num font-num-560 mt-1 text-bullish">
            {formatPercentage(tpHitRate, 0, false)}
          </p>
          <p className="text-micro text-text-muted mt-0.5">{periodLabel}</p>
        </div>

        <div className="p-3 bg-bg-secondary/60 border border-border-subtle rounded-xl">
          <p className="text-micro text-text-muted uppercase font-medium">SL Orani</p>
          <p className="text-xl num font-num-560 mt-1 text-bearish">
            {formatPercentage(slRate, 0, false)}
          </p>
          <p className="text-micro text-text-muted mt-0.5">{periodLabel}</p>
        </div>
      </div>

      {(bestSignal || worstSignal) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4">
          {bestSignal && (
            <div className="flex items-center gap-3 p-3 bg-bullish/[0.04] border border-bullish/20 rounded-xl">
              <TrendingUp className="w-4 h-4 text-bullish flex-shrink-0" />
              <div className="min-w-0">
                <p className="text-micro text-text-muted uppercase font-medium">En Iyi Sinyal</p>
                <p className="text-sm font-display text-text-primary mt-0.5 truncate">
                  {bestSignal.symbol}
                  <span className="ml-2 num font-num-520 text-bullish">
                    {formatPercentage(bestSignal.return)}
                  </span>
                </p>
              </div>
            </div>
          )}
          {worstSignal && (
            <div className="flex items-center gap-3 p-3 bg-bearish/[0.04] border border-bearish/20 rounded-xl">
              <TrendingDown className="w-4 h-4 text-bearish flex-shrink-0" />
              <div className="min-w-0">
                <p className="text-micro text-text-muted uppercase font-medium">En Kotu Sinyal</p>
                <p className="text-sm font-display text-text-primary mt-0.5 truncate">
                  {worstSignal.symbol}
                  <span className="ml-2 num font-num-520 text-bearish">
                    {formatPercentage(worstSignal.return)}
                  </span>
                </p>
              </div>
            </div>
          )}
        </div>
      )}
    </GlassCard>
  );
}
