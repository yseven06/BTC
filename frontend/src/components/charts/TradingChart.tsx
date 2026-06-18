'use client';

import React, { useEffect, useRef } from 'react';
import {
  createChart, ColorType, CrosshairMode, LineStyle,
  type IChartApi, type ISeriesApi, type CandlestickData,
} from 'lightweight-charts';

export interface ChartCandle {
  time:   number;   // unix seconds
  open:   number;
  high:   number;
  low:    number;
  close:  number;
  volume: number;
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
      timeScale: {
        borderColor: 'rgba(148, 163, 184, 0.15)',
        timeVisible: true,
        secondsVisible: false,
      },
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor:        '#00e676',
      downColor:      '#ff5252',
      borderUpColor:  '#00e676',
      borderDownColor: '#ff5252',
      wickUpColor:    '#00e676',
      wickDownColor:  '#ff5252',
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
    addLine(signal.stopLoss,  { color: '#ff5252', title: 'SL' });
    addLine(signal.tp1,       { color: '#00e676', title: 'TP1' });
    addLine(signal.tp2,       { color: '#00e676', title: 'TP2' });
    addLine(signal.tp3,       { color: '#00e676', title: 'TP3' });

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
