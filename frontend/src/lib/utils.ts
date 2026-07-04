// ============================================
// TradeMinds AI - Utility Functions
// ============================================

import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { SignalType, RiskLevel } from '@/types';

/**
 * Merge class names with clsx, then resolve Tailwind conflicts with
 * tailwind-merge (last-wins). clsx handles conditional composition; twMerge
 * dedupes conflicting utilities so `cn('px-2', cond && 'px-4')` → 'px-4'.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format number as currency
 */
export function formatCurrency(
  value: number,
  currency: string = 'USD',
  locale: string = 'en-US'
): string {
  if (currency === 'TRY') {
    return new Intl.NumberFormat('tr-TR', {
      style: 'currency',
      currency: 'TRY',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  }

  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    minimumFractionDigits: value >= 1 ? 2 : value >= 0.01 ? 4 : 6,
    maximumFractionDigits: value >= 1 ? 2 : value >= 0.01 ? 4 : 8,
  }).format(value);
}

/**
 * Format large numbers (e.g. market cap)
 */
export function formatLargeNumber(value: number): string {
  if (value >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
  if (value >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
  if (value >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
  if (value >= 1e3) return `$${(value / 1e3).toFixed(2)}K`;
  return `$${value.toFixed(2)}`;
}

/**
 * Format percentage with sign
 */
export function formatPercentage(value: number, decimals: number = 2): string {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(decimals)}%`;
}

/**
 * Adaptive price formatting. Fixed-decimal formatting collapses micro-cap prices
 * to "0" / "0,00" (e.g. SHIB ~0.0000089). Scale precision to magnitude — ≥1000
 * → 2 decimals, ≥1 → up to 4, and under 1 keep ~4 significant figures so small
 * prices stay meaningful. Returns "—" for null/NaN.
 */
export function formatPrice(value: number | null | undefined, locale: string = 'tr-TR'): string {
  if (value == null || Number.isNaN(value)) return '—';
  const abs = Math.abs(value);
  if (abs === 0) return '0';
  if (abs >= 1) {
    return value.toLocaleString(locale, { maximumFractionDigits: abs >= 1000 ? 2 : 4 });
  }
  return value.toLocaleString(locale, { maximumSignificantDigits: 4 });
}

/**
 * Get signal color class
 */
export function getSignalColor(signal: SignalType): string {
  const colors: Record<SignalType, string> = {
    strong_buy: 'text-signal-strong-buy',
    buy: 'text-signal-buy',
    hold: 'text-signal-hold',
    sell: 'text-signal-sell',
    strong_sell: 'text-signal-strong-sell',
  };
  return colors[signal];
}

/**
 * Get signal background class
 */
export function getSignalBgClass(signal: SignalType): string {
  const classes: Record<SignalType, string> = {
    strong_buy: 'signal-bg-strong-buy',
    buy: 'signal-bg-buy',
    hold: 'signal-bg-hold',
    sell: 'signal-bg-sell',
    strong_sell: 'signal-bg-strong-sell',
  };
  return classes[signal];
}

/**
 * Get risk level color
 */
export function getRiskColor(level: RiskLevel): string {
  const colors: Record<RiskLevel, string> = {
    low: '#34D399',
    medium: '#F59E0B',
    high: '#F59E0B',
    very_high: '#EF4444',
  };
  return colors[level];
}

/**
 * Get risk level text class
 */
export function getRiskTextClass(level: RiskLevel): string {
  const classes: Record<RiskLevel, string> = {
    low: 'text-signal-buy',
    medium: 'text-signal-hold',
    high: 'text-orange-500',
    very_high: 'text-signal-sell',
  };
  return classes[level];
}

/**
 * Get price change color class
 */
export function getPriceChangeClass(change: number): string {
  if (change > 0) return 'price-up';
  if (change < 0) return 'price-down';
  return 'price-neutral';
}

/**
 * Format relative time. Compares two epoch moments — timezone independent
 * since getTime() returns UTC ms. Sub-day labels still mean what users expect.
 */
export function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMinutes = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMinutes < 1) return 'Az önce';
  if (diffMinutes < 60) return `${diffMinutes} dakika önce`;
  if (diffHours < 24) return `${diffHours} saat önce`;
  return `${diffDays} gün önce`;
}

/** Absolute time formatter: backend UTC → Europe/Istanbul human label. */
export function formatAbsoluteTimeTR(dateString: string | Date, includeTime = true): string {
  const d = typeof dateString === 'string' ? new Date(dateString) : dateString;
  return d.toLocaleString('tr-TR', {
    timeZone: 'Europe/Istanbul',
    day: '2-digit', month: '2-digit', year: 'numeric',
    ...(includeTime ? { hour: '2-digit', minute: '2-digit' } : {}),
  });
}

/**
 * Generate a deterministic color from a string
 */
export function stringToColor(str: string): string {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = hash % 360;
  return `hsl(${hue}, 70%, 60%)`;
}

/**
 * Clamp a number between min and max
 */
export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}
