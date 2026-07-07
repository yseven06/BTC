'use client';

import React, { useEffect, useState } from 'react';
import { cn, formatCurrency, formatPercentage } from '@/lib/utils';
import type { TickerItem } from '@/types';

// Symbols to display and their display labels
const TICKER_SYMBOLS: Array<{ binanceSymbol: string; label: string }> = [
  { binanceSymbol: 'BTCUSDT', label: 'BTC' },
  { binanceSymbol: 'ETHUSDT', label: 'ETH' },
  { binanceSymbol: 'SOLUSDT', label: 'SOL' },
  { binanceSymbol: 'BNBUSDT', label: 'BNB' },
  { binanceSymbol: 'XRPUSDT', label: 'XRP' },
  { binanceSymbol: 'ADAUSDT', label: 'ADA' },
  { binanceSymbol: 'AVAXUSDT', label: 'AVAX' },
  { binanceSymbol: 'DOGEUSDT', label: 'DOGE' },
];

// Fallback data when the API is unavailable
const FALLBACK: TickerItem[] = [
  { symbol: 'BTC', name: 'Bitcoin', price: 0, change: 0, changePercent: 0 },
  { symbol: 'ETH', name: 'Ethereum', price: 0, change: 0, changePercent: 0 },
  { symbol: 'SOL', name: 'Solana', price: 0, change: 0, changePercent: 0 },
  { symbol: 'BNB', name: 'BNB', price: 0, change: 0, changePercent: 0 },
  { symbol: 'XRP', name: 'Ripple', price: 0, change: 0, changePercent: 0 },
  { symbol: 'ADA', name: 'Cardano', price: 0, change: 0, changePercent: 0 },
  { symbol: 'AVAX', name: 'Avalanche', price: 0, change: 0, changePercent: 0 },
  { symbol: 'DOGE', name: 'Dogecoin', price: 0, change: 0, changePercent: 0 },
];

async function fetchBinanceTickers(): Promise<TickerItem[]> {
  const symbols = JSON.stringify(TICKER_SYMBOLS.map((s) => `"${s.binanceSymbol}"`).join(','));
  const url = `https://api.binance.com/api/v3/ticker/24hr?symbols=[${TICKER_SYMBOLS.map((s) => `"${s.binanceSymbol}"`).join(',')}]`;
  const res = await fetch(url, { next: { revalidate: 0 } });
  if (!res.ok) throw new Error('Binance API error');

  const data: Array<{
    symbol: string;
    lastPrice: string;
    priceChange: string;
    priceChangePercent: string;
  }> = await res.json();

  return data.map((d) => {
    const meta = TICKER_SYMBOLS.find((s) => s.binanceSymbol === d.symbol);
    return {
      symbol: meta?.label ?? d.symbol.replace('USDT', ''),
      name: meta?.label ?? d.symbol,
      price: parseFloat(d.lastPrice),
      change: parseFloat(d.priceChange),
      changePercent: parseFloat(d.priceChangePercent),
    };
  });
}

function TickerItemDisplay({ item }: { item: TickerItem }) {
  const isPositive = item.changePercent >= 0;

  return (
    <div className="flex items-center gap-2.5 px-4 py-1 cursor-default group">
      <span className="text-xs font-display text-text-primary group-hover:text-accent-primary transition-colors whitespace-nowrap">
        {item.symbol}
      </span>
      <span className="text-xs num font-num-480 text-text-secondary whitespace-nowrap">
        {item.price === 0
          ? '—'
          : item.symbol.includes('/')
          ? item.price.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
          : formatCurrency(item.price)}
      </span>
      {item.price !== 0 && (
        <span
          className={cn(
            'text-[11px] num font-num-520 whitespace-nowrap',
            isPositive ? 'text-bullish' : 'text-bearish'
          )}
        >
          {formatPercentage(item.changePercent)}
        </span>
      )}
      <div className="w-px h-3 bg-border-subtle mx-1" />
    </div>
  );
}

export default function TickerBand() {
  const [tickerData, setTickerData] = useState<TickerItem[]>(FALLBACK);

  useEffect(() => {
    let cancelled = false;

    async function refresh() {
      try {
        const data = await fetchBinanceTickers();
        if (!cancelled) setTickerData(data);
      } catch {
        // Keep current data on error — silent fail
      }
    }

    refresh();
    const interval = setInterval(refresh, 30_000); // refresh every 30s
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const items = [...tickerData, ...tickerData];

  return (
    <div className="w-full overflow-hidden bg-bg-secondary/50 border-b border-border-subtle relative">
      {/* Left fade gradient */}
      <div className="absolute left-0 top-0 bottom-0 w-12 bg-gradient-to-r from-bg-secondary/80 to-transparent z-10 pointer-events-none" />
      {/* Right fade gradient */}
      <div className="absolute right-0 top-0 bottom-0 w-12 bg-gradient-to-l from-bg-secondary/80 to-transparent z-10 pointer-events-none" />

      <div className="ticker-animate flex items-center h-8">
        {items.map((item, index) => (
          <TickerItemDisplay key={`${item.symbol}-${index}`} item={item} />
        ))}
      </div>
    </div>
  );
}
