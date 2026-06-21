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

// BIST has no equivalent of coincap.io — no free, standard, symbol-keyed
// logo API exists for it. TradingView's CDN does serve real company logos,
// but only under company-name slugs that aren't derivable from the ticker
// (e.g. AKBNK → "akbank" works, but GARAN needs "garanti" not "garan", and
// THYAO needs "turk-hava-yollari" not "thy"/"thyao"). Each entry below was
// individually verified against the CDN (200 vs 403) — this is not a
// formula, it's a lookup table built one symbol at a time.
const BIST_LOGO_SLUGS: Record<string, string> = {
  THYAO: 'turk-hava-yollari',
  GARAN: 'garanti',
  AKBNK: 'akbank',
  ISCTR: 'is-bankasi',
  SISE: 'sisecam',
  TUPRS: 'tupras',
  ASELS: 'aselsan',
  PETKM: 'petkim',
  TCELL: 'turkcell',
  TTKOM: 'turk-telekom',
  FROTO: 'ford-otosan',
  ENKAI: 'enka-insaat',
  KCHOL: 'koc',
  SAHOL: 'sabanci-holding',
  HALKB: 't-halk-bankasi',
  DOHOL: 'dogan-holding',
  PNSUT: 'pinar-sut',
  MRSHL: 'marshall-boya',
  EDIP: 'edip-gayrimenkul',
  AZTEK: 'aztek-teknoloji',
  OBASE: 'obase-bilgisayar',
  BURCE: 'burcelik',
  CMBTN: 'cimbeton',
  KRPLS: 'kartonsan',
  TRALT: 'trakya-cam',
  MEGAP: 'mega-polietilen',
  // Not found on TradingView's CDN under any guessed slug — these still
  // fall back to the two-letter initials until someone supplies a logo:
  // EREGL, YKBNK, TOASO, BIMAS, VAKBN, INVEO, ELITE, PAMEL, PRDGS, KARSN,
  // ODAS, SASA.
};

function bistLogoSlug(symbol: string): string | null {
  const ticker = symbol.toUpperCase().replace(/\.IS$/, '');
  return BIST_LOGO_SLUGS[ticker] ?? null;
}

interface CoinIconProps {
  symbol: string;
  assetType?: string;
}

/**
 * Drop-in replacement for the old `{symbol.slice(0, 2)}` initials —
 * renders a real logo (coincap.io for crypto, a hand-verified TradingView
 * slug for the ~26 BIST stocks we found one for) and falls back to the
 * two-letter initials if the image 404s or no logo source is known.
 * Intentionally renders only the *content*: callers keep their existing
 * sized/styled wrapper div unchanged.
 */
export function CoinIcon({ symbol, assetType }: CoinIconProps) {
  const [errored, setErrored] = useState(false);
  const isStock = assetType === 'stock';
  const cryptoBase = !isStock ? baseCoinSymbol(symbol) : null;
  const stockSlug = isStock ? bistLogoSlug(symbol) : null;

  const src = cryptoBase
    ? `https://assets.coincap.io/assets/icons/${cryptoBase.toLowerCase()}@2x.png`
    : stockSlug
    ? `https://s3-symbol-logo.tradingview.com/${stockSlug}--big.svg`
    : null;

  if (src && !errored) {
    return (
      <img
        src={src}
        alt={symbol}
        className="w-2/3 h-2/3 object-contain"
        onError={() => setErrored(true)}
      />
    );
  }

  return <>{symbol.slice(0, 2)}</>;
}
