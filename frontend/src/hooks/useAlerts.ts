'use client';

import { useEffect, useState } from 'react';
import { fetchAlerts, type ApiAlert } from '@/lib/api';

// Single-source alert fetch shared across Header + Sidebar (and any future
// consumer). The persistent app shell mounts these once per session, so a
// module-level cache + in-flight dedupe means /alerts is fetched ONCE instead
// of once per component — same data, fewer requests. Behaviour matches the
// previous "fetch once on mount" (no polling); a full reload refreshes it.
let cache: ApiAlert[] | null = null;
let inflight: Promise<ApiAlert[]> | null = null;
const subscribers = new Set<(a: ApiAlert[]) => void>();

function loadOnce(): Promise<ApiAlert[]> {
  if (cache) return Promise.resolve(cache);
  if (!inflight) {
    inflight = fetchAlerts()
      .then((a) => {
        cache = a;
        subscribers.forEach((fn) => fn(a));
        return a;
      })
      .catch(() => {
        cache = [];
        return [];
      })
      .finally(() => {
        inflight = null;
      });
  }
  return inflight;
}

/** Returns the current user's alerts, fetched once and shared app-wide. */
export function useAlerts(): ApiAlert[] {
  const [alerts, setAlerts] = useState<ApiAlert[]>(cache ?? []);
  useEffect(() => {
    subscribers.add(setAlerts);
    loadOnce().then(setAlerts);
    return () => {
      subscribers.delete(setAlerts);
    };
  }, []);
  return alerts;
}
