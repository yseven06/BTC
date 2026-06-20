'use client';

import React, { useEffect, useRef, useId } from 'react';
import { toTradingViewSymbol, toTradingViewInterval } from '@/lib/tradingview';

interface TradingViewChartProps {
  symbol: string;
  assetType?: string;
  timeframe?: string;
  /** Chart height in px. Default 500. */
  height?: number;
  /** Technical studies to preload, e.g. ['RSI@tv-basicstudies']. */
  studies?: string[];
  /** Compact mode hides side toolbar and details. */
  compact?: boolean;
}

// Minimal global typing for the TradingView embed script
declare global {
  interface Window {
    TradingView?: {
      widget: new (config: Record<string, unknown>) => unknown;
    };
  }
}

const TV_SCRIPT_SRC = 'https://s3.tradingview.com/tv.js';
const DEFAULT_STUDIES = ['RSI@tv-basicstudies', 'MACD@tv-basicstudies'];
let scriptPromise: Promise<void> | null = null;

/** Load the tv.js script once and cache the promise. */
function loadTradingViewScript(): Promise<void> {
  if (typeof window === 'undefined') return Promise.resolve();
  if (window.TradingView) return Promise.resolve();
  if (scriptPromise) return scriptPromise;

  scriptPromise = new Promise<void>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${TV_SCRIPT_SRC}"]`);
    if (existing) {
      existing.addEventListener('load', () => resolve());
      existing.addEventListener('error', () => reject(new Error('tv.js failed')));
      return;
    }
    const script = document.createElement('script');
    script.src = TV_SCRIPT_SRC;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error('tv.js failed'));
    document.head.appendChild(script);
  });

  return scriptPromise;
}

export default function TradingViewChart({
  symbol,
  assetType,
  timeframe,
  height = 500,
  studies = DEFAULT_STUDIES,
  compact = false,
}: TradingViewChartProps) {
  const reactId = useId().replace(/[:]/g, '');
  const containerId = `tv_chart_${reactId}`;
  const containerRef = useRef<HTMLDivElement>(null);
  // Serialize studies so the effect doesn't re-run on every parent render
  const studiesKey = studies.join(',');

  useEffect(() => {
    let cancelled = false;

    loadTradingViewScript()
      .then(() => {
        if (cancelled || !window.TradingView || !containerRef.current) return;

        // Clear any previous widget instance
        containerRef.current.innerHTML = '';

        new window.TradingView.widget({
          container_id: containerId,
          symbol: toTradingViewSymbol(symbol, assetType),
          interval: toTradingViewInterval(timeframe),
          timezone: 'Europe/Istanbul',
          theme: 'dark',
          style: '1', // candlesticks
          locale: 'tr',
          toolbar_bg: '#020817',
          enable_publishing: false,
          allow_symbol_change: !compact,
          hide_side_toolbar: compact,
          hide_top_toolbar: compact,
          withdateranges: !compact,
          studies: compact ? [] : studies,
          autosize: true,
          backgroundColor: '#020817',
          gridColor: 'rgba(148, 163, 184, 0.06)',
        });
      })
      .catch(() => {
        if (containerRef.current) {
          containerRef.current.innerHTML =
            '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#64748b;font-size:13px;">Grafik yüklenemedi</div>';
        }
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, assetType, timeframe, containerId, compact, studiesKey, height]);

  return (
    <div
      className="w-full overflow-hidden rounded-xl border border-border-subtle bg-bg-primary"
      style={{ height }}
    >
      <div id={containerId} ref={containerRef} style={{ height: '100%', width: '100%' }} />
    </div>
  );
}
