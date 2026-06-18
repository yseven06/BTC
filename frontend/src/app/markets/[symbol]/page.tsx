'use client';

import React, { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, TrendingUp, TrendingDown, Target, Shield, Zap } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { SignalBadge } from '@/components/ui/SignalBadge';
import { ScoreRing } from '@/components/ui/ScoreRing';
import TradingViewChart from '@/components/charts/TradingViewChart';
import { TradingChart, type ChartCandle } from '@/components/charts/TradingChart';
import { fetchActiveSignals, fetchOhlcv, type ApiSignal } from '@/lib/api';
import { useLivePrices } from '@/hooks/useLivePrices';
import { SignalType } from '@/types';
import { cn } from '@/lib/utils';

export default function AssetDetailPage() {
  const params = useParams();
  const router = useRouter();
  const symbol = decodeURIComponent(String(params.symbol ?? '')).toUpperCase();

  const [signal, setSignal] = useState<ApiSignal | null>(null);
  const [candles, setCandles] = useState<ChartCandle[]>([]);
  const [chartMode, setChartMode] = useState<'overlay' | 'tradingview'>('overlay');
  const [loading, setLoading] = useState(true);

  const prices = useLivePrices(symbol ? [symbol] : []);
  const live = prices[symbol];

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetchActiveSignals({ page_size: 100 }),
      fetchOhlcv(symbol, '1h', 200).catch(() => ({ candles: [] as ChartCandle[] })),
    ]).then(([signalsRes, ohlcvRes]) => {
      const match = signalsRes.items.find((s) => s.asset?.symbol?.toUpperCase() === symbol);
      setSignal(match ?? null);
      setCandles(ohlcvRes.candles ?? []);
    }).finally(() => setLoading(false));
  }, [symbol]);

  const assetType = signal?.asset?.asset_type;
  const assetName = signal?.asset?.name ?? symbol;
  const up = (live?.changePct24h ?? 0) >= 0;

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

      {/* Chart + Signal */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-5">
        <GlassCard className="p-0 overflow-hidden">
          {/* Chart mode tabs */}
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-border-subtle">
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
            {signal && chartMode === 'overlay' && (
              <span className="text-[10px] text-text-muted">
                Giriş, SL ve TP seviyeleri grafikte
              </span>
            )}
          </div>

          {chartMode === 'overlay' ? (
            candles.length > 0 ? (
              <TradingChart
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

        {/* Signal Panel */}
        <div className="space-y-4">
          {loading ? (
            <GlassCard className="flex justify-center py-16">
              <div className="w-6 h-6 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" />
            </GlassCard>
          ) : signal ? (
            <>
              {/* Signal header */}
              <GlassCard className="space-y-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-bold text-text-primary flex items-center gap-2">
                    <Zap className="w-4 h-4 text-accent-primary" /> AI Sinyali
                  </h2>
                  <SignalBadge type={signal.signal_type as SignalType} />
                </div>

                {priceStatus && (
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-text-muted">Anlık durum:</span>
                    <span className={cn('font-bold', priceStatus.color)}>{priceStatus.label}</span>
                  </div>
                )}

                <div className="flex justify-around pt-2">
                  <ScoreRing score={signal.confidence_score} size={64} strokeWidth={5} label="Güven" />
                  <ScoreRing score={signal.probability_score} size={64} strokeWidth={5} label="Olasılık" />
                </div>
              </GlassCard>

              {/* Levels */}
              <GlassCard className="space-y-3">
                <h3 className="text-xs font-bold text-text-muted uppercase tracking-wide flex items-center gap-1.5">
                  <Target className="w-3.5 h-3.5" /> Seviyeler
                </h3>

                <LevelRow label="Giriş Bölgesi" color="text-text-primary"
                  value={`${signal.entry_zone_low?.toLocaleString('tr-TR')} – ${signal.entry_zone_high?.toLocaleString('tr-TR')}`} />
                <LevelRow label="Zarar Durdur (SL)" color="text-bearish"
                  value={signal.stop_loss?.toLocaleString('tr-TR') ?? '—'} />
                <LevelRow label="Hedef 1 (TP1)" color="text-bullish"
                  value={signal.tp1?.toLocaleString('tr-TR') ?? '—'} />
                <LevelRow label="Hedef 2 (TP2)" color="text-bullish"
                  value={signal.tp2?.toLocaleString('tr-TR') ?? '—'} />
                {signal.tp3 != null && (
                  <LevelRow label="Hedef 3 (TP3)" color="text-bullish"
                    value={signal.tp3?.toLocaleString('tr-TR')} />
                )}

                <div className="flex items-center gap-2 pt-2 border-t border-border-subtle">
                  <Shield className="w-3.5 h-3.5 text-text-muted" />
                  <span className="text-xs text-text-muted">Risk:</span>
                  <span className="text-xs font-bold text-text-primary capitalize">{signal.risk_level}</span>
                  <span className="ml-auto text-[10px] text-text-muted">{signal.timeframe}</span>
                </div>
              </GlassCard>

              {/* Explanation */}
              {signal.explanation_tr && (
                <GlassCard>
                  <h3 className="text-xs font-bold text-text-muted uppercase tracking-wide mb-2">Neden bu sinyal?</h3>
                  <p className="text-xs text-text-secondary leading-relaxed">{signal.explanation_tr}</p>
                </GlassCard>
              )}
            </>
          ) : (
            <GlassCard className="text-center py-12">
              <p className="text-sm text-text-muted">Bu varlık için aktif sinyal yok.</p>
              <p className="text-xs text-text-muted mt-2">Grafik yine de canlı görüntüleniyor.</p>
            </GlassCard>
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
