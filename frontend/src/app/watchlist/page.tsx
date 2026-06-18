'use client';

import React from 'react';
import { Star } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';

export default function WatchlistPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold text-text-primary flex items-center gap-2">
          <Star className="w-6 h-6 text-accent-primary" /> İzleme Listesi
        </h1>
        <p className="text-sm text-text-secondary mt-1">Kaydettiğin varlıklar</p>
      </div>
      <GlassCard>
        <p className="text-text-muted text-sm text-center py-10">
          İzleme listesi özelliği yakında aktif olacak.
        </p>
      </GlassCard>
    </div>
  );
}
