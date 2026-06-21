'use client';

import React, { useState, useEffect } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { ArrowLeft, TrendingUp, TrendingDown, Target, Shield, Zap, ExternalLink, Code2, Check } from 'lucide-react';
import { toTradingViewSymbol } from '@/lib/tradingview';
import { GlassCard } from '@/components/ui/GlassCard';
import { SignalBadge } from '@/components/ui/SignalBadge';
import { ScoreRing } from '@/components/ui/ScoreRing';
import TradingViewChart from '@/components/charts/TradingViewChart';
import { TradingChart, type ChartCandle } from '@/components/charts/TradingChart';
import { fetchActiveSignals, fetchOhlcv, type ApiSignal } from '@/lib/api';
import { useLivePrices } from '@/hooks/useLivePrices';
import { SignalType } from '@/types';
import { cn } from '@/lib/utils';
import { SignalDetailSection } from '@/components/ui/SignalDetailSection';

/**
 * Builds a Pine Script v5 indicator that draws the signal's entry/SL/TP
 * levels as horizontal lines WITH persistent on-chart text labels.
 * TradingView's real site doesn't accept custom drawings via URL
 * (anti-abuse), so this is the only way to get our levels onto the user's
 * own actual TradingView chart — they paste this into the Pine Editor and
 * add it as an indicator.
 *
 * hline() alone only shows its title on hover, not as visible chart text —
 * so each level also gets a label.new() pinned to the last bar. The
 * var-declared label is deleted and recreated each time barstate.islast is
 * true, otherwise Pine would spawn a new label on every realtime tick.
 */
function buildPineScript(symbol: string, signal: ApiSignal): string {
  const hlines: string[] = [];
  const labelDecls: string[] = [];
  const labelAssigns: string[] = [];

  const addLevel = (price: number | null | undefined, varName: string, title: string, color: string, style?: string) => {
    if (price == null || !isFinite(price)) return;
    const styleArg = style ? `, linestyle=${style}` : '';
    hlines.push(`hline(${price}, "${title}", color=color.new(${color}, 0), linewidth=2${styleArg})`);
    labelDecls.push(`var label lbl_${varName} = na`);
    labelAssigns.push(
      `    if not na(lbl_${varName})\n` +
      `        label.delete(lbl_${varName})\n` +
      `    lbl_${varName} := label.new(bar_index, ${price}, "${title}  ${price}", style=label.style_label_left, color=color.new(${color}, 0), textcolor=color.white, size=size.small)`
    );
  };

  addLevel(signal.entry_zone_low, 'entry_low', 'Giriş Alt', 'color.orange', 'hline.style_dotted');
  addLevel(signal.entry_zone_high, 'entry_high', 'Giriş Üst', 'color.orange', 'hline.style_dotted');
  addLevel(signal.stop_loss, 'sl', 'SL', 'color.red');
  addLevel(signal.tp1, 'tp1', 'TP1', 'color.green');
  addLevel(signal.tp2, 'tp2', 'TP2', 'color.green');
  addLevel(signal.tp3, 'tp3', 'TP3', 'color.green');

  return [
    '//@version=5',
    `indicator("TradeMinds AI — ${symbol} Sinyal Seviyeleri", overlay=true)`,
    '',
    ...hlines,
    '',
    ...labelDecls,
    '',
    'if barstate.islast',
    ...labelAssigns,
  ].join('\n');
}

