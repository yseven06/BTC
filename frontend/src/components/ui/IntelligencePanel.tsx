'use client';

import React, { useEffect, useState } from 'react';
import { GlassCard } from './GlassCard';
import { cn, formatRelativeTime, formatPercentage, formatNumber } from '@/lib/utils';
import { fetchSignalIntelligence, type SignalIntelligence } from '@/lib/api';
import { Brain, History, Gauge } from 'lucide-react';
import { LIVE_STATUS_META } from './LiveStatusBadge';
import { LifecycleJourney } from './LifecycleJourney';

const REGIME_TR: Record<string, string> = {
  trending_bull: 'Yükseliş Trendi',
  trending_bear: 'Düşüş Trendi',
  ranging: 'Yatay / Range',
  volatile_high: 'Yüksek Volatilite',
  low_volume: 'Düşük Hacim',
  breakout: 'Kırılma (Breakout)',
  unknown: 'Belirsiz',
};

function humanizeDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m} dk`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} sa`;
  return `${Math.floor(h / 24)} gün`;
}

function Stat({ label, value, sub, valueCls }: { label: string; value: React.ReactNode; sub?: string; valueCls?: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-micro text-text-muted font-medium uppercase">{label}</span>
      <span className={cn('font-display text-sm', valueCls ?? 'text-text-primary')}>{value}</span>
      {sub && <span className="text-micro text-text-muted">{sub}</span>}
    </div>
  );
}

interface Props {
  signalId: string;
  compact?: boolean;
}

/**
 * "Bu sinyal şu an hâlâ geçerli mi?" — Adaptive Signal Intelligence panel.
 * Self-fetches so it can drop into any signal view without prop plumbing.
 */
