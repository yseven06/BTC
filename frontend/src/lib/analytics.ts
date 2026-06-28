'use client';

/**
 * Provider-agnostic analytics facade.
 *
 * The application calls ONLY `track / identify / reset / pageview` (plus the
 * lifecycle helpers) and never imports the underlying provider. PostHog is an
 * implementation detail confined to this file — to switch providers later,
 * change ONLY this module.
 *
 * Privacy: consent-gated (nothing is captured until `setAnalyticsConsent(true)`,
 * which the cookie banner will call) and a no-op unless NEXT_PUBLIC_POSTHOG_KEY
 * is set — so local/dev and the data-collection backend are unaffected.
 */

import posthog from 'posthog-js';

const KEY = process.env.NEXT_PUBLIC_POSTHOG_KEY;
const HOST = process.env.NEXT_PUBLIC_POSTHOG_HOST ?? 'https://eu.i.posthog.com';
const APP_VERSION = process.env.NEXT_PUBLIC_APP_VERSION ?? '0.0.0';

// Bump when the event taxonomy / common-property schema changes.
const ANALYTICS_SCHEMA_VERSION = 1;

type Props = Record<string, unknown>;

let _initialized = false;
let _consent = false;
let _userTier = 'anonymous';

const isBrowser = (): boolean => typeof window !== 'undefined';
const active = (): boolean => _initialized && _consent && isBrowser();

/** Common properties merged into EVERY event (caller may add symbol/timeframe/regime). */
function withCommon(props?: Props): Props {
  return {
    app_version: APP_VERSION,
    schema_version: ANALYTICS_SCHEMA_VERSION,
    user_tier: _userTier,
    source: 'web',
    ...(props ?? {}),
  };
}

export function initAnalytics(): void {
  if (_initialized || !KEY || !isBrowser()) return;
  posthog.init(KEY, {
    api_host: HOST,
    autocapture: false,
    capture_pageview: false,
    capture_pageleave: true,
    persistence: 'localStorage+cookie',
    person_profiles: 'identified_only',
    // Consent-gated: capture nothing until the user opts in (cookie banner).
    opt_out_capturing_by_default: true,
  });
  _initialized = true;
  if (_consent) posthog.opt_in_capturing();
}

export function setAnalyticsConsent(granted: boolean): void {
  _consent = granted;
  if (!_initialized) return;
  if (granted) posthog.opt_in_capturing();
  else posthog.opt_out_capturing();
}

export function setUserTier(tier?: string | null): void {
  _userTier = tier || 'anonymous';
}

export function track(event: string, props?: Props): void {
  if (!active()) return;
  posthog.capture(event, withCommon(props));
}

export function identify(userId: string, traits?: Props): void {
  if (!active()) return;
  posthog.identify(userId, traits);
}

export function reset(): void {
  _userTier = 'anonymous';
  if (!_initialized) return;
  posthog.reset();
}

export function pageview(path?: string): void {
  if (!active()) return;
  posthog.capture('$pageview', withCommon({ path: path ?? window.location.pathname }));
}
