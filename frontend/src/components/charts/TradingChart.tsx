'use client';

import React, { useEffect, useRef } from 'react';
import {
  createChart, ColorType, CrosshairMode, LineStyle,
  type IChartApi, type ISeriesApi, type CandlestickData,
} from 'lightweight-charts';

export interface ChartCandle {
  time:   number;   // unix seconds (UTC, from backend)
  open:   number;
  high:   number;
  low:    number;
  close:  number;
  volume: number;
}

// ─── Europe/Istanbul timezone helpers ────────────────────────────────────────
const TR_TZ = 'Europe/Istanbul';

const trDateTimeFmt = new Intl.DateTimeFormat('tr-TR', {
  timeZone: TR_TZ,
  day: '2-digit', month: '2-digit', year: 'numeric',
  hour: '2-digit', minute: '2-digit',
});
const trTimeFmt = new Intl.DateTimeFormat('tr-TR', {
  timeZone: TR_TZ, hour: '2-digit', minute: '2-digit',
});
const trDateFmt = new Intl.DateTimeFormat('tr-TR', {
  timeZone: TR_TZ, day: '2-digit', month: 'short',
});
const trMonthFmt = new Intl.DateTimeFormat('tr-TR', {
  timeZone: TR_TZ, month: 'short', year: 'numeric',
});

/** Format unix seconds → human-friendly Istanbul-local label. */
function formatTRTime(unixSeconds: number): string {
  return trDateTimeFmt.format(new Date(unixSeconds * 1000));
}

export interface SignalLevels {
  entryLow?:  number | null;
  entryHigh?: number | null;
  stopLoss?:  number | null;
  tp1?:       number | null;
  tp2?:       number | null;
  tp3?:       number | null;
  direction?: 'long' | 'short';
}

interface TradingChartProps {
  candles:  ChartCandle[];
  signal?:  SignalLevels;
  height?:  number;
}

/**
 * Professional candlestick chart powered by TradingView's free
 * lightweight-charts library. Overlays trade signal levels (entry zone,
 * stop loss, take-profits) directly on the chart for instant context.
 */
export function TradingChart({ candles, signal, height = 480 }: TradingChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);

  // Initialize chart once
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor:  '#94a3b8',
        fontFamily: 'system-ui, -apple-system, sans-serif',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: 'rgba(148, 163, 184, 0.06)' },
        horzLines: { color: 'rgba(148, 163, 184, 0.06)' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: '#f97316', width: 1, style: LineStyle.Dashed, labelBackgroundColor: '#f97316' },
        horzLine: { color: '#f97316', width: 1, style: LineStyle.Dashed, labelBackgroundColor: '#f97316' },
      },
      rightPriceScale: {
        borderColor: 'rgba(148, 163, 184, 0.15)',
      },
      // Crosshair tooltip + bottom-edge time label: Türkiye saati (Europe/Istanbul)
      localization: {
        locale: 'tr-TR',
        timeFormatter: (time: any) => {
          const sec = typeof time === 'number' ? time : Number(time);
          return formatTRTime(sec);
        },
      },
      timeScale: {
        borderColor: 'rgba(148, 163, 184, 0.15)',
        timeVisible: true,
        secondsVisible: false,
        // X-axis tick labels: gün/saat formatları Türkiye saatine göre
        tickMarkFormatter: (time: any, tickMarkType: number) => {
          const sec = typeof time === 'number' ? time : Number(time);
          const d = new Date(sec * 1000);
          // tickMarkType: 0=Year, 1=Month, 2=DayOfMonth, 3=Time, 4=TimeWithSeconds
          if (tickMarkType === 0) return trMonthFmt.format(d).split(' ')[1] ?? '';
          if (tickMarkType === 1) return trMonthFmt.format(d);
          if (tickMarkType === 2) return trDateFmt.format(d);
          return trTimeFmt.format(d);
        },
      },
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor:        '#10B981',
      downColor:      '#EF4444',
      borderUpColor:  '#10B981',
      borderDownColor: '#EF4444',
      wickUpColor:    '#10B981',
      wickDownColor:  '#EF4444',
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;

    // Resize handler
    const resize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', resize);

    return () => {
      window.removeEventListener('resize', resize);
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
    };
  }, [height]);

  // Update candles when data changes
  useEffect(() => {
    if (!candleSeriesRef.current || candles.length === 0) return;
    const data: CandlestickData[] = candles.map((c) => ({
      time: c.time as any,
      open: c.open, high: c.high, low: c.low, close: c.close,
    }));

    // Price axis + price-line labels (TP/SL/Giriş) default to too few decimals
    // for sub-$1 assets — match the Trade Plan ladder's precision (4 decimals
    // there) by sizing precision to the asset's actual price magnitude.
    const lastPrice = candles[candles.length - 1].close;
    const precision = lastPrice >= 100 ? 2 : lastPrice >= 1 ? 4 : lastPrice >= 0.01 ? 4 : 6;
    candleSeriesRef.current.applyOptions({
      priceFormat: { type: 'price', precision, minMove: 1 / 10 ** precision },
    });

    candleSeriesRef.current.setData(data);
    chartRef.current?.timeScale().fitContent();
  }, [candles]);

  // Draw signal levels (entry / SL / TP lines)
  useEffect(() => {
    if (!candleSeriesRef.current || !signal) return;
    const series = candleSeriesRef.current;
    const created: ReturnType<ISeriesApi<'Candlestick'>['createPriceLine']>[] = [];

    const addLine = (price: number | null | undefined, opts: {
      color: string; title: string; lineStyle?: LineStyle;
    }) => {
      if (price == null || !isFinite(price)) return;
      const line = series.createPriceLine({
        price,
        color: opts.color,
        lineWidth: 2,
        lineStyle: opts.lineStyle ?? LineStyle.Solid,
        axisLabelVisible: true,
        title: opts.title,
      });
      created.push(line);
    };

    addLine(signal.entryLow,  { color: '#f97316', title: 'Giriş ↓', lineStyle: LineStyle.Dotted });
    addLine(signal.entryHigh, { color: '#f97316', title: 'Giriş ↑', lineStyle: LineStyle.Dotted });
    addLine(signal.stopLoss,  { color: '#EF4444', title: 'SL' });
    addLine(signal.tp1,       { color: '#10B981', title: 'TP1' });
    addLine(signal.tp2,       { color: '#10B981', title: 'TP2' });
    addLine(signal.tp3,       { color: '#10B981', title: 'TP3' });

    return () => {
      for (const line of created) series.removePriceLine(line);
    };
  }, [signal]);

  return (
    <div className="relative">
      <div ref={containerRef} style={{ width: '100%', height }} />
    </div>
  );
}
