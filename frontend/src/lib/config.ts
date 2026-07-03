/**
 * App-wide feature flags (single source of truth).
 *
 * PAYMENTS_ENABLED — the paid subscription funnel: pricing checkout, "Yükselt"
 * upgrade CTAs, and the distance-sale / auto-renewal / withdrawal-waiver consent
 * collection. Disabled for the invite-only beta; payments turn on only once Stripe
 * and the operator's billing info are live. Gate EVERY checkout action and upgrade
 * CTA on this flag — do not hardcode payment availability anywhere else.
 *
 * Override at build time with NEXT_PUBLIC_PAYMENTS_ENABLED=true.
 */
export const PAYMENTS_ENABLED =
  (process.env.NEXT_PUBLIC_PAYMENTS_ENABLED ?? 'false').toLowerCase() === 'true';