export default function AssetDetailPage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const symbol = decodeURIComponent(String(params.symbol ?? '')).toUpperCase();
  // A symbol can have several concurrently-active signals across timeframes
  // (e.g. SANDUSDT 15m + 1h + 4h + 1d at once), each with its own entry/SL/TP.
  // Without this, the page always grabbed whichever one the API happened to
  // list first — so clicking a specific row's "Grafiği Aç" could silently
  // show a different timeframe's levels than the one the user actually opened.
  const requestedTf = searchParams.get('tf');

  const [signal, setSignal] = useState<ApiSignal | null>(null);
  const [candles, setCandles] = useState<ChartCandle[]>([]);
  const [chartMode, setChartMode] = useState<'overlay' | 'tradingview'>('overlay');
  const [loading, setLoading] = useState(true);

  // Defaults to the signal's own timeframe (matches what the tracker actually
  // evaluated TP/SL against), but the user can switch it manually to inspect
  // other granularities — the "Anlık" status badge above is computed from the
  // live price, not from the chart, so switching TF here never misrepresents
  // whether a signal is really active/closed.
  const [manualTf, setManualTf] = useState<string | null>(null);
  const [pineCopied, setPineCopied] = useState(false);

  const prices = useLivePrices(symbol ? [symbol] : []);
  const live = prices[symbol];

  const chartTimeframe = manualTf ?? signal?.timeframe ?? '1h';

  // Reset the manual override when navigating to a different symbol.
  useEffect(() => { setManualTf(null); }, [symbol]);

  const loadData = React.useCallback(async (showLoading: boolean) => {
    if (showLoading) setLoading(true);
    try {
      const [signalsRes, ohlcvRes] = await Promise.all([
        fetchActiveSignals({ page_size: 100 }),
        fetchOhlcv(symbol, chartTimeframe, 200).catch(() => ({ candles: [] as ChartCandle[] })),
      ]);
      const candidates = signalsRes.items.filter((s) => s.asset?.symbol?.toUpperCase() === symbol);
      const match = requestedTf
        ? candidates.find((s) => s.timeframe === requestedTf) ?? candidates[0]
        : candidates[0];
      setSignal(match ?? null);
      setCandles(ohlcvRes.candles ?? []);
    } finally {
      if (showLoading) setLoading(false);
    }
  }, [symbol, chartTimeframe, requestedTf]);

  useEffect(() => {
    loadData(true);
    // Refresh candles + signal status every 30s so the chart and "active"
    // badge stay live without a manual page reload.
    const id = setInterval(() => loadData(false), 30_000);
    return () => clearInterval(id);
  }, [loadData]);

  const assetType = signal?.asset?.asset_type;
  const assetName = signal?.asset?.name ?? symbol;
  const up = (live?.changePct24h ?? 0) >= 0;

  const openInTradingView = () => {
    const tvSymbol = toTradingViewSymbol(symbol, assetType);
    window.open(`https://www.tradingview.com/chart/?symbol=${encodeURIComponent(tvSymbol)}`, '_blank', 'noopener,noreferrer');
  };

  const copyPineScript = async () => {
    if (!signal) return;
    try {
      await navigator.clipboard.writeText(buildPineScript(symbol, signal));
      setPineCopied(true);
      setTimeout(() => setPineCopied(false), 2500);
    } catch {
      alert('Kopyalanamadı — tarayıcın panoya erişime izin vermiyor olabilir.');
    }
  };

  // Determine where current price sits relative to signal levels
  const priceStatus = (() => {
    if (!live || !signal) return null;
    const p = live.price;
    if (signal.stop_loss && p <= signal.stop_loss) return { label: 'Stop-Loss altında', color: 'text-bearish' };
    if (signal.tp2 && p >= signal.tp2) return { label: 'TP2 üzerinde', color: 'text-bullish' };
    if (signal.tp1 && p >= signal.tp1) return { label: 'TP1 üzerinde', color: 'text-bullish' };
    if (signal.entry_zone_low && signal.entry_zone_high && p >= signal.entry_zone_low && p <= signal.entry_zone_high)
      return { label: 'Giriş bölgesinde', color: 'text-accent-primary' };
    return { label: 'Bekliyor', color: 'text-text-muted' };
  })();

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.back()}
            className="p-2 rounded-lg bg-bg-secondary border border-border-subtle text-text-muted hover:text-text-primary transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div className="w-11 h-11 rounded-xl bg-bg-tertiary border border-border-subtle flex items-center justify-center font-bold font-mono text-base text-accent-primary">
            {symbol.slice(0, 2)}
          </div>
          <div>
            <h1 className="text-xl font-extrabold text-text-primary">{symbol}</h1>
            <p className="text-xs text-text-secondary">{assetName}</p>
          </div>
        </div>

        {/* Live price */}
        {live && (
          <div className="text-right">
            <p className="text-2xl font-bold font-mono text-text-primary">
              {live.price.toLocaleString('tr-TR', { maximumFractionDigits: 4 })}
            </p>
            <p className={cn('text-sm font-mono font-semibold flex items-center justify-end gap-1', up ? 'text-bullish' : 'text-bearish')}>
              {up ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
              {up ? '+' : ''}{live.changePct24h?.toFixed(2)}% (24s)
            </p>
          </div>
        )}
      </div>

      {/* ─── Chart: full width, premium ─── */}
      <GlassCard className="p-0 overflow-hidden">
        <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-b border-border-subtle flex-wrap">
          <div className="flex gap-1 p-0.5 bg-bg-tertiary/50 rounded-lg">
            <button
              onClick={() => setChartMode('overlay')}
              className={cn(
                'px-3 py-1 text-xs font-semibold rounded-md transition-all',
                chartMode === 'overlay'
                  ? 'bg-accent-primary text-white shadow-glow-sm'
                  : 'text-text-muted hover:text-text-primary'
              )}
            >
              Sinyal Overlay
            </button>
            <button
              onClick={() => setChartMode('tradingview')}
              className={cn(
                'px-3 py-1 text-xs font-semibold rounded-md transition-all',
                chartMode === 'tradingview'
                  ? 'bg-accent-primary text-white shadow-glow-sm'
                  : 'text-text-muted hover:text-text-primary'
              )}
            >
              TradingView
            </button>
          </div>

          {/* Timeframe selector — overlay chart only (TradingView widget has its own) */}
          {chartMode === 'overlay' && (
            <div className="flex gap-1 p-0.5 bg-bg-tertiary/50 rounded-lg">
              {(['15m', '1h', '4h', '1d'] as const).map((tf) => (
                <button
                  key={tf}
                  onClick={() => setManualTf(tf)}
                  className={cn(
                    'px-2.5 py-1 text-[11px] font-bold uppercase rounded-md transition-all',
                    chartTimeframe === tf
                      ? 'bg-accent-primary text-white shadow-glow-sm'
                      : 'text-text-muted hover:text-text-primary'
                  )}
                >
                  {tf}
                </button>
              ))}
            </div>
          )}

          {/* Price status + chart info */}
          <div className="flex items-center gap-4">
            {priceStatus && (
              <div className="flex items-center gap-2 text-xs">
                <span className="text-text-muted">Anlık:</span>
                <span className={cn('font-bold uppercase tracking-wider', priceStatus.color)}>{priceStatus.label}</span>
              </div>
            )}
            {signal && chartMode === 'overlay' && (
              <span className="text-[10px] text-text-muted hidden md:inline">
                Giriş · SL · TP seviyeleri grafikte
              </span>
            )}
            <button
              onClick={openInTradingView}
              title="Gerçek TradingView'da bu sembolü aç"
              className="flex items-center gap-1.5 text-[11px] font-semibold text-text-muted hover:text-text-primary border border-border-subtle hover:border-accent-primary/40 px-2.5 py-1.5 rounded-lg transition-all"
            >
              <ExternalLink className="w-3.5 h-3.5" /> TradingView'da Aç
            </button>
            {signal && (
              <button
                onClick={copyPineScript}
                title="Giriş/SL/TP seviyelerini TradingView'a yapıştırmak için Pine Script kopyala"
                className="flex items-center gap-1.5 text-[11px] font-semibold text-text-muted hover:text-text-primary border border-border-subtle hover:border-accent-primary/40 px-2.5 py-1.5 rounded-lg transition-all"
              >
                {pineCopied ? <Check className="w-3.5 h-3.5 text-bullish" /> : <Code2 className="w-3.5 h-3.5" />}
                {pineCopied ? 'Kopyalandı!' : 'Pine Script Kopyala'}
              </button>
            )}
          </div>
        </div>

        {chartMode === 'overlay' ? (
          candles.length > 0 ? (
            <TradingChart
              key={chartTimeframe}
              candles={candles}
              signal={signal ? {
                entryLow:  signal.entry_zone_low,
                entryHigh: signal.entry_zone_high,
                stopLoss:  signal.stop_loss,
                tp1:       signal.tp1,
                tp2:       signal.tp2,
                tp3:       signal.tp3,
                direction: signal.direction === 'bullish' ? 'long' : 'short',
              } : undefined}
              height={520}
            />
          ) : (
            <div className="flex justify-center items-center h-[520px]">
              <div className="w-7 h-7 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" />
            </div>
          )
        ) : (
          <TradingViewChart
            symbol={symbol}
            assetType={assetType}
            timeframe={signal?.timeframe}
            height={520}
          />
        )}
      </GlassCard>

      {/* ─── Signal Analytics: full width, below chart ─── */}
      {loading ? (
        <GlassCard className="flex justify-center py-16">
          <div className="w-6 h-6 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" />
        </GlassCard>
      ) : signal ? (
        <SignalDetailSection signal={signal} />
      ) : (
        <GlassCard className="text-center py-12">
          <p className="text-sm text-text-muted">Bu varlık için aktif sinyal yok.</p>
          <p className="text-xs text-text-muted mt-2">Grafik yine de canlı görüntüleniyor.</p>
        </GlassCard>
      )}
    </div>
  );
}

function LevelRow({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-text-muted">{label}</span>
      <span className={cn('text-sm font-bold font-mono', color)}>{value}</span>
    </div>
  );
}
