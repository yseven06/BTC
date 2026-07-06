'use client';

import React, { useEffect, useRef, useState } from 'react';
import {
  createChart, ColorType, CrosshairMode, LineStyle,
  type IChartApi, type ISeriesApi, type CandlestickData, type SeriesMarker, type Time,
} from 'lightweight-charts';
import { fetchOhlcv, type OhlcvCandle } from '@/lib/api';
import { chartColor, withAlpha } from '@/lib/chartColors';

interface PriceLevel {
  price: number;
  color: string;
  title: string;
  style?: LineStyle;
}

interface PatternMarker {
  index: number;
  bias: 'bullish' | 'bearish';
  label: string;
}

// ─── Indicator math (computed client-side from the same OHLCV the chart draws) ──
function ema(values: number[], period: number): number[] {
  const k = 2 / (period + 1);
  const out: number[] = [];
  let prev = values[0];
  values.forEach((v, i) => {
    prev = i === 0 ? v : v * k + prev * (1 - k);
    out.push(prev);
  });
  return out;
}

function macd(closes: number[]): { macdLine: number[]; signalLine: number[]; histogram: number[] } {
  const ema12 = ema(closes, 12);
  const ema26 = ema(closes, 26);
  const macdLine = ema12.map((v, i) => v - ema26[i]);
  const signalLine = ema(macdLine, 9);
  const histogram = macdLine.map((v, i) => v - signalLine[i]);
  return { macdLine, signalLine, histogram };
}

// ─── Per-engine: build price levels + markers from supporting_data ──────────
function buildOverlay(engineName: string, sd: any): { levels: PriceLevel[]; markers: PatternMarker[] } {
  const levels: PriceLevel[] = [];
  const markers: PatternMarker[] = [];
  if (!sd) return { levels, markers };
  // Renk migration (P9.5/D9-07): owned tek-kaynak (chartColors runtime-resolve).
  // FVG = cyan-sınır tek dil (COL-05/07: cyan yalnız çizgi-iz; pembe #f472b6
  // EMEKLİ — 3.-renk salgını); yön bilgisi title + Dashed stille korunur.
  const bull = chartColor('bull'), bear = chartColor('bear');
  const tx2 = chartColor('tx2'), cyan = chartColor('cyan');

  if (engineName === 'market_structure') {
    for (const lv of (sd.horizontal_sr ?? []).slice(0, 4)) {
      const isSupport = lv.type === 'support';
      levels.push({
        price: lv.price,
        color: isSupport ? bull : bear,
        title: `${isSupport ? 'Destek' : 'Direnç'} (g:${Math.round(lv.strength)})`,
      });
    }
    for (const lv of (sd.fibonacci ?? []).slice(0, 4)) {
      levels.push({ price: lv.price, color: tx2, title: lv.label, style: LineStyle.Dotted });
    }
  }

  if (engineName === 'smart_money_concepts') {
    const pd = sd.premium_discount;
    if (pd) {
      if (pd.swing_high) levels.push({ price: pd.swing_high, color: bear, title: 'Prim üst', style: LineStyle.Dashed });
      if (pd.equilibrium) levels.push({ price: pd.equilibrium, color: tx2, title: 'Denge', style: LineStyle.Dotted });
      if (pd.swing_low) levels.push({ price: pd.swing_low, color: bull, title: 'İskonto alt', style: LineStyle.Dashed });
    }
    const zone = (arr: any[], color: string, label: string) => {
      for (const z of (arr ?? []).slice(0, 2)) {
        levels.push({ price: z.high, color, title: `${label} üst`, style: LineStyle.Dashed });
        levels.push({ price: z.low, color, title: `${label} alt`, style: LineStyle.Dashed });
      }
    };
    zone(sd.unmitigated_bullish_ob, bull, 'OB');
    zone(sd.unmitigated_bearish_ob, bear, 'OB');
    zone(sd.unfilled_bullish_fvg, cyan, 'FVG');
    zone(sd.unfilled_bearish_fvg, cyan, 'FVG');
  }

  if (engineName === 'candle_range_theory') {
    const rp = sd.range_position;
    if (rp?.htf_high) levels.push({ price: rp.htf_high, color: bear, title: 'HTF Üst' });
    if (rp?.htf_low) levels.push({ price: rp.htf_low, color: bull, title: 'HTF Alt' });
  }

  if (engineName === 'technical_analysis') {
    for (const p of (sd.patterns ?? []).slice(0, 6)) {
      if (typeof p.index !== 'number') continue;
      markers.push({ index: p.index, bias: p.type === 'bearish' ? 'bearish' : 'bullish', label: p.name ?? '' });
    }
  }

  return { levels, markers };
}

const SUPPORTS_MACD = new Set(['technical_analysis']);

interface EngineMiniChartProps {
  symbol: string;
  timeframe: string;
  engineName: string;
  supportingData: any;
}

