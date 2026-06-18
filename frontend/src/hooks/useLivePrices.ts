'use client';

import { useEffect, useRef, useState, useCallback } from 'react';

export interface LivePrice {
  symbol: string;
  price: number;
  change24h: number;        // absolute change
  changePct24h: number;     // percentage
  high24h: number;
  low24h: number;
  volume24h: number;
}

type PriceMap = Record<string, LivePrice>;

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// Binance mini-ticker WebSocket for a list of crypto symbols
function buildBinanceStreamUrl(symbols: string[]): string {
  const streams = symbols.map((s) => `${s.toLowerCase()}@ticker`).join('/');
  return `wss://stream.binance.com:9443/stream?streams=${streams}`;
}

export function useLivePrices(symbols: string[]): PriceMap {
  const [prices, setPrices] = useState<PriceMap>({});
  const wsRef = useRef<WebSocket | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const cryptoSymbols = symbols.filter((s) => !s.includes('.'));
  const stockSymbols  = symbols.filter((s) =>  s.includes('.'));

  // ── Binance WebSocket ────────────────────────────────────────────────────
  const connectBinance = useCallback(() => {
    if (!cryptoSymbols.length) return;

    // Close existing connection
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
    }

    const ws = new WebSocket(buildBinanceStreamUrl(cryptoSymbols));
    wsRef.current = ws;

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data as string);
        const d = msg.data ?? msg; // combined stream wraps in {stream, data}
        if (!d?.s) return;

        const sym = (d.s as string).toUpperCase();
        setPrices((prev) => ({
          ...prev,
          [sym]: {
            symbol: sym,
            price:       parseFloat(d.c),
            change24h:   parseFloat(d.p),
            changePct24h: parseFloat(d.P),
            high24h:     parseFloat(d.h),
            low24h:      parseFloat(d.l),
            volume24h:   parseFloat(d.v),
          },
        }));
      } catch {
        // ignore parse errors
      }
    };

    ws.onerror = () => ws.close();

    // Reconnect on unexpected close
    ws.onclose = () => {
      setTimeout(connectBinance, 3000);
    };
  }, [cryptoSymbols.join(',')]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Yahoo/REST polling for stocks ────────────────────────────────────────
  const pollStocks = useCallback(async () => {
    if (!stockSymbols.length) return;
    try {
      const q = stockSymbols.join(',');
      const res = await fetch(`${API_URL}/api/v1/prices/tickers?symbols=${encodeURIComponent(q)}`);
      if (!res.ok) return;
      const data: Record<string, any> = await res.json();
      setPrices((prev) => {
        const updated = { ...prev };
        for (const [sym, ticker] of Object.entries(data)) {
          if (!ticker) continue;
          updated[sym] = {
            symbol: sym,
            price:       ticker.current_price ?? 0,
            change24h:   ticker.price_change_24h ?? 0,
            changePct24h: ticker.price_change_percentage_24h ?? 0,
            high24h:     ticker.high_24h ?? 0,
            low24h:      ticker.low_24h ?? 0,
            volume24h:   ticker.volume_24h ?? 0,
          };
        }
        return updated;
      });
    } catch {
      // network errors: silently retry next interval
    }
  }, [stockSymbols.join(','), API_URL]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    connectBinance();
    pollStocks();

    // Poll stocks every 30 seconds (Yahoo Finance delay is ~15-20s anyway)
    pollRef.current = setInterval(pollStocks, 30_000);

    return () => {
      wsRef.current?.close();
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [connectBinance, pollStocks]);

  return prices;
}
