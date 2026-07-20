'use client';

import React, { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { Modal } from '@/components/ui/Modal';
import { Skeleton } from '@/components/ui/Skeleton';
import { TradingChart, type ChartCandle } from '@/components/charts/TradingChart';
import { fetchOhlcv, type ApiSignal } from '@/lib/api';
import { formatAbsoluteTimeTR, cn, formatPercentage } from '@/lib/utils';
import { CoinIcon } from './CoinIcon';

const TF_SECONDS: Record<string, number> = { '15m': 900, '1h': 3600, '4h': 14400, '1d': 86400 };

const OUTCOME_LABEL: Record<string, string> = {
  win: 'TP — Kazandı',
  loss: 'Stop Oldu',
  breakeven: 'Başabaş',
  expired: 'Süresi Doldu',
  invalidated: 'İptal Edildi (Tersine Sinyal)',
};
const OUTCOME_COLOR: Record<string, string> = {
  win: 'text-bullish',
  loss: 'text-bearish',
  breakeven: 'text-amber',
  expired: 'text-text-muted',
  invalidated: 'text-accent-ui',
};

interface Props {
  signal: ApiSignal;
  onClose: () => void;
}

/**
 * Replays a closed signal's chart as it looked at resolution time — the
 * Sinyal Geçmişi table only shows outcome/return as numbers, with no way
 * to see *how* a trade actually played out (did it run straight to TP3, or
 * scrape TP1 and reverse?). Reuses the same OHLCV endpoint as the live
 * chart, just anchored to closed_at instead of "now".
 */
export function ClosedSignalChartModal({ signal, onClose }: Props) {
  const [candles, setCandles] = useState<ChartCandle[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const symbol = signal.asset?.symbol ?? '';
    const tfSec = TF_SECONDS[signal.timeframe] ?? 3600;
    const anchorIso = signal.closed_at ?? signal.generated_at;
    const anchorSec = Math.floor(new Date(anchorIso).getTime() / 1000);
    // A little breathing room past the close so the chart doesn't end
    // exactly on the resolving candle — shows what happened right after too.
    const endTime = anchorSec + tfSec * 15;

    fetchOhlcv(symbol, signal.timeframe, 150, endTime)
      .then((r) => { if (!cancelled) setCandles(r.candles); })
      .catch(() => { if (!cancelled) setError(true); });

    return () => { cancelled = true; };
  }, [signal]);

  const generatedAtSec = Math.floor(new Date(signal.generated_at).getTime() / 1000);

  return (
    // S1c2 — ad-hoc kabuk (fixed inset-0 + ham z-50 + elle scrim + onClick/
    // stopPropagation backdrop + glass-panel kutu) kanonik <Modal>'a devredildi:
    // portal, role=dialog + aria-modal + ariaLabel, panel-kapsamlı focus-trap ve
    // odak-iadesi, ESC, gövde scroll-kilidi, E3 materyal (S1a) ve z-modal artık
    // tek-kaynaktan gelir. KRİTİK KAZANIM: kanonik backdrop DRAG-SAFE (mousedown
    // izlemeli) — grafik üzerinde sürükleyip imleci backdrop'ta bırakınca modal
    // ARTIK KAPANMIYOR (eski kabuğun gerçek bug'ıydı).
    // padded={false}: zengin iki-satırlı başlık (ikon + sembol·TF + outcome) ve
    // mevcut ✕ AYNEN korunur. Bu modda Modal kendi başlık şeridini/✕'ini hiç
    // render etmez → çift ✕ oluşmaz (showClose'a gerek yok).
    // Not (CP-MODAL-PRESENCE): çağrı yeri koşullu mount ettiği için çıkış
    // animasyonu oynamaz — bilinen ortak borç; bu CP'de çözülmez.
    <Modal open onClose={onClose} ariaLabel="Kapanmış sinyal grafiği" size="max-w-4xl" padded={false}>
      {/* Başlık şeridi — shrink-0: gövde kayarken kimlik/outcome sabit kalır */}
      <div className="flex items-center justify-between px-5 pt-5 pb-4 shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-bg-tertiary border border-border-subtle flex items-center justify-center overflow-hidden flex-shrink-0">
            <CoinIcon symbol={signal.asset?.symbol ?? ''} assetType={signal.asset?.asset_type} />
          </div>
          <div>
            <p className="text-sm font-display text-text-primary">
              {signal.asset?.symbol} · {signal.timeframe.toUpperCase()}
            </p>
            <p className={cn('text-xs font-display', OUTCOME_COLOR[signal.outcome ?? ''] ?? 'text-text-muted')}>
              {OUTCOME_LABEL[signal.outcome ?? ''] ?? signal.outcome}
              {signal.actual_return != null && ` · ${formatPercentage(signal.actual_return)}`}
              {signal.closed_at && ` · ${formatAbsoluteTimeTR(signal.closed_at)}`}
            </p>
          </div>
        </div>
        <button onClick={onClose} aria-label="Kapat" className="text-text-muted hover:text-text-primary flex-shrink-0">
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Gövde — kısa viewport'ta iç scroll (min-h-0: flex-col içinde küçülebilsin) */}
      <div className="grow min-h-0 overflow-y-auto px-5 pb-5 space-y-4">
        {error && (
          <p className="text-sm text-text-muted text-center py-12">Grafik yüklenemedi.</p>
        )}
        {!error && !candles && (
          <div role="status" aria-busy="true">
            <span className="sr-only">Yükleniyor</span>
            <Skeleton className="w-full h-[420px]" />
          </div>
        )}
        {!error && candles && candles.length > 0 && (
          <TradingChart
            candles={candles}
            height={420}
            signal={{
              entryLow: signal.entry_zone_low,
              entryHigh: signal.entry_zone_high,
              stopLoss: signal.stop_loss,
              tp1: signal.tp1,
              tp2: signal.tp2,
              tp3: signal.tp3,
              direction: signal.direction === 'bearish' ? 'short' : 'long',
              generatedAt: generatedAtSec,
            }}
          />
        )}
        {!error && candles && candles.length === 0 && (
          <p className="text-sm text-text-muted text-center py-12">Bu tarih aralığı için veri bulunamadı.</p>
        )}
      </div>
    </Modal>
  );
}