export function EngineMiniChart({ symbol, timeframe, engineName, supportingData }: EngineMiniChartProps) {
  const [candles, setCandles] = useState<OhlcvCandle[] | null>(null);
  const [error, setError] = useState(false);
  const priceRef = useRef<HTMLDivElement>(null);
  const macdRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    // 100 candles — must match the backend engine pipeline's fetch limit
    // (scheduler.py fetch_ohlcv(..., limit=100)) so pattern.candle_index
    // (an index into that same 100-bar window) lines up with this array.
    fetchOhlcv(symbol, timeframe, 100)
      .then((r) => { if (!cancelled) setCandles(r.candles); })
      .catch(() => { if (!cancelled) setError(true); });
    return () => { cancelled = true; };
  }, [symbol, timeframe]);

  useEffect(() => {
    if (!priceRef.current || !candles || candles.length === 0) return;

    // Owned chart-token'lar (P9.5): eksen tx2 (DoD ≥tx2), grid hl10, sınır hl16.
    const C = {
      tx2: chartColor('tx2'), hl10: chartColor('hl10'), hl16: chartColor('hl16'),
      bull: chartColor('bull'), bear: chartColor('bear'),
      accentUi: chartColor('accentUi'), amber: chartColor('amber'),
    };

    const chart = createChart(priceRef.current, {
      width: priceRef.current.clientWidth,
      height: 460,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: C.tx2, fontSize: 11 },
      grid: { vertLines: { color: C.hl10 }, horzLines: { color: C.hl10 } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: C.hl16 },
      timeScale: { borderColor: C.hl16, timeVisible: true, secondsVisible: false },
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor: C.bull, downColor: C.bear,
      borderUpColor: C.bull, borderDownColor: C.bear,
      wickUpColor: C.bull, wickDownColor: C.bear,
    });

    const data: CandlestickData[] = candles.map((c) => ({
      time: c.time as any, open: c.open, high: c.high, low: c.low, close: c.close,
    }));
    candleSeries.setData(data);

    const { levels, markers } = buildOverlay(engineName, supportingData);
    for (const lv of levels) {
      candleSeries.createPriceLine({
        price: lv.price, color: lv.color, lineWidth: 1,
        lineStyle: lv.style ?? LineStyle.Solid, axisLabelVisible: true, title: lv.title,
      });
    }
    if (markers.length > 0) {
      const seriesMarkers: SeriesMarker<Time>[] = markers
        .filter((m) => m.index >= 0 && m.index < candles.length)
        .map((m) => ({
          time: candles[m.index].time as any,
          position: m.bias === 'bullish' ? 'belowBar' : 'aboveBar',
          color: m.bias === 'bullish' ? C.bull : C.bear,
          shape: m.bias === 'bullish' ? 'arrowUp' : 'arrowDown',
          text: m.label,
        }));
      candleSeries.setMarkers(seriesMarkers);
    }

    chart.timeScale().fitContent();

    let macdChart: IChartApi | null = null;
    if (SUPPORTS_MACD.has(engineName) && macdRef.current && candles.length > 30) {
      macdChart = createChart(macdRef.current, {
        width: macdRef.current.clientWidth,
        height: 160,
        layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: C.tx2, fontSize: 11 },
        grid: { vertLines: { color: C.hl10 }, horzLines: { color: C.hl10 } },
        rightPriceScale: { borderColor: C.hl16 },
        timeScale: { borderColor: C.hl16, timeVisible: true, secondsVisible: false },
      });
      const { histogram, macdLine, signalLine } = macd(candles.map((c) => c.close));
      const histSeries = macdChart.addHistogramSeries({ priceFormat: { type: 'volume' } });
      // Histogram bull/bear @.6 alfa (eski rgba(16,185,129)/(244,85,110) emekli).
      const histUp = withAlpha(C.bull, 0.6), histDown = withAlpha(C.bear, 0.6);
      histSeries.setData(candles.map((c, i) => ({
        time: c.time as any, value: histogram[i], color: histogram[i] >= 0 ? histUp : histDown,
      })));
      // MACD çizgisi accent-ui iz (#378ADD 4.-mavi emekli); sinyal çizgisi amber (#f59e0b orange emekli).
      const macdSeries = macdChart.addLineSeries({ color: C.accentUi, lineWidth: 1 });
      macdSeries.setData(candles.map((c, i) => ({ time: c.time as any, value: macdLine[i] })));
      const sigSeries = macdChart.addLineSeries({ color: C.amber, lineWidth: 1 });
      sigSeries.setData(candles.map((c, i) => ({ time: c.time as any, value: signalLine[i] })));
      macdChart.timeScale().fitContent();
    }

    const resize = () => {
      if (priceRef.current) chart.applyOptions({ width: priceRef.current.clientWidth });
      if (macdChart && macdRef.current) macdChart.applyOptions({ width: macdRef.current.clientWidth });
    };
    window.addEventListener('resize', resize);

    return () => {
      window.removeEventListener('resize', resize);
      chart.remove();
      macdChart?.remove();
    };
  }, [candles, engineName, supportingData]);

  if (error) return <p className="text-[11px] text-text-muted text-center py-3">Grafik yüklenemedi.</p>;
  if (!candles) {
    // Must match the real chart's final height (460 price + 160 MACD for
    // engines that render one) — otherwise the panel grows the instant
    // candles arrive, shifting everything below it (the "Bulgular" toggle)
    // down just as a user clicks it, swallowing the click.
    const placeholderHeight = SUPPORTS_MACD.has(engineName) ? 460 + 160 + 4 : 460;
    return (
      <div className="flex justify-center items-center" style={{ height: placeholderHeight }}>
        <div className="w-5 h-5 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="bg-bg-secondary/60 rounded-xl border border-border-subtle p-2">
      <div ref={priceRef} />
      {SUPPORTS_MACD.has(engineName) && <div ref={macdRef} className="mt-1" />}
    </div>
  );
}
