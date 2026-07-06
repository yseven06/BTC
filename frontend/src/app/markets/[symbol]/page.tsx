'use client';

import React, { useState, useEffect } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { ArrowLeft, TrendingUp, TrendingDown, Target, Shield, Zap, ExternalLink, Code2, Check, AlertTriangle, X, Maximize2, Minimize2, HelpCircle } from 'lucide-react';
import { toTradingViewSymbol } from '@/lib/tradingview';
import { GlassCard } from '@/components/ui/GlassCard';
import { SignalBadge } from '@/components/ui/SignalBadge';
import { ScoreRing } from '@/components/ui/ScoreRing';
import TradingViewChart from '@/components/charts/TradingViewChart';
import { TradingChart, type ChartCandle } from '@/components/charts/TradingChart';
import { fetchActiveSignals, fetchOhlcv, fetchSignalHistory, type ApiSignal } from '@/lib/api';
import { useLivePrices } from '@/hooks/useLivePrices';
import { SignalType } from '@/types';
import { cn, formatRelativeTime, formatAbsoluteTimeTR, formatPrice, formatPercentage } from '@/lib/utils';
import { SignalDetailSection } from '@/components/ui/SignalDetailSection';
import { CoinIcon } from '@/components/ui/CoinIcon';

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

const RECENT_OUTCOME_LABEL: Record<string, string> = {
  win: 'TP — Kazandı', loss: 'Stop Oldu', breakeven: 'Başabaş',
  expired: 'Süresi Doldu', invalidated: 'İptal Edildi',
};
const RECENT_OUTCOME_COLOR: Record<string, string> = {
  win: 'text-bullish', loss: 'text-bearish', breakeven: 'text-amber',
  expired: 'text-text-muted', invalidated: 'text-purple-400',
};

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
  const [recentClosed, setRecentClosed] = useState<ApiSignal[]>([]);
  const [candles, setCandles] = useState<ChartCandle[]>([]);
  const [chartMode, setChartMode] = useState<'overlay' | 'tradingview'>('overlay');
  const [loading, setLoading] = useState(true);
  // CSS-only overlay rather than the native Fullscreen API — some
  // environments (corporate browser policies, embedded iframes) reject
  // requestFullscreen() outright, so a plain fixed-position overlay is the
  // version that's guaranteed to work everywhere.
  const [manualFullscreen, setManualFullscreen] = useState(false);

  const toggleFullscreen = () => setManualFullscreen((v) => !v);

  useEffect(() => {
    if (!manualFullscreen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setManualFullscreen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [manualFullscreen]);

  // Background polling refreshes the signal silently every 30s — the user
  // could otherwise watch a LONG call flip to SHORT or vanish entirely with
  // no indication anything changed. This tracks the previously-seen signal
  // so we can surface that transition explicitly instead of just swapping
  // the numbers underneath them.
  const prevSignalRef = React.useRef<ApiSignal | null>(null);
  const [changeNotice, setChangeNotice] = useState<string | null>(null);
  // When the user picks a timeframe tab that has no actionable signal right
  // now, loadData silently falls back to whichever timeframe *does* — the
  // only trace of that swap was a tiny "[4H]" badge buried in the engine
  // card, easy to miss. A user comparing two screenshots taken on different
  // tabs (thinking they were the same timeframe) saw entry/SL/TP "change"
  // when really they were looking at two different signals all along.
  const [tfFallbackNotice, setTfFallbackNotice] = useState<string | null>(null);

  // Fit the chart + sidebar row to whatever vertical space is actually left
  // in the viewport below this row, instead of giving the chart a fixed
  // height and letting the rest of the screen sit empty. The row's own top
  // offset is read from the DOM (not assumed) so it stays correct whether
  // or not the "sinyal değişti" banner above it is showing.
  const rowRef = React.useRef<HTMLDivElement>(null);
  const [rowHeight, setRowHeight] = useState<number | null>(null);
  useEffect(() => {
    if (manualFullscreen) return;
    const update = () => {
      if (!rowRef.current) return;
      const top = rowRef.current.getBoundingClientRect().top;
      setRowHeight(Math.max(480, window.innerHeight - top - 24));
    };
    update();
    window.addEventListener('resize', update);
    // Re-measure shortly after mount too — the "sinyal değişti" banner
    // (and the initial loading→loaded swap) can shift this row's top
    // offset after the first paint.
    const t = setTimeout(update, 200);
    return () => { window.removeEventListener('resize', update); clearTimeout(t); };
  }, [manualFullscreen, changeNotice ? changeNotice : null, tfFallbackNotice ? tfFallbackNotice : null, loading]);

  // lightweight-charts needs an explicit pixel height — it won't just fill
  // a flex/grid parent — so the chart's own render area is measured and fed
  // back in as `chartHeight`, after subtracting the control bar above it.
  const chartAreaRef = React.useRef<HTMLDivElement>(null);
  const [chartHeight, setChartHeight] = useState(520);
  useEffect(() => {
    if (!chartAreaRef.current) return;
    const el = chartAreaRef.current;
    const observer = new ResizeObserver(() => setChartHeight(el.offsetHeight));
    observer.observe(el);
    return () => observer.disconnect();
  }, [manualFullscreen]);

  // Defaults to the signal's own timeframe (matches what the tracker actually
  // evaluated TP/SL against), but the user can switch it manually to inspect
  // other granularities — the "Anlık" status badge above is computed from the
  // live price, not from the chart, so switching TF here never misrepresents
  // whether a signal is really active/closed.
  const [manualTf, setManualTf] = useState<string | null>(null);
  const [pineCopied, setPineCopied] = useState(false);
  const [showPineHint, setShowPineHint] = useState(false);

  const prices = useLivePrices(symbol ? [symbol] : []);
  const live = prices[symbol];

  const chartTimeframe = manualTf ?? signal?.timeframe ?? '1h';

  // Reset the manual override when navigating to a different symbol.
  useEffect(() => { setManualTf(null); prevSignalRef.current = null; setChangeNotice(null); }, [symbol]);

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

      setTfFallbackNotice(
        requestedTf && match && match.timeframe !== requestedTf
          ? `${requestedTf.toUpperCase()} için şu an aktif bir sinyal yok — gösterilen, ${match.timeframe.toUpperCase()} zaman diliminin sinyali.`
          : null
      );

      // Persisted across page reloads (sessionStorage), not just in-memory —
      // a full F5 re-mounts this component and wipes prevSignalRef, so a
      // signal that closed-then-got-replaced moments before the reload
      // silently looked "back" with no explanation. The notice key is tied
      // to the symbol so it survives the reload but still expires quickly
      // (closures older than a few minutes aren't worth re-surfacing).
      const noticeKey = `signal_notice_${symbol}`;
      const prev = prevSignalRef.current ?? (() => {
        try {
          const raw = sessionStorage.getItem(noticeKey);
          if (!raw) return null;
          const { signal: storedSig, savedAt } = JSON.parse(raw);
          if (Date.now() - savedAt > 10 * 60_000) return null; // stale, ignore
          return storedSig as ApiSignal;
        } catch {
          return null;
        }
      })();

      // `match` being truthy means a signal is genuinely active right now —
      // a "this signal closed" notice is a contradiction in that case (it
      // previously stayed on screen indefinitely once set, because this
      // block only ever set the notice, never cleared it once a fresh
      // active signal came back). Clear it explicitly in every branch that
      // doesn't earn a notice of its own.
      if (match) {
        if (prev && match.id !== prev.id && match.direction !== prev.direction) {
          const fromLabel = prev.direction === 'bullish' ? 'LONG' : prev.direction === 'bearish' ? 'SHORT' : 'BEKLE';
          const toLabel = match.direction === 'bullish' ? 'LONG' : match.direction === 'bearish' ? 'SHORT' : 'BEKLE';
          setChangeNotice(`Önceki sinyal (${fromLabel}) kapandı, bu YENİ bir sinyal: ${toLabel} (${formatRelativeTime(match.generated_at)})`);
        } else {
          setChangeNotice(null);
        }
      } else if (prev) {
        const prevDirLabel = prev.direction === 'bullish' ? 'LONG' : prev.direction === 'bearish' ? 'SHORT' : 'BEKLE';
        setChangeNotice(`Bu sinyal kapandı (son yön: ${prevDirLabel}). Aşağıdaki bilgiler artık güncel değil — Sinyal Geçmişi'nde sonucu görebilirsin.`);
      } else {
        setChangeNotice(null);
      }
      prevSignalRef.current = match ?? null;

      try {
        if (match) {
          sessionStorage.setItem(noticeKey, JSON.stringify({ signal: match, savedAt: Date.now() }));
        } else {
          sessionStorage.removeItem(noticeKey);
        }
      } catch {
        // sessionStorage unavailable (private mode etc.) — notice just won't survive a reload
      }

      setSignal(match ?? null);
      setCandles(ohlcvRes.candles ?? []);

      // No active signal for this symbol — surface its recent closed ones so
      // "aktif sinyal yok" doesn't read as "no signal ever existed". Users
      // tracking a symbol that just resolved need to find the outcome
      // without manually paging through Sinyal Geçmişi's full list.
      if (!match) {
        try {
          const histRes = await fetchSignalHistory({ symbol, only_resolved: true, page_size: 5 });
          setRecentClosed(histRes.items);
        } catch {
          setRecentClosed([]);
        }
      } else {
        setRecentClosed([]);
      }
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
    // SHORT sinyalinde SL girişin ÜSTÜNDE, TP'ler girişin ALTINDA olur —
    // LONG'daki "p <= SL" / "p >= TP" karşılaştırmaları SHORT'ta ters
    // sonuç verir, bu yüzden yön burada ayrıca kontrol edilmeli.
    const isShort = signal.direction === 'bearish';
    const sl = signal.stop_loss, tp1 = signal.tp1, tp2 = signal.tp2;
    const lo = signal.entry_zone_low, hi = signal.entry_zone_high;

    if (sl != null && (isShort ? p >= sl : p <= sl))
      return { label: isShort ? 'Stop-Loss üzerinde' : 'Stop-Loss altında', color: 'text-bearish' };
    if (tp2 != null && (isShort ? p <= tp2 : p >= tp2))
      return { label: isShort ? 'TP2 altında' : 'TP2 üzerinde', color: 'text-bullish' };
    if (tp1 != null && (isShort ? p <= tp1 : p >= tp1))
      return { label: isShort ? 'TP1 altında' : 'TP1 üzerinde', color: 'text-bullish' };
    if (lo != null && hi != null && p >= lo && p <= hi)
      return { label: 'Giriş bölgesinde', color: 'text-accent-primary' };

    // Fiyat giriş bandının dışında ama henüz TP/SL'e ulaşmadı: hangi
    // tarafta olduğunu belirt — "Bekliyor" tek başına neyin beklendiğini
    // söylemiyordu.
    if (lo != null && hi != null) {
      const beyondEntry = isShort ? p < lo : p > hi;
      return beyondEntry
        ? { label: 'Girişten ileride, TP yolda', color: 'text-bullish' }
        : { label: 'Giriş seviyesi bekleniyor', color: 'text-text-muted' };
    }
    return { label: 'Bekliyor', color: 'text-text-muted' };
  })();

  return (
    <div className="space-y-5">
      {/* Header — price sits right next to the symbol instead of being
          flung to the far edge; on the wide (fullWidth) layout that gap
          read as two disconnected pieces rather than one header. */}
      <div className="flex items-center gap-4">
        <button
          onClick={() => router.back()}
          className="p-2 rounded-lg bg-bg-secondary border border-border-subtle text-text-muted hover:text-text-primary transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
        </button>
        <div className="w-11 h-11 rounded-xl bg-bg-tertiary border border-border-subtle flex items-center justify-center font-bold font-mono text-base text-accent-primary overflow-hidden">
          <CoinIcon symbol={symbol} assetType={assetType} />
        </div>
        <div>
          <h1 className="text-xl font-extrabold text-text-primary">{symbol}</h1>
          <p className="text-xs text-text-secondary">{assetName}</p>
        </div>

        {/* Live price */}
        {live && (
          <div className="flex items-baseline gap-2.5 ml-1 pl-4 border-l border-border-subtle">
            <p className="text-2xl font-bold font-mono text-text-primary">
              {formatPrice(live.price)}
            </p>
            <p className={cn('text-sm font-mono font-semibold flex items-center gap-1', up ? 'text-bullish' : 'text-bearish')}>
              {up ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
              {formatPercentage(live.changePct24h ?? 0)} (24s)
            </p>
          </div>
        )}
      </div>

      {changeNotice && (
        <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-amber-500/10 border border-amber-500/30">
          <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
          <p className="text-xs text-amber-300 flex-1">{changeNotice}</p>
          <button onClick={() => setChangeNotice(null)} className="text-amber-400/70 hover:text-amber-300 flex-shrink-0">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {tfFallbackNotice && (
        <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-accent-primary/10 border border-accent-primary/30">
          <AlertTriangle className="w-4 h-4 text-accent-primary flex-shrink-0" />
          <p className="text-xs text-accent-primary flex-1">{tfFallbackNotice}</p>
          <button onClick={() => setTfFallbackNotice(null)} className="text-accent-primary/70 hover:text-accent-primary flex-shrink-0">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* ─── Chart (left) + Signal sidebar (right) — both stretched to fill
           whatever vertical space is left in the viewport, so nothing sits
           empty below the fold and nothing forces the page to scroll ─── */}
      <div
        ref={rowRef}
        className="flex flex-col lg:flex-row gap-5 items-stretch"
        style={!manualFullscreen && rowHeight ? { height: rowHeight } : undefined}
      >
      <div
        className={cn(
          'w-full lg:flex-1 lg:min-w-0 lg:h-full',
          manualFullscreen && 'fixed inset-0 z-50 bg-bg-primary p-4 overflow-y-auto'
        )}
      >
      <GlassCard className="p-0 overflow-hidden lg:h-full flex flex-col">
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
              <span className="text-[10px] text-text-muted hidden lg:inline">
                Giriş · SL · TP seviyeleri grafikte
              </span>
            )}
            <button
              onClick={toggleFullscreen}
              title={manualFullscreen ? 'Tam ekrandan çık (Esc)' : 'Grafiği tam ekran göster'}
              className="flex items-center gap-1.5 text-[11px] font-semibold text-text-muted hover:text-text-primary border border-border-subtle hover:border-accent-primary/40 px-2.5 py-1.5 rounded-lg transition-all"
            >
              {manualFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
            </button>
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
            {signal && (
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setShowPineHint((v) => !v)}
                  onBlur={() => setTimeout(() => setShowPineHint(false), 150)}
                  className="flex items-center justify-center w-6 h-6 rounded-full text-text-muted hover:text-text-primary border border-border-subtle hover:border-accent-primary/40 transition-all"
                >
                  <HelpCircle className="w-3.5 h-3.5" />
                </button>
                {showPineHint && (
                  <div className="absolute right-0 top-full mt-2 w-64 glass-card-static rounded-xl border border-border-subtle shadow-2xl p-3 text-[11px] leading-relaxed text-text-secondary z-50">
                    <p className="font-semibold text-text-primary mb-1.5">Nasıl kullanılır?</p>
                    <ol className="list-decimal list-inside space-y-1">
                      <li>Pine Script Kopyala'ya bas</li>
                      <li>TradingView'da Aç ile gerçek TradingView'ı aç</li>
                      <li>Pine Editor'e yapıştır ve indikatör olarak ekle</li>
                    </ol>
                    <p className="mt-1.5 text-text-muted">Giriş/SL/TP seviyeleri orada da görünür.</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        <div ref={chartAreaRef} className="lg:flex-1 lg:min-h-0">
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
                  generatedAt: Math.floor(new Date(signal.generated_at).getTime() / 1000),
                } : undefined}
                height={chartHeight}
              />
            ) : (
              <div className="flex justify-center items-center" style={{ height: chartHeight }}>
                <div className="w-7 h-7 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" />
              </div>
            )
          ) : (
            <TradingViewChart
              symbol={symbol}
              assetType={assetType}
              timeframe={signal?.timeframe}
              height={chartHeight}
            />
          )}
        </div>
      </GlassCard>
      </div>

      {/* ─── Signal sidebar: stretches to the same height as the chart
           column (flex items-stretch on the row above) and scrolls
           internally if its own content (mostly engine scores + AI
           explanation) runs longer than that — the page itself never has
           to scroll to see everything. ─── */}
      <div className="w-full lg:w-[540px] lg:flex-shrink-0 lg:h-full lg:min-h-0 lg:overflow-y-auto lg:pr-1">
        {loading ? (
          <GlassCard className="flex justify-center py-16">
            <div className="w-6 h-6 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" />
          </GlassCard>
        ) : signal ? (
          <SignalDetailSection signal={signal} compact />
        ) : (
          <div className="space-y-4">
            <GlassCard className="text-center py-12">
              <p className="text-sm text-text-muted">Bu varlık için aktif sinyal yok.</p>
              <p className="text-xs text-text-muted mt-2">Grafik yine de canlı görüntüleniyor.</p>
            </GlassCard>
            {recentClosed.length > 0 && (
              <GlassCard className="p-4">
                <p className="text-xs font-bold text-text-muted uppercase tracking-wider mb-3">
                  Son Kapanan Sinyaller
                </p>
                <div className="space-y-2">
                  {recentClosed.map((s) => (
                    <div key={s.id} className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg bg-bg-secondary/50 border border-border-subtle text-xs">
                      <div className="min-w-0">
                        <span className={cn('font-semibold', RECENT_OUTCOME_COLOR[s.outcome ?? ''] ?? 'text-text-muted')}>
                          {RECENT_OUTCOME_LABEL[s.outcome ?? ''] ?? s.outcome}
                        </span>
                        <span className="text-text-muted ml-2">{s.timeframe.toUpperCase()}</span>
                      </div>
                      <div className="text-right flex-shrink-0">
                        {s.actual_return != null && (
                          <span className={cn('font-mono font-bold mr-2', s.actual_return > 0 ? 'text-bullish' : s.actual_return < 0 ? 'text-bearish' : 'text-text-muted')}>
                            {formatPercentage(s.actual_return)}
                          </span>
                        )}
                        <span className="text-text-muted">{s.closed_at ? formatAbsoluteTimeTR(s.closed_at) : ''}</span>
                      </div>
                    </div>
                  ))}
                </div>
                <button
                  onClick={() => router.push('/signal-history')}
                  className="w-full mt-3 text-[11px] text-accent-primary hover:text-accent-ui text-center"
                >
                  Sinyal Geçmişi'nde tümünü gör →
                </button>
              </GlassCard>
            )}
          </div>
        )}
      </div>
      </div>
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
