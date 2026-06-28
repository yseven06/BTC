'use client';

import { useEffect, useState } from 'react';

/**
 * Single source of truth for BIST (Borsa İstanbul) open/closed status.
 *
 * Backed by GET /api/v1/prices/market-status. Module-level cache + in-flight
 * dedupe + a shared 60s refresh so the whole app issues at most one status
 * request per minute, no matter how many components subscribe. Returns:
 *   true  → BIST açık
 *   false → BIST kapalı
 *   null  → henüz bilinmiyor (ilk yükleme)
 *
 * Used to gate stock price polling and to show a "Piyasa kapalı · Son kapanış"
 * state. Crypto is 24/7 and never consults this.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const REFRESH_MS = 60_000;

let cached: boolean | null = null;
let lastFetch = 0;
let inflight: Promise<void> | null = null;
const subscribers = new Set<(v: boolean | null) => void>();

async function refresh(force = false): Promise<void> {
  if (!force && Date.now() - lastFetch < REFRESH_MS) return;
  if (inflight) return inflight;
  inflight = (async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/prices/market-status`);
      if (res.ok) {
        const data = await res.json();
        cached = !!data.bist_open;
        lastFetch = Date.now();
        subscribers.forEach((cb) => cb(cached));
      }
    } catch {
      // network error → keep last known value
    } finally {
      inflight = null;
    }
  })();
  return inflight;
}

export function useBistStatus(): boolean | null {
  const [open, setOpen] = useState<boolean | null>(cached);

  useEffect(() => {
    subscribers.add(setOpen);
    refresh(); // deduped across subscribers
    const id = setInterval(() => refresh(), REFRESH_MS);
    return () => {
      subscribers.delete(setOpen);
      clearInterval(id);
    };
  }, []);

  return open;
}
