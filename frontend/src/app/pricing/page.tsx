'use client';

import React, { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Check, X, Crown, Zap, Sparkles } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Skeleton } from '@/components/ui/Skeleton';
import {
  fetchPlans, fetchMySubscription, startCheckout, cancelSubscription, recordCheckoutConsent,
  type Plan, type BillingCycle, type PlanPricing, type SubscriptionTier,
  type SubscriptionResponse,
} from '@/lib/api';
import { cn, formatDateTR, formatUsd, formatPercentage } from '@/lib/utils';
import { PAYMENTS_ENABLED } from '@/lib/config';
import { track } from '@/lib/analytics';
import { AnalyticsEvent } from '@/lib/analytics-events';
import { InvestmentDisclaimer } from '@/components/legal/InvestmentDisclaimer';
import { CheckoutConfirmModal } from '@/components/billing/CheckoutConfirmModal';
import { useToast } from '@/components/ui/Toast';
import { LEGAL_META } from '@/lib/legal/registry';

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
  premium: 'text-amber',
};

export default function PricingPage() {
  const router = useRouter();
  const search = useSearchParams();
  const toast = useToast();

  const [plans, setPlans] = useState<Plan[]>([]);
  const [sub, setSub] = useState<SubscriptionResponse | null>(null);
  const [cycle, setCycle] = useState<BillingCycle>('quarterly');
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState<SubscriptionTier | null>(null);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [canceling, setCanceling] = useState(false);
  const [pending, setPending] = useState<{ tier: SubscriptionTier; cycle: BillingCycle } | null>(null);

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

  // Revenue-funnel entry: the pricing page was viewed.
  useEffect(() => {
    track(AnalyticsEvent.pricing_viewed);
  }, []);

  // Open the pre-payment confirmation modal (shows terms + auto-renewal, collects consent).
  const subscribe = (tier: SubscriptionTier, overrideCycle?: BillingCycle) => {
    // Beta: payments disabled — never open the checkout/consent flow.
    if (tier === 'free' || !PAYMENTS_ENABLED) return;
    setPending({ tier, cycle: overrideCycle ?? cycle });
  };

  // After the user accepts in the modal: record checkout consent, then start payment.
  const confirmCheckout = async () => {
    if (!pending) return;
    const { tier, cycle: cyc } = pending;
    const plan = plans.find((p) => p.tier === tier);
    const pricing = plan?.pricing.find((p) => p.cycle === cyc) ?? plan?.pricing[0];
    const months = pricing?.months ?? 1;
    const next = new Date();
    next.setMonth(next.getMonth() + months);

    track(AnalyticsEvent.checkout_started, { tier, billing_cycle: cyc });
    setProcessing(tier);
    try {
      // Record distance-sale + auto-renewal + withdrawal-waiver consent BEFORE payment
      // (best-effort: never block the purchase if the audit infra is mid-migration).
      await recordCheckoutConsent({
        tier,
        cycle: cyc,
        amount_usd: pricing?.amount_usd ?? 0,
        months,
        next_charge_date: next.toISOString(),
        document_version: LEGAL_META['mesafeli-satis']?.version ?? '0.0.0',
        document_hash: LEGAL_META['mesafeli-satis']?.hash ?? '',
        immediate_performance: true,
      }).catch(() => {});

      const r = await startCheckout(tier, cyc);
      if (r.mock) {
        router.push(r.url);
      } else {
        window.location.href = r.url;
      }
    } catch (e: any) {
      toast.error('Ödeme başlatılamadı: ' + (e?.message ?? 'bilinmeyen hata'));
    } finally {
      setProcessing(null);
      setPending(null);
    }
  };

  // Cancel = stop auto-renew (backend sets cancel_at_period_end). There is no
  // separate "resume" endpoint — reactivation goes through checkout again.
  const doCancel = async () => {
    setCanceling(true);
    try {
      const updated = await cancelSubscription();
      setSub(updated);
      setConfirmCancel(false);
    } catch (e: any) {
      toast.error('İptal edilemedi: ' + (e?.message ?? 'bilinmeyen hata'));
    } finally {
      setCanceling(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="text-center max-w-2xl mx-auto">
        <h1 className="text-h1 font-display text-text-primary">Planlar & Fiyatlandırma</h1>
        <p className="text-sm text-text-secondary mt-2">
          AI motorlarına tam erişim ve sınırsız sinyal için yükselt.
        </p>
      </div>

      {!PAYMENTS_ENABLED && (
        <div className="bg-accent-primary/10 border border-accent-primary/30 rounded-xl p-3 text-center text-sm text-accent-primary max-w-2xl mx-auto">
          Ödeme sistemi çok yakında. Beta süresince planları inceleyebilirsin; şu an ödeme alınmıyor.
        </div>
      )}

      {canceled && (
        <div className="bg-amber/10 border border-amber/30 rounded-xl p-3 text-center text-sm text-amber">
          Ödeme iptal edildi. Hazır olduğunda tekrar dene.
        </div>
      )}

      {/* Current Subscription */}
      {sub && sub.tier !== 'free' && (
        <GlassCard className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div className="min-w-0">
            <p className="text-xs text-text-muted uppercase font-display">Mevcut Aboneliğin</p>
            <p className="text-lg font-display text-text-primary capitalize mt-1">
              {sub.tier} – {sub.status}
              {sub.billing_cycle && <span className="text-text-muted font-medium"> · {CYCLE_LABEL[sub.billing_cycle]}</span>}
            </p>
            {sub.current_period_end && (
              <p className="text-xs text-text-secondary mt-0.5">
                {sub.cancel_at_period_end ? (
                  <>Aboneliğin <span className="text-bearish font-display">{formatDateTR(sub.current_period_end)}</span> tarihinde sona erecek.</>
                ) : (
                  <>Sonraki yenileme: {formatDateTR(sub.current_period_end)}</>
                )}
              </p>
            )}
            {sub.cancel_at_period_end && (
              <p className="text-micro text-text-muted mt-1 max-w-md">
                Aboneliğin mevcut dönem sonunda sona erecek. Devam etmek istersen ödeme ekranından yeniden etkinleştirebilirsin.
              </p>
            )}
          </div>

          <div className="flex-shrink-0">
            {sub.cancel_at_period_end ? (
              <button
                onClick={() => subscribe(sub.tier, sub.billing_cycle ?? undefined)}
                disabled={processing !== null}
                className="focus-ring inline-flex items-center text-sm font-display bg-accent-primary hover:bg-accent-hover text-white px-4 py-2 rounded-xl transition-colors disabled:opacity-50"
              >
                {processing === sub.tier ? 'İşleniyor...' : 'Aboneliği Devam Ettir'}
              </button>
            ) : confirmCancel ? (
              <div className="flex items-center gap-2">
                <span className="text-xs text-text-secondary">Emin misin?</span>
                <button
                  onClick={doCancel}
                  disabled={canceling}
                  className="focus-ring inline-flex items-center text-xs font-display bg-bearish/15 border border-bearish/40 text-bearish hover:bg-bearish/25 px-3 py-1.5 rounded-xl transition-colors disabled:opacity-50"
                >
                  {canceling ? 'Durduruluyor...' : 'Evet, durdur'}
                </button>
                <button
                  onClick={() => setConfirmCancel(false)}
                  disabled={canceling}
                  className="focus-ring text-xs font-display text-text-secondary hover:text-text-primary px-2 py-1.5 rounded-lg transition-colors disabled:opacity-50"
                >
                  Vazgeç
                </button>
              </div>
            ) : (
              <button
                onClick={() => setConfirmCancel(true)}
                className="focus-ring inline-flex items-center text-sm font-display text-text-secondary hover:text-text-primary border border-border-medium hover:border-bearish/40 px-4 py-2 rounded-xl transition-colors"
              >
                Yenilemeyi Durdur
              </button>
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
                'px-4 py-2 text-sm font-display rounded-lg transition-colors',
                cycle === c ? 'bg-accent-primary text-white' : 'text-text-muted hover:text-text-primary'
              )}
            >
              {CYCLE_LABEL[c]}
            </button>
          ))}
        </div>
      </div>

      {/* Plans */}
      {loading ? (
        <div role="status" aria-busy="true">
          <span className="sr-only">Yükleniyor...</span>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5" aria-hidden="true">
            {[0, 1, 2].map((i) => (
              <GlassCard key={i} className="flex flex-col md:min-h-[476px]">
                {/* icon + plan adı */}
                <div className="flex items-center gap-2 mb-1">
                  <Skeleton className="h-5 w-5 rounded-md" />
                  <Skeleton className="h-6 w-28 rounded-md" />
                </div>
                {/* açıklama */}
                <Skeleton className="h-3 w-44 rounded-md mb-4" />
                {/* fiyat bloğu */}
                <div className="mb-5">
                  <Skeleton className="h-9 w-28 rounded-md" />
                  <Skeleton className="h-3 w-20 rounded-md mt-2" />
                  <Skeleton className="h-3 w-16 rounded-md mt-1.5" />
                </div>
                {/* özellikler */}
                <div className="space-y-2 mb-6 flex-1">
                  {Array.from({ length: 9 }).map((_, r) => (
                    <div key={r} className="flex items-start gap-2">
                      <Skeleton className="h-3.5 w-3.5 rounded-md flex-shrink-0" />
                      <Skeleton className="h-3.5 flex-1 rounded-md" />
                    </div>
                  ))}
                </div>
                {/* CTA */}
                <Skeleton className="h-10 w-full rounded-xl" />
              </GlassCard>
            ))}
          </div>
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
                  plan.recommended && 'border-accent-primary/40'
                )}
              >
                {plan.recommended && (
                  <span className="absolute -top-2.5 left-1/2 -translate-x-1/2 text-micro font-medium uppercase bg-accent-primary text-white px-3 py-1 rounded-full">
                    Önerilen
                  </span>
                )}

                <div className="flex items-center gap-2 mb-1">
                  <Icon className={cn('w-5 h-5', TIER_COLOR[plan.tier])} />
                  <h3 className="text-lg font-display text-text-primary">{plan.name}</h3>
                </div>
                <p className="text-xs text-text-secondary mb-4">{plan.description}</p>

                <div className="mb-5">
                  {pricing.amount_usd === 0 ? (
                    <p className="text-h1 font-display text-text-primary">Ücretsiz</p>
                  ) : (
                    <>
                      <p className="text-h1 font-display text-text-primary">
                        ${pricing.amount_usd}
                        <span className="text-xs font-medium text-text-muted ml-1">/{CYCLE_LABEL[pricing.cycle]}</span>
                      </p>
                      {pricing.months > 1 && (
                        <p className="text-micro text-text-muted mt-0.5">
                          (~{formatUsd(monthlyEffective)}/ay)
                        </p>
                      )}
                      {pricing.savings_pct > 0 && (
                        <p className="text-micro text-bullish font-medium mt-0.5">{formatPercentage(pricing.savings_pct, 0, false)} tasarruf</p>
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
                  disabled={isCurrent || plan.tier === 'free' || processing !== null || !PAYMENTS_ENABLED}
                  className={cn(
                    'w-full py-2.5 rounded-xl text-sm font-display transition-[color,background-color,border-color,opacity] disabled:opacity-50',
                    isCurrent
                      ? 'bg-bg-tertiary text-text-muted cursor-default'
                      : plan.tier === 'free' || !PAYMENTS_ENABLED
                      ? 'bg-bg-tertiary text-text-muted'
                      : plan.recommended
                      ? 'bg-accent-primary hover:bg-accent-hover text-white'
                      : 'bg-bg-tertiary border border-border-medium hover:border-accent-primary/40 text-text-primary'
                  )}
                >
                  {processing === plan.tier ? 'İşleniyor...'
                   : isCurrent ? 'Mevcut Planın'
                   : plan.tier === 'free' ? 'Varsayılan'
                   : !PAYMENTS_ENABLED ? 'Yakında'
                   : 'Yükselt'}
                </button>
              </GlassCard>
            );
          })}
        </div>
      )}

      {PAYMENTS_ENABLED && (
        <p className="text-center text-micro text-text-muted">
          Ödemeler USD üzerinden alınır. İstediğin zaman iptal edebilirsin.
        </p>
      )}

      <InvestmentDisclaimer variant="inline" className="mx-auto max-w-2xl" />

      {pending && (() => {
        const plan = plans.find((p) => p.tier === pending.tier);
        const pricing = plan?.pricing.find((p) => p.cycle === pending.cycle) ?? plan?.pricing[0];
        const months = pricing?.months ?? 1;
        const next = new Date();
        next.setMonth(next.getMonth() + months);
        return (
          <CheckoutConfirmModal
            planName={plan?.name ?? pending.tier}
            cycleLabel={CYCLE_LABEL[pending.cycle]}
            months={months}
            amountUsd={pricing?.amount_usd ?? 0}
            nextRenewalStr={formatDateTR(next)}
            processing={processing === pending.tier}
            onConfirm={confirmCheckout}
            onClose={() => setPending(null)}
          />
        );
      })()}
    </div>
  );
}
