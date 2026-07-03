'use client';

import React from 'react';
import Link from 'next/link';
import { Lock, Crown } from 'lucide-react';
import { PAYMENTS_ENABLED } from '@/lib/config';

interface LockedOverlayProps {
  title?: string;
  description?: string;
  className?: string;
}

export function LockedOverlay({
  title       = 'Pro Özellik',
  description = 'Bu içeriği görmek için Pro veya üzeri bir abonelik gereklidir.',
  className,
}: LockedOverlayProps) {
  return (
    <div className={`absolute inset-0 flex flex-col items-center justify-center bg-bg-primary/85 backdrop-blur-md rounded-2xl z-20 p-6 text-center ${className ?? ''}`}>
      <div className="w-12 h-12 rounded-full bg-orange-500/15 border border-orange-500/30 flex items-center justify-center mb-3">
        <Lock className="w-5 h-5 text-orange-400" />
      </div>
      <h3 className="text-base font-bold text-text-primary mb-1">{title}</h3>
      <p className="text-xs text-text-secondary max-w-xs mb-4">{description}</p>
      {PAYMENTS_ENABLED ? (
        <Link
          href="/pricing"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-orange-500 hover:bg-orange-600 text-white text-sm font-bold transition-colors"
        >
          <Crown className="w-4 h-4" /> Plana Yükselt
        </Link>
      ) : (
        <span className="text-[11px] text-text-muted">Beta sürümünde yakında açılacak.</span>
      )}
    </div>
  );
}

/** Compact inline-locked badge for hiding small areas (e.g. a single card). */
export function InlineLocked({ feature = 'Pro' }: { feature?: string }) {
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase text-orange-400 bg-orange-500/10 border border-orange-500/30 px-2 py-0.5 rounded">
      <Lock className="w-2.5 h-2.5" /> {feature}
    </span>
  );
}
