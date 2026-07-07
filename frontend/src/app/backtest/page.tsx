'use client';

import React from 'react';
import { FlaskConical } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import Link from 'next/link';
import { InvestmentDisclaimer } from '@/components/legal/InvestmentDisclaimer';

export default function BacktestPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-display text-text-primary flex items-center gap-2">
          <FlaskConical className="w-6 h-6 text-accent-primary" /> Backtest
        </h1>
        <p className="text-sm text-text-secondary mt-1">Walk-forward geçmiş simülasyonları</p>
      </div>
      <GlassCard>
        <p className="text-text-secondary text-sm text-center py-6">
          Backtest özelliği Performans sayfasında mevcuttur.{' '}
          <Link href="/performance" className="text-accent-primary hover:underline font-display">
            Performans &amp; Backtest →
          </Link>
        </p>
      </GlassCard>
      <InvestmentDisclaimer variant="backtest" />
    </div>
  );
}
