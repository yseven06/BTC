'use client';

import { useEffect, useRef } from 'react';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { useTierLimits } from '@/hooks/useTierLimits';
import { initAnalytics, identify, reset, pageview, setUserTier } from '@/lib/analytics';
import { onConsentChange } from '@/lib/consent/cookie-consent';
import { recordCookieConsent } from '@/lib/api';

/**
 * Wires the analytics facade to app lifecycle: init once, keep `user_tier`
 * fresh, identify on login / reset on logout, and one pageview per route change.
 * Renders nothing. Imports ONLY the analytics facade — never the provider.
 */
export function AnalyticsProvider() {
  const pathname = usePathname();
  const { user } = useAuth();
  const limits = useTierLimits();
  const prevUserId = useRef<string | null>(null);

  // One-time init (no-op unless a key is configured).
  useEffect(() => {
    initAnalytics();
  }, []);

  // Keep the common `user_tier` property in sync with the resolved tier.
  useEffect(() => {
    if (!limits.loading) setUserTier(limits.tier);
  }, [limits.tier, limits.loading]);

  // Identify on login, reset on logout (single source of truth).
  useEffect(() => {
    const id = user?.id ?? null;
    if (id && id !== prevUserId.current) {
      identify(id, { role: user?.role, is_admin: user?.is_admin });
    } else if (!id && prevUserId.current) {
      reset();
    }
    prevUserId.current = id;
  }, [user]);

  // Manual pageview on client-side navigation.
  useEffect(() => {
    if (pathname) pageview(pathname);
  }, [pathname]);

  // Mirror cookie-consent changes to the server ConsentLog for logged-in users
  // (anonymous consent stays client-side).
  useEffect(() => {
    return onConsentChange((c) => {
      if (user) recordCookieConsent(c.analytics, c.version, 'tr').catch(() => {});
    });
  }, [user]);

  return null;
}
