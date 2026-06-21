'use client';

import React, { useState } from 'react';

// Longest-first so "USDT" matches before the shorter "USD" would
// incorrectly strip just the trailing "T".
const QUOTE_SUFFIXES = ['USDT', 'BUSD', 'USDC', 'TUSD', 'TRY', 'EUR', 'GBP', 'USD', 'BTC', 'ETH', 'BNB'];

function baseCoinSymbol(symbol: string): string | null {
  const s = symbol.toUpperCase();
  for (const q of QUOTE_SUFFIXES) {
    if (s.length > q.length && s.endsWith(q)) {
      return s.slice(0, s.length - q.length);
    }
  }
  return null;
}

interface CoinIconProps {
  symbol: string;
  assetType?: string;
}

/**
 * Drop-in replacement for the old `{symbol.slice(0, 2)}` initials —
 * renders the real coin logo (from coincap.io's public icon CDN) when the
 * symbol looks like crypto, falling back to the two-letter initials if the
 * image 404s or the asset isn't crypto (stocks/forex have no coin logo).
 * Intentionally renders only the *content*: callers keep their existing
 * sized/styled wrapper div unchanged.
 */
export function CoinIcon({ symbol, assetType }: CoinIconProps) {
  const [errored, setErrored] = useState(false);
  const base = (!assetType || assetType === 'crypto') ? baseCoinSymbol(symbol) : null;

  if (base && !errored) {
    return (
      <img
        src={`https://assets.coincap.io/assets/icons/${base.toLowerCase()}@2x.png`}
        alt={symbol}
        className="w-2/3 h-2/3 object-contain"
        onError={() => setErrored(true)}
      />
    );
  }

  return <>{symbol.slice(0, 2)}</>;
}
