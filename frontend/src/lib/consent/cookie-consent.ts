'use client';

/**
 * Cookie consent — single source for the consent state + persistence.
 *
 * - Necessary cookies are always on (no consent needed).
 * - Analytics (PostHog) is OFF by default and only enabled after EXPLICIT consent.
 * - The choice is stored client-side (localStorage) with a version + timestamp,
 *   which is the KVKK cookie-consent record and works for anonymous visitors too.
 * - On every change we (1) gate analytics via the provider-agnostic facade and
 *   (2) notify listeners — used in a later step to mirror the change to the
 *   server-side ConsentLog for logged-in users.
 */
import { setAnalyticsConsent } from '@/lib/analytics';

/** Bump when the cookie policy / categories change → users are re-asked. */
export const CONSENT_VERSION = 1;
const STORAGE_KEY = 'tm_cookie_consent';
export const OPEN_COOKIE_SETTINGS_EVENT = 'tm:open-cookie-settings';

export interface CookieConsent {
  necessary: true; // always granted
  analytics: boolean;
  version: number;
  updatedAt: string; // ISO-8601
}

const isBrowser = (): boolean => typeof window !== 'undefined';

/** Stored consent, or null if none yet / stored under an older version. */
export function getStoredConsent(): CookieConsent | null {
  if (!isBrowser()) return null;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CookieConsent;
    if (parsed.version !== CONSENT_VERSION) return null; // re-ask on version bump
    return parsed;
  } catch {
    return null;
  }
}

/** Apply a consent state to the analytics facade (call on app load). */
export function applyConsent(consent: CookieConsent | null): void {
  setAnalyticsConsent(Boolean(consent?.analytics));
}

/** Persist + apply (gates analytics) + notify listeners. */
export function saveConsent(analytics: boolean): CookieConsent {
  const consent: CookieConsent = {
    necessary: true,
    analytics,
    version: CONSENT_VERSION,
    updatedAt: new Date().toISOString(),
  };
  if (isBrowser()) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(consent));
    } catch {
      /* storage unavailable — consent still applied in-memory for this session */
    }
  }
  applyConsent(consent);
  notify(consent);
  return consent;
}

// --- change listeners (server-side ConsentLog sync hooks in later) ----------
type Listener = (c: CookieConsent) => void;
const listeners = new Set<Listener>();

export function onConsentChange(fn: Listener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function notify(c: CookieConsent): void {
  listeners.forEach((fn) => {
    try {
      fn(c);
    } catch {
      /* a listener must never break the consent flow */
    }
  });
}

/** Reopen the cookie settings panel from anywhere (e.g. the footer link). */
export function openCookieSettings(): void {
  if (isBrowser()) window.dispatchEvent(new Event(OPEN_COOKIE_SETTINGS_EVENT));
}
