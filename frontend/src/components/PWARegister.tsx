'use client';

import { useEffect } from 'react';

/**
 * Registers the service worker (public/sw.js) for PWA / offline support.
 * Production-only: in dev we skip it so it never interferes with Next HMR.
 */
export function PWARegister() {
  useEffect(() => {
    if (
      typeof window === 'undefined' ||
      !('serviceWorker' in navigator) ||
      process.env.NODE_ENV !== 'production'
    ) {
      return;
    }
    const onLoad = () => {
      navigator.serviceWorker.register('/sw.js').catch(() => {
        /* registration is best-effort; the app works without it */
      });
    };
    window.addEventListener('load', onLoad);
    return () => window.removeEventListener('load', onLoad);
  }, []);

  return null;
}
