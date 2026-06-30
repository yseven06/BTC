'use client';

import React, { useCallback, useEffect, useRef } from 'react';
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
  /** Unix seconds the signal was generated at. The Giriş/SL/TP lines are
   * drawn flat across the whole visible range (lightweight-charts price
   * lines aren't time-bounded) — without a marker here, price action from
   * *before* the signal existed reads as if it happened against these
   * levels, which is misleading (e.g. a pre-signal dip below the SL price
   * looks like a stop-out that never actually happened). */
  generatedAt?: number | null;
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
  // Amber segment marking the signal price, anchored at its LEFT end to the
  // signal-start candle (see the marker effect below).
  const signalLineRef = useRef<ISeriesApi<'Line'> | null>(null);
  // HTML price chip pinned exactly at the signal point (the left dot). An
  // above-bar marker can't sit at an arbitrary price, so the price label is a
  // DOM overlay positioned from chart coordinates and kept in sync on pan/zoom.
  const labelRef = useRef<HTMLDivElement | null>(null);
  // Vertical dashed line calling out WHICH candle is the signal (a horizontal
  // line couldn't — it crossed later candles).
  const vLineRef = useRef<HTMLDivElement | null>(null);
  const signalAnchorRef = useRef<{ time: number; price: number; text: string } | null>(null);
  // Last applied chip state, so the per-frame loop only touches the DOM when the
  // position actually moved (idle frames are a couple of cheap coordinate reads).
  const lastPosRef = useRef<string | null>(null);

  // Reposition the price chip onto the signal point using current chart
  // coordinates. Stable (reads refs only). Called every animation frame so the
  // chip stays glued through zoom/pan even while lightweight-charts animates the
  // view across several frames (a one-shot read lands on an intermediate frame).
  const updateSignalLabel = useCallback(() => {
    const chart = chartRef.current;
    const series = candleSeriesRef.current;
    const label = labelRef.current;
    const vline = vLineRef.current;
    if (!chart || !series || !label || !vline) return;
    const anchor = signalAnchorRef.current;
    const hide = () => {
      if (lastPosRef.current !== null) {
        label.style.display = 'none';
        vline.style.display = 'none';
        lastPosRef.current = null;
      }
    };
    if (!anchor) { hide(); return; }
    const x = chart.timeScale().timeToCoordinate(anchor.time as any);
    const y = series.priceToCoordinate(anchor.price);
    if (x == null || y == null) { hide(); return; }
    const key = `${anchor.text}|${Math.round(x)}|${Math.round(y)}`;
    if (key === lastPosRef.current) return;  // nothing moved this frame
    lastPosRef.current = key;
    // Vertical line marks the candle (x only — full height via CSS).
    vline.style.display = 'block';
    vline.style.left = `${x}px`;
    // Chip pinned at the exact price point on that candle.
    label.textContent = anchor.text;
    label.style.display = 'block';
    label.style.left = `${x}px`;
    label.style.top = `${y}px`;
  }, []);
  // Only auto-fit the view on the very first data load. The parent polls
  // for fresh candles every 30s — calling fitContent() on every refresh
  // snapped the chart back to the default view a few seconds after a user
  // panned/zoomed, making manual navigation feel broken.
  const hasFitOnceRef = useRef(false);

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

    // A thin amber line series used to draw ONLY the signal-price segment
    // (from the signal-start candle rightward). Added after the candles so it
    // sits on top. No price line / last-value label → it never crowds the
    // right-axis Giriş/SL/TP labels, even when the signal price hugs the entry.
    const signalLine = chart.addLineSeries({
      color: '#fbbf24',
      lineWidth: 3,
      lineStyle: LineStyle.Solid,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
      pointMarkersVisible: true,
      pointMarkersRadius: 4,
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    signalLineRef.current = signalLine;

    // Resize handler
    const resize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
      }
      requestAnimationFrame(updateSignalLabel);
    };
    window.addEventListener('resize', resize);

    return () => {
      window.removeEventListener('resize', resize);
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      signalLineRef.current = null;
    };
    // Mount-once: `height` is read here only as the initial value. Putting
    // it in the dependency array (as before) tore down and recreated the
    // whole chart — including the candle series — every time the parent
    // changed height (e.g. toggling fullscreen), and since `candles` itself
    // hadn't changed, the data-sync effect below never re-ran to repopulate
    // the brand-new empty series. The chart looked blank until a refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keep the signal price chip pinned to its point every frame. lightweight-
  // charts has no "viewport changed" event that covers wheel-zoom, axis-drag
  // zoom AND price-scale rescale together, and it animates the view over several
  // frames — so a per-frame reposition is the only thing that never drifts. The
  // body early-returns cheaply when nothing moved, so idle frames are ~free.
  useEffect(() => {
    let rafId = requestAnimationFrame(function tick() {
      updateSignalLabel();
      rafId = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(rafId);
  }, [updateSignalLabel]);

  // Resize an already-mounted chart when the parent changes `height`
  // (e.g. fullscreen toggle) without tearing down the series/data. Width
  // must be re-read here too — the container only grows because a CSS
  // class flipped (fullscreen overlay), not because the browser window
  // itself resized, so the regular `window.resize` listener never fires.
  useEffect(() => {
    chartRef.current?.applyOptions({
      height,
      width: containerRef.current?.clientWidth,
    });
    requestAnimationFrame(updateSignalLabel);
  }, [height, updateSignalLabel]);

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
    const precision = lastPrice >= 100 ? 2 : lastPrice >= 1 ? 4 : lastPrice >= 0.01 ? 4 : lastPrice >= 0.0001 ? 6 : 8;
    candleSeriesRef.current.applyOptions({
      priceFormat: { type: 'price', precision, minMove: 1 / 10 ** precision },
    });

    candleSeriesRef.current.setData(data);
    if (!hasFitOnceRef.current) {
      // fitContent() crams all 200 fetched candles into view, which makes
      // recent price action (and the signal-start marker) too cramped to
      // read. Show roughly the last ~5 days instead, centered on the latest
      // candle (equal empty space on the right as candles on display, so
      // the most recent candle sits near the middle, not pinned to an edge).
      // Deferred a tick — right after setData() the timeScale hasn't laid
      // out yet and setVisibleLogicalRange is silently a no-op.
      const visibleCount = Math.min(120, candles.length);
      const halfSpan = visibleCount / 2;
      requestAnimationFrame(() => {
        chartRef.current?.timeScale().setVisibleLogicalRange({
          from: candles.length - halfSpan,
          to: candles.length + halfSpan,
        });
      });
      hasFitOnceRef.current = true;
    }
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

  // Mark the candle where the signal actually started. The Giriş/SL/TP
  // lines above are drawn flat across the whole visible range — without
  // this marker, price action from before the signal existed reads as if
  // it happened against those levels (e.g. a pre-signal dip below the SL
  // price looks like a stop-out that never actually happened).
  useEffect(() => {
    if (!candleSeriesRef.current) return;
    const series = candleSeriesRef.current;
    if (!signal?.generatedAt || candles.length === 0) {
      series.setMarkers([]);
      signalLineRef.current?.setData([]);
      signalAnchorRef.current = null;
      updateSignalLabel();
      return;
    }
    // Anchor the marker to the candle that CONTAINS the signal time, not the
    // next one. candle.time is the bar's OPEN (UTC); signals are minted
    // mid-bar, so the old `c.time >= generatedAt` skipped the containing bar
    // and landed on the following one — off by a full bar (a whole day on 1D).
    // The right bar is the last one whose open is <= generatedAt.
    // Fallback: a signal newer than the last fetched candle (OHLCV polling and
    // signal generation aren't perfectly in sync) still anchors to the latest
    // bar rather than not rendering at all.
    const gen = signal.generatedAt!;
    const nextIdx = candles.findIndex((c) => c.time > gen);
    const startIdx = nextIdx === -1
      ? candles.length - 1            // signal at/after the last bar's open
      : Math.max(0, nextIdx - 1);     // the bar that contains the signal
    const startCandle = candles[startIdx];
    if (!startCandle) {
      series.setMarkers([]);
      signalLineRef.current?.setData([]);
      signalAnchorRef.current = null;
      updateSignalLabel();
      return;
    }
    // The exact market price at signal time = the close of the bar that
    // contained generatedAt. A bare above-bar arrow can't sit at a price (so
    // "top or bottom of the candle?" stayed ambiguous); instead the segment's
    // left dot marks the point and an HTML price chip is pinned right on it.
    const signalPrice = startCandle.close;
    const p = signalPrice >= 100 ? 2 : signalPrice >= 0.01 ? 4 : signalPrice >= 0.0001 ? 6 : 8;
    const priceStr = signalPrice.toLocaleString('tr-TR', {
      minimumFractionDigits: p, maximumFractionDigits: p,
    });
    // No above-bar arrow anymore — clear any from a prior render.
    series.setMarkers([]);

    // Mark the signal with a SINGLE dot at its exact point. A rightward
    // horizontal segment was ambiguous once zoomed (it crossed later candles,
    // so "which candle gave the signal?" was unclear); the candle is now called
    // out by the vertical line overlay instead (see updateSignalLabel).
    signalLineRef.current?.setData([{ time: startCandle.time as any, value: signalPrice }]);

    // Pin the chip + vertical line onto the signal point.
    signalAnchorRef.current = { time: startCandle.time, price: signalPrice, text: `Sinyal · ${priceStr}` };
    requestAnimationFrame(updateSignalLabel);
  }, [signal?.generatedAt, candles, updateSignalLabel]);

  return (
    <div className="relative">
      <div ref={containerRef} style={{ width: '100%', height }} />
      {/* Vertical dashed line marking the signal candle (left set imperatively).
          Stops above the time axis. Identifies WHICH candle unambiguously. */}
      <div
        ref={vLineRef}
        style={{
          display: 'none',
          position: 'absolute',
          top: 0,
          bottom: '24px',
          left: 0,
          width: 0,
          borderLeft: '1.5px dashed rgba(251, 191, 36, 0.55)',
          transform: 'translateX(-0.75px)',
          pointerEvents: 'none',
          zIndex: 4,
        }}
      />
      {/* Price chip pinned to the signal point (left dot). Positioned from
          chart coordinates (left/top set imperatively); the transform parks it
          just left of and vertically centered on the dot. */}
      <div
        ref={labelRef}
        style={{
          display: 'none',
          position: 'absolute',
          left: 0,
          top: 0,
          transform: 'translate(calc(-100% - 10px), -50%)',
          background: '#fbbf24',
          color: '#1f2937',
          fontSize: '11px',
          fontWeight: 700,
          lineHeight: 1,
          padding: '3px 7px',
          borderRadius: '5px',
          whiteSpace: 'nowrap',
          pointerEvents: 'none',
          zIndex: 5,
        }}
      />
    </div>
  );
}
