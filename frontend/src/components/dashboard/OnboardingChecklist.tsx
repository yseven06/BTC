'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  Zap, Bell, BarChart3, Star, Check, X, ArrowRight, PartyPopper,
} from 'lucide-react';
import { cn } from '@/lib/utils';

// Frontend-only onboarding state (device-scoped). No backend dependency —
// cross-device persistence would need a user.is_onboarded field later.
const STORAGE_KEY = 'tm_onboarding_v1';

interface Step {
  id: string;
  label: string;
  desc: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
}

const STEPS: Step[] = [
  { id: 'signal',    label: 'İlk sinyalini incele',          desc: 'AI motorlarının ürettiği AL/SAT sinyallerini gör.', href: '/signals',         icon: Zap },
  { id: 'telegram',  label: 'Telegram bildirimlerini bağla', desc: 'Yeni sinyallerden anında haberdar ol.',             href: '/settings',        icon: Bell },
  { id: 'analysis',  label: 'İlk Symbol Analysis\'i aç',      desc: 'Bir coin için derin AI analizini çalıştır.',        href: '/symbol-analysis', icon: BarChart3 },
  { id: 'watchlist', label: 'Watchlist oluştur',             desc: 'Takip etmek istediğin coinleri ekle.',              href: '/watchlist',       icon: Star },
];

interface OnboardingState {
  completed: string[];
  dismissed: boolean;
}

function loadState(): OnboardingState {
  if (typeof window === 'undefined') return { completed: [], dismissed: false };
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { completed: [], dismissed: false };
    const parsed = JSON.parse(raw);
    return {
      completed: Array.isArray(parsed?.completed) ? parsed.completed : [],
      dismissed: !!parsed?.dismissed,
    };
  } catch {
    return { completed: [], dismissed: false };
  }
}

function saveState(s: OnboardingState): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  } catch {
    /* storage unavailable — non-fatal */
  }
}

export default function OnboardingChecklist() {
  // localStorage is client-only; render nothing until mounted to avoid
  // hydration mismatch / flash.
  const [mounted, setMounted] = useState(false);
  const [state, setState] = useState<OnboardingState>({ completed: [], dismissed: false });

  useEffect(() => {
    setState(loadState());
    setMounted(true);
  }, []);

  if (!mounted || state.dismissed) return null;

  const markComplete = (id: string) => {
    setState((prev) => {
      if (prev.completed.includes(id)) return prev;
      const next = { ...prev, completed: [...prev.completed, id] };
      saveState(next);
      return next;
    });
  };

  const dismiss = () => {
    const next = { ...state, dismissed: true };
    saveState(next);
    setState(next);
  };

  const done = state.completed.length;
  const total = STEPS.length;
  const allDone = done >= total;

  return (
    <div className="bg-gradient-to-r from-accent-primary/10 via-bg-secondary/40 to-accent-primary/10 border border-accent-primary/30 rounded-2xl p-5">
      {/* Header + progress count + dismiss */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-sm font-bold text-text-primary flex items-center gap-2">
            <PartyPopper className="w-4 h-4 text-accent-primary flex-shrink-0" />
            {allDone ? 'Harika! Kuruluma hazırsın' : "TradeMinds'e hoş geldin — başlamak için 4 adım"}
          </h2>
          {!allDone && (
            <p className="text-xs text-text-secondary mt-0.5">Birkaç dakikada ürünü tanı, ilk değerini yakala.</p>
          )}
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          <span className="text-xs font-mono font-bold text-accent-primary whitespace-nowrap">{done}/{total}</span>
          <button onClick={dismiss} aria-label="Onboarding'i kapat" className="focus-ring rounded-md text-text-muted hover:text-text-primary transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Progress bar */}
      <div className="mt-3 h-1.5 rounded-full bg-bg-tertiary overflow-hidden">
        <div className="h-full bg-accent-primary transition-all duration-300" style={{ width: `${(done / total) * 100}%` }} />
      </div>

      {allDone ? (
        <div className="mt-4 text-center">
          <p className="text-sm font-semibold text-bullish">Tüm adımları tamamladın — iyi işlemler! 🚀</p>
          <button
            onClick={dismiss}
            className="focus-ring mt-3 inline-flex items-center text-xs font-bold bg-accent-primary hover:bg-accent-secondary text-white px-4 py-2 rounded-xl transition-colors"
          >
            Kapat
          </button>
        </div>
      ) : (
        <ul className="mt-4 space-y-2">
          {STEPS.map((s) => {
            const isDone = state.completed.includes(s.id);
            const Icon = s.icon;
            return (
              <li key={s.id}>
                <Link
                  href={s.href}
                  onClick={() => markComplete(s.id)}
                  className="focus-ring group flex items-center gap-3 rounded-xl border border-border-subtle bg-bg-secondary/50 hover:border-accent-primary/40 px-3 py-2.5 transition-colors"
                >
                  <span className={cn('flex items-center justify-center w-7 h-7 rounded-lg flex-shrink-0', isDone ? 'bg-bullish/15 text-bullish' : 'bg-accent-primary/10 text-accent-primary')}>
                    {isDone ? <Check className="w-4 h-4" /> : <Icon className="w-4 h-4" />}
                  </span>
                  <span className="flex-1 min-w-0">
                    <span className={cn('block text-sm font-semibold', isDone ? 'text-text-muted line-through' : 'text-text-primary')}>{s.label}</span>
                    <span className="block text-[11px] text-text-secondary truncate">{s.desc}</span>
                  </span>
                  {!isDone && <ArrowRight className="w-4 h-4 text-text-muted group-hover:text-accent-primary flex-shrink-0" />}
                </Link>
              </li>
            );
          })}
        </ul>
      )}

      {/* Bottom note */}
      <p className="mt-3 text-[11px] text-text-muted text-center">
        Bu adımları istediğin zaman atlayabilir veya daha sonra tamamlayabilirsin.
      </p>
    </div>
  );
}
