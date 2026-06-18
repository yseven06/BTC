'use client';

import React, { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Check, X, Crown, Zap, Sparkles } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import {
  fetchPlans, fetchMySubscription, startCheckout,
  type Plan, type BillingCycle, type PlanPricing, type SubscriptionTier,
  type SubscriptionResponse,
} from '@/lib/api';
import { cn } from '@/lib/utils';

const CYCLE_LABEL: Record<BillingCycle, string> = {
  monthly:     '1 Ay',
  quarterly:   '3 Ay',
  semi_annual: '6 Ay',
  yearly:      '12 Ay',
};

const TIER_ICON: Record<SubscriptionTier, React.ComponentType<{ className?: string }>> = {
  free:    Sparkles,
  pro:     Zap,
  premium: Crown,
};

const TIER_COLOR: Record<SubscriptionTier, string> = {
  free:    'text-text-muted',
  pro:     'text-accent-primary',
  premium: 'text-yellow-400',
};

export default function PricingPage() {
  const router = useRouter();
  const search = useSearchParams();

  const [plans, setPlans] = useState<Plan[]>([]);
  const [sub, setSub] = useState<SubscriptionResponse | null>(null);
  const [cycle, setCycle] = useState<BillingCycle>('quarterly');
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState<SubscriptionTier | null>(null);

  // Detect cancel-from-Stripe redirect
  const canceled = search.get('canceled');

  useEffect(() => {
    Promise.all([fetchPlans(), fetchMySubscription().catch(() => null)])
      .then(([p, s]) => {
        setPlans(p.plans);
        setSub(s);
      })
      .finally(() => setLoading(false));
  }, []);

  const subscribe = async (tier: SubscriptionTier) => {
    if (tier === 'free') return;
    setProcessing(tier);
    try {
      const r = await startCheckout(tier, cycle);
      if (r.mock) {
        // Mock mode: immediately refresh and notify user
        router.push(r.url);
      } else {
        window.location.href = r.url;
      }
    } catch (e: any) {
      alert('Ödeme başlatılamadı: ' + (e?.message ?? 'bilinmeyen hata'));
    } finally {
      setProcessing(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="text-center max-w-2xl mx-auto">
        <h1 className="text-3xl font-extrabold text-text-primary">Planlar & Fiyatlandırma</h1>
        <p className="text-sm text-text-secondary mt-2">
          AI motorlarına tam erişim ve sınırsız sinyal için yükselt.
        </p>
      </div>

      {canceled && (
        <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-xl p-3 text-center text-sm text-yellow-400">
          Ödeme iptal edildi. Hazır olduğunda tekrar dene.
        </div>
      )}

      {/* Current Subscription */}
      {sub && sub.tier !== 'free' && (
        <GlassCard className="flex items-center justify-between">
          <div>
            <p className="text-xs text-text-muted uppercase font-semibold">Mevcut Aboneliğin</p>
            <p className="text-lg font-bold text-text-primary capitalize mt-1">{sub.tier} – {sub.status}</p>
            {sub.current_period_end && (
              <p className="text-xs text-text-secondary mt-0.5">
                Bitiş: {new Date(sub.current_period_end).toLocaleDateString('tr-TR')}
                {sub.cancel_at_period_end && <span className="text-bearish ml-2">(iptal edildi)</span>}
              </p>
            )}
          </div>
        </GlassCard>
      )}

      {/* Cycle selector */}
      <div className="flex justify-center">
        <div className="inline-flex gap-1 p-1 bg-bg-secondary border border-border-subtle rounded-xl">
          {(Object.keys(CYCLE_LABEL) as BillingCycle[]).map((c) => (
            <button
              key={c}
              onClick={() => setCycle(c)}
              className={cn(
                'px-4 py-2 text-sm font-semibold rounded-lg transition-all',
                cycle === c ? 'bg-accent-primary text-white shadow-glow-sm' : 'text-text-muted hover:text-text-primary'
              )}
            >
              {CYCLE_LABEL[c]}
            </button>
          ))}
        </div>
      </div>

      {/* Plans */}
      {loading ? (
        <div className="flex justify-center py-16">
          <div className="w-8 h-8 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {plans.map((plan) => {
            const Icon = TIER_ICON[plan.tier];
            const pricing = plan.pricing.find((p: PlanPricing) => p.cycle === cycle)
                          ?? plan.pricing[0];
            const monthlyEffective = pricing.amount_usd / pricing.months;
            const isCurrent = sub?.tier === plan.tier && sub?.status === 'active';

            return (
              <GlassCard
                key={plan.tier}
                className={cn(
                  'flex flex-col relative',
                  plan.recommended && 'border-accent-primary/40 shadow-glow-sm'
                )}
              >
                {plan.recommended && (
                  <span className="absolute -top-2.5 left-1/2 -translate-x-1/2 text-[10px] font-bold uppercase bg-accent-primary text-white px-3 py-1 rounded-full">
                    Önerilen
                  </span>
                )}

                <div className="flex items-center gap-2 mb-1">
                  <Icon className={cn('w-5 h-5', TIER_COLOR[plan.tier])} />
                  <h3 className="text-lg font-bold text-text-primary">{plan.name}</h3>
                </div>
                <p className="text-xs text-text-secondary mb-4">{plan.description}</p>

                <div className="mb-5">
                  {pricing.amount_usd === 0 ? (
                    <p className="text-3xl font-extrabold text-text-primary">Ücretsiz</p>
                  ) : (
                    <>
                      <p className="text-3xl font-extrabold text-text-primary">
                        ${pricing.amount_usd}
                        <span className="text-xs font-medium text-text-muted ml-1">/{CYCLE_LABEL[pricing.cycle]}</span>
                      </p>
                      {pricing.months > 1 && (
                        <p className="text-[11px] text-text-muted mt-0.5">
                          (~${monthlyEffective.toFixed(2)}/ay)
                        </p>
                      )}
                      {pricing.savings_pct > 0 && (
                        <p className="text-[11px] text-bullish font-bold mt-0.5">%{pricing.savings_pct} tasarruf</p>
                      )}
                    </>
                  )}
                </div>

                <ul className="space-y-2 mb-6 flex-1">
                  {plan.features.map((f) => (
                    <li key={f.label} className="flex items-start gap-2 text-xs">
                      {f.included ? (
                        <Check className="w-3.5 h-3.5 text-bullish flex-shrink-0 mt-0.5" />
                      ) : (
                        <X className="w-3.5 h-3.5 text-text-muted flex-shrink-0 mt-0.5" />
                      )}
                      <span className={f.included ? 'text-text-primary' : 'text-text-muted line-through'}>
                        {f.label}
                      </span>
                    </li>
                  ))}
                </ul>

                <button
                  onClick={() => subscribe(plan.tier)}
                  disabled={isCurrent || plan.tier === 'free' || processing !== null}
                  className={cn(
                    'w-full py-2.5 rounded-xl text-sm font-bold transition-all disabled:opacity-50',
                    isCurrent
                      ? 'bg-bg-tertiary text-text-muted cursor-default'
                      : plan.tier === 'free'
                      ? 'bg-bg-tertiary text-text-muted'
                      : plan.recommended
                      ? 'bg-accent-primary hover:bg-accent-secondary text-white'
                      : 'bg-bg-tertiary border border-border-medium hover:border-accent-primary/40 text-text-primary'
                  )}
                >
                  {processing === plan.tier ? 'İşleniyor...'
                   : isCurrent ? 'Mevcut Planın'
                   : plan.tier === 'free' ? 'Varsayılan'
                   : 'Yükselt'}
                </button>
              </GlassCard>
            );
          })}
        </div>
      )}

      <p className="text-center text-[10px] text-text-muted">
        Ödemeler USD üzerinden alınır. İstediğin zaman iptal edebilirsin.
      </p>
    </div>
  );
}
