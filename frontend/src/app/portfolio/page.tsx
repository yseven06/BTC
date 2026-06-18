'use client';

import React from 'react';
import { PieChart } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';

export default function PortfolioPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold text-text-primary flex items-center gap-2">
          <PieChart className="w-6 h-6 text-accent-primary" /> Portföy
        </h1>
        <p className="text-sm text-text-secondary mt-1">Portföy takip ve analiz</p>
      </div>
      <GlassCard>
        <p className="text-text-muted text-sm text-center py-10">
          Portföy özelliği yakında aktif olacak.
        </p>
      </GlassCard>
    </div>
  );
}