export function IntelligencePanel({ signalId, compact }: Props) {
  const [data, setData] = useState<SignalIntelligence | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setFailed(false);
    fetchSignalIntelligence(signalId)
      .then((d) => { if (!cancelled) setData(d); })
      .catch(() => { if (!cancelled) setFailed(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [signalId, reloadKey]);

  if (loading) {
    return (
      <GlassCard dense={compact}>
        <div className="flex items-center gap-2 text-text-muted text-xs">
          <div className="w-4 h-4 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" />
          Akıllı durum yükleniyor…
        </div>
      </GlassCard>
    );
  }
  // Never vanish silently: a fetch failure (timeout, backend restart, etc.)
  // used to render nothing, so the whole "Akıllı Durum" panel disappeared and
  // the screen looked inconsistent. Show a small placeholder with a retry
  // instead, so the panel is always present.
  if (failed || !data) {
    return (
      <GlassCard dense={compact}>
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-text-muted text-xs">
            <Brain className="w-3.5 h-3.5 text-accent-primary" />
            Akıllı Durum yüklenemedi
          </div>
          <button
            onClick={() => setReloadKey((k) => k + 1)}
            className="text-micro font-medium text-accent-primary hover:underline"
          >
            Tekrar dene
          </button>
        </div>
      </GlassCard>
    );
  }

  const status = data.live_status && LIVE_STATUS_META[data.live_status] ? LIVE_STATUS_META[data.live_status] : LIVE_STATUS_META.active;
  const StatusIcon = status.Icon;
  const coin = data.coin_memory;

  return (
    <GlassCard dense={compact}>
      <h3 className="text-xs font-display text-text-muted uppercase tracking-wider flex items-center gap-1.5 mb-3">
        <Brain className="w-3.5 h-3.5 text-accent-primary" /> Akıllı Durum
        <span className="ml-auto normal-case font-normal text-micro text-text-muted">
          {data.status_updated_at ? `Güncellendi ${formatRelativeTime(data.status_updated_at)}` : ''}
        </span>
      </h3>

      {/* Live status banner (only meaningful while the signal is active) */}
      {data.is_active && (
        <div className={cn('flex items-start gap-2.5 rounded-xl border px-3 py-2.5 mb-4', status.bg)}>
          <StatusIcon className={cn('w-5 h-5 flex-shrink-0 mt-0.5', status.cls)} />
          <div>
            <div className={cn('font-display text-sm flex items-center gap-2', status.cls)}>
              {status.label}
              {data.seconds_in_state != null && data.seconds_in_state >= 60 && (
                <span className="text-micro font-normal text-text-muted">
                  · {humanizeDuration(data.seconds_in_state)} süredir
                </span>
              )}
            </div>
            {data.status_reason && <p className="text-micro text-text-secondary mt-0.5">{data.status_reason}</p>}
          </div>
        </div>
      )}

      {/* Resolved-signal label (when closed) */}
      {!data.is_active && data.detail_label_tr && (
        <div className="flex items-center gap-2 rounded-xl border border-border-subtle bg-bg-tertiary/40 px-3 py-2.5 mb-4">
          <History className="w-4 h-4 text-text-muted flex-shrink-0" />
          <span className="text-sm font-display text-text-primary">{data.detail_label_tr}</span>
        </div>
      )}

      {/* Lifecycle journey — how this signal travelled here (SL-b, static) */}
      <LifecycleJourney signalId={signalId} />

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-3">
        {/* Market regime at signal time */}
        <Stat
          label="Piyasa Rejimi"
          value={data.regime ? (REGIME_TR[data.regime] ?? data.regime) : '—'}
          sub={data.regime_win_rate != null ? `Bu rejimde %${data.regime_win_rate} başarı` : undefined}
        />

        {/* Coin-specific learned track record */}
        <Stat
          label="Coin Özel Başarı"
          value={
            coin.has_memory && coin.win_rate != null
              ? <span className={coin.win_rate >= 55 ? 'text-bullish' : coin.win_rate <= 45 ? 'text-bearish' : 'text-text-primary'}>{formatPercentage(coin.win_rate, 0, false)}</span>
              : <span className="text-text-muted">Henüz veri yok</span>
          }
          sub={coin.has_memory ? `${coin.total_signals} sinyal · ${coin.wins ?? 0}G/${coin.losses ?? 0}K` : 'Öğreniyor'}
        />

        {/* Birth confidence */}
        <Stat
          label="Doğuş Güveni"
          value={data.birth_confidence != null ? `${Math.round(data.birth_confidence)}` : '—'}
          sub="Motor uyumu (0-100)"
        />

        {/* Volatility */}
        {data.atr_pct != null && (
          <Stat
            label="Volatilite (ATR)"
            value={formatPercentage(data.atr_pct, 2, false)}
            sub={data.volatility_ratio != null ? `Tabanın ${formatNumber(data.volatility_ratio)}×'i` : undefined}
          />
        )}

        {/* Live MFE / drawdown for active, final for closed */}
        {data.mfe_pct != null && (
          <Stat
            label="Lehte Hareket"
            value={<span className="text-bullish">{formatPercentage(data.mfe_pct)}</span>}
            sub={data.max_drawdown != null ? `Aleyhte: -${formatPercentage(data.max_drawdown, 2, false)}` : undefined}
          />
        )}

        {/* Fear & Greed at signal time */}
        {data.fear_greed != null && (
          <Stat
            label="Korku/Açgözlülük"
            value={`${data.fear_greed}`}
            sub={data.fear_greed <= 25 ? 'Aşırı Korku' : data.fear_greed >= 75 ? 'Aşırı Açgözlülük' : 'Nötr'}
          />
        )}
      </div>

      {/* Historical similarity — "bu setup'a benzeyen geçmiş işlemler" */}
      {data.similar_setups?.has_data && data.similar_setups.win_rate != null && (
        <div className="mt-4 pt-3 border-t border-border-subtle">
          <div className="flex items-center gap-2">
            <History className="w-4 h-4 text-accent-primary flex-shrink-0" />
            <span className="text-micro text-text-secondary">
              Benzer <b className="text-text-primary">{data.similar_setups.match_count}</b> geçmiş setup'ta
              {' '}
              <b className={data.similar_setups.win_rate >= 55 ? 'text-bullish' : data.similar_setups.win_rate <= 45 ? 'text-bearish' : 'text-text-primary'}>
                {formatPercentage(data.similar_setups.win_rate, 0, false)}
              </b>{' '}başarı
              {data.similar_setups.wins != null && (
                <span className="text-text-muted"> ({data.similar_setups.wins}G/{data.similar_setups.losses}K)</span>
              )}
            </span>
          </div>
        </div>
      )}

      {/* Adaptive-weights learning indicator */}
      {coin.has_memory && (
        <div className="mt-4 pt-3 border-t border-border-subtle flex items-center gap-2 text-micro text-text-muted">
          <Gauge className="w-3 h-3" />
          {coin.adaptive_active
            ? `Bu coin/zaman dilimi için adaptif ağırlıklar aktif (${coin.total_signals} sinyalden öğrenildi).`
            : `Adaptif ağırlıklar için yeterli veri birikiyor (${coin.total_signals} sinyal; eşik 20).`}
        </div>
      )}
    </GlassCard>
  );
}
