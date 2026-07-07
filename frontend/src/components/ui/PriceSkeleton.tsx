'use client';

import { useEffect, useState } from 'react';

/**
 * Placeholder for a live price that hasn't streamed in yet.
 *
 * Live prices arrive via the Binance WebSocket / REST poll a beat after first
 * render — showing a bare "—" or 0 in that window reads as "broken". This shows
 * a pulsing skeleton bar during a short grace window, then falls back to "—"
 * only if the price is genuinely unavailable.
 *
 * Self-contained: it is rendered only while the price is missing and unmounts
 * the moment the price arrives, so no parent loading state is needed.
 */
export function PriceSkeleton({ graceMs = 4000 }: { graceMs?: number }) {
  const [waited, setWaited] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setWaited(true), graceMs);
    return () => clearTimeout(t);
  }, [graceMs]);

  if (waited) return <span className="text-text-muted">—</span>;

  return (
    <span
      role="status"
      aria-label="Fiyat yükleniyor"
      className="inline-block h-3.5 w-14 rounded bg-text-muted/20 align-middle"
    />
  );
}
