'use client';

import React, { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import {
  Zap, CheckCircle, AlertTriangle,
  LineChart as ChartIcon, ArrowRight, RefreshCw, Activity, X,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { SignalTable, DensityToggle, type Density } from '@/components/signals/SignalTable';
import { SignalDetailSection } from '@/components/ui/SignalDetailSection';
import {
  fetchActiveSignals, fetchPerformanceSummary, fetchSignalHistoryStats,
  fetchGlobalMarket, fetchFearGreed,
  type ApiSignal, type PerformanceSummary, type SignalHistoryStats,
  type GlobalMarketData, type FearGreedData,
} from '@/lib/api';
import { ACTIVE_SIGNAL_PARAMS } from '@/lib/active-signal';
import { formatLargeNumber, formatPercentage, cn } from '@/lib/utils';
import { PAYMENTS_ENABLED } from '@/lib/config';
import { InvestmentDisclaimer } from '@/components/legal/InvestmentDisclaimer';
import { useLivePrices } from '@/hooks/useLivePrices';
import { useExitPresence } from '@/hooks/useExitPresence';
import { useTierLimits } from '@/hooks/useTierLimits';
import { useAuth } from '@/lib/auth-context';
import { EmptyState } from '@/components/ui/EmptyState';
import OnboardingChecklist from '@/components/dashboard/OnboardingChecklist';
import CoachmarkTour from '@/components/dashboard/CoachmarkTour';
import { DurumBandi } from '@/components/dashboard/DurumBandi';
import { LifecycleHealth } from '@/components/dashboard/LifecycleHealth';
import { AIGorusu } from '@/components/dashboard/AIGorusu';
import { Sicil } from '@/components/dashboard/Sicil';
import { Crown, Lock } from 'lucide-react';
import { chartColor } from '@/lib/chartColors';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fngLabel(v: number): string {
  if (v >= 75) return 'AŞIRI AÇGÖZLÜLÜK';
  if (v >= 55) return 'AÇGÖZLÜLÜK (GREED)';
  if (v >= 45) return 'NÖTR';
  if (v >= 25) return 'KORKU (FEAR)';
  return 'AŞIRI KORKU';
}

// Owned semantik (P9.7): greed=bull · nötr/korku=amber · aşırı-korku=bear;
// extreme/greed ayrımı label'da (tek owned-hex; #34D399/#F59E0B/#EF4444 emekli).
function fngColor(v: number): string {
  if (v >= 75) return chartColor('bull');
  if (v >= 55) return chartColor('bull');
  if (v >= 45) return chartColor('amber');
  if (v >= 25) return chartColor('amber');
  return chartColor('bear');
}

function LiveClock() {
  const [time, setTime] = useState('');
  useEffect(() => {
    const update = () => {
      const now = new Date();
      setTime(now.toLocaleString('tr-TR', {
        timeZone: 'Europe/Istanbul',
        day: '2-digit', month: 'long', year: 'numeric',
        hour: '2-digit', minute: '2-digit', second: '2-digit',
      }));
    };
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, []);
  return <span className="text-sm text-text-muted font-mono">{time}</span>;
}

// ---------------------------------------------------------------------------
// Neden? — inline detay paneli (PI-2c disclosure settle)
// Kullanıcı-tetikli açılış/kapanış: scaleIn (giriş) + ters scaleIn (çıkış), PI-1a
// deterministik-timer mekanizması (useExitPresence). transform/opacity-only → CLS=0,
// MO-01 layout-anim yok. Dış shell animasyonlanır; SignalDetailSection'a dokunulmaz.
// ---------------------------------------------------------------------------
function ReasonPanel({ signal, onClose }: { signal: ApiSignal | null; onClose: () => void }) {
  const { rendered, closing, value, ref } = useExitPresence<ApiSignal>(signal);
  if (!rendered || !value) return null;
  return (
    <div
      ref={ref}
      className={cn(
        'glass-panel border border-border-subtle rounded-2xl overflow-hidden',
        closing
          ? '[animation:scaleIn_var(--dur-state)_ease-out_reverse_forwards]'
          : 'animate-scale-in'
      )}
    >
      <div className="flex items-center justify-between px-5 py-3 border-b border-border-subtle bg-bg-secondary/30">
        <h3 className="text-sm font-display text-text-primary flex items-center gap-2">
          <Activity className="w-4 h-4 text-accent-primary" />
          {value.asset?.symbol} · Neden?
        </h3>
        <button
          onClick={onClose}
          className="text-text-muted hover:text-text-primary p-1 rounded-lg hover:bg-bg-secondary transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
      <div className="p-5">
        <SignalDetailSection signal={value} compact />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Dashboard
// ---------------------------------------------------------------------------

export default function DashboardPage() {
  const [timeRange, setTimeRange] = useState<'24s' | '7g' | '30g'>('24s');
  const [density, setDensity] = useState<Density>('compact');
  const [selectedSignal, setSelectedSignal] = useState<ApiSignal | null>(null);

  const [signals, setSignals] = useState<ApiSignal[]>([]);
  const [perf, setPerf] = useState<PerformanceSummary | null>(null);
  const [global, setGlobal] = useState<GlobalMarketData | null>(null);
  const [fng, setFng] = useState<FearGreedData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  // CoinGecko's free API rate-limits (503) under repeated calls — when that
  // happens we keep showing the last successfully fetched values (if any)
  // instead of wiping them, and surface a clear message instead of leaving
  // the cards stuck on "—" / "Yükleniyor..." forever with no explanation.
  const [globalError, setGlobalError] = useState(false);
  // Core platform data (signals + performance) unreachable — surface an honest
  // error + retry instead of rendering misleading zeros as if they were real.
  const [dataError, setDataError] = useState(false);
  // CP-7 tek sayı sözlüğü (lib/active-signal.ts): sayaç, tablo, lifecycle-census
  // ve AI-Görüşü/Risk agregaları AYNI actionable fetch'inden beslenir —
  // kart-tablo-sayaç aynı sayıyı söyler; Sinyal Merkezi default'uyla birebir
  // (süperset kuralı). perf.active_count HOLD içerir → kullanıcı-yüzeyinde yok.
  const [actionableActiveCount, setActionableActiveCount] = useState(0);
  // Closed trades within the selected 24s/7g/30g window — replaces the old
  // "Toplam Sinyal" (all-time, ignored the period selector entirely).
  const [periodStats, setPeriodStats] = useState<SignalHistoryStats | null>(null);

  const signalSymbols = [...new Set(signals.map((s) => s.asset?.symbol ?? '').filter(Boolean))];
  const livePrices = useLivePrices(signalSymbols);
  const limits = useTierLimits();
  const isFreeTier = !limits.loading && limits.tier === 'free';
  const { user } = useAuth();
  const firstName = user?.full_name?.trim().split(/\s+/)[0] ?? '';

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);

    const periodHours = timeRange === '24s' ? 24 : timeRange === '7g' ? 24 * 7 : 24 * 30;
    const dateFrom = new Date(Date.now() - periodHours * 3600_000).toISOString();

    const [signalsRes, perfRes, periodRes, globalRes, fngRes] = await Promise.allSettled([
      fetchActiveSignals({ ...ACTIVE_SIGNAL_PARAMS, page_size: 100 }),
      fetchPerformanceSummary(),
      fetchSignalHistoryStats({ date_from: dateFrom }),
      fetchGlobalMarket(),
      fetchFearGreed(),
    ]);

    // Tek response = tek evren: satırlar (items) + sayaç (total) aynı fetch'ten.
    if (signalsRes.status === 'fulfilled') {
      setSignals(signalsRes.value.items);
      setActionableActiveCount(signalsRes.value.total);
    }
    if (perfRes.status === 'fulfilled') setPerf(perfRes.value);
    if (periodRes.status === 'fulfilled') setPeriodStats(periodRes.value);
    if (globalRes.status === 'fulfilled') {
      const g = globalRes.value;
      setGlobal(g);
      setGlobalError(false);
    } else {
      setGlobalError(true);
    }
    if (fngRes.status === 'fulfilled') setFng(fngRes.value);

    // Both core platform fetches failing = backend unreachable, not "0 signals".
    setDataError(signalsRes.status === 'rejected' && perfRes.status === 'rejected');

    setLoading(false);
    setRefreshing(false);
  }, [timeRange]);

  useEffect(() => {
    load();
    // Signal counts churn continuously in the background (scheduler regen +
    // live TP/SL/reversal resolution every few minutes) — without this the
    // stat cards go stale within minutes of opening the page.
    const id = setInterval(() => load(true), 30_000);
    return () => clearInterval(id);
  }, [load]);

  useEffect(() => {
    const saved = window.localStorage.getItem('tm.dashboard.density');
    if (saved === 'compact' || saved === 'comfortable') setDensity(saved);
  }, []);

  const changeDensity = (d: Density) => {
    setDensity(d);
    try { window.localStorage.setItem('tm.dashboard.density', d); } catch {}
  };

  const handleSignalSelect = (sig: ApiSignal) => {
    setSelectedSignal((prev) => (prev?.id === sig.id ? null : sig));
  };

  useEffect(() => {
    if (selectedSignal && !signals.find((s) => s.id === selectedSignal.id)) {
      setSelectedSignal(null);
    }
  }, [signals, selectedSignal]);

  // Derived stats
  const activeCount = actionableActiveCount;
  const winRate = perf?.win_rate ?? 0;
  const avgReturn = perf?.average_return ?? 0;
  const fngValue = fng?.value ?? 50;
  const periodPhrase = timeRange === '24s' ? '24 saatte' : timeRange === '7g' ? '7 günde' : '30 günde';
  const periodClosedCount = periodStats?.closed_count ?? 0;
  const periodLabel = timeRange === '24s' ? 'son 24 saat' : timeRange === '7g' ? 'son 7 gün' : 'son 30 gün';
  // Lifecycle-health census over ALL active signals (not just the recent 6) —
  // client-derived from the already-fetched list, no endpoint.
  const lifecycleCounts = signals.reduce<Record<string, number>>((acc, s) => {
    if (s.live_status) acc[s.live_status] = (acc[s.live_status] ?? 0) + 1;
    return acc;
  }, {});
  // AI Görüşü + Risk Dağılımı aggregates — client-derived from active signals.
  const longCount = signals.filter((s) => String(s.direction ?? '').toLowerCase().includes('bull')).length;
  const shortCount = signals.filter((s) => String(s.direction ?? '').toLowerCase().includes('bear')).length;
  const avgConfidence = signals.length
    ? Math.round(signals.reduce((a, s) => a + (s.confidence_score || 0), 0) / signals.length)
    : 0;
  const winCount = perf?.win_count ?? 0;
  const lossCount = perf?.loss_count ?? 0;
  const breakevenCount = perf?.breakeven_count ?? 0;

  // Real compounded total return from the backend's resolved-trade equity
  // curve (10000 starting capital), instead of avgReturn * totalSignals —
  // that multiplication produces a meaningless number once totalSignals is
  // in the thousands (e.g. "+12214%").
  const equityCurve = perf?.historical_equity_curve ?? [];
  const totalReturnPct = equityCurve.length > 1
    ? ((equityCurve[equityCurve.length - 1].capital - equityCurve[0].capital) / equityCurve[0].capital) * 100
    : 0;

  return (
    <div className="space-y-5">
      {/* First-run onboarding checklist + welcome tour (frontend-only, localStorage) */}
      <OnboardingChecklist />
      <CoachmarkTour />

      {/* Free tier banner — hidden in beta while the payment funnel is disabled */}
      {isFreeTier && PAYMENTS_ENABLED && (
        <Link
          href="/pricing"
          className="block bg-gradient-to-r from-amber/15 via-accent-primary/15 to-amber/15 border border-amber/30 rounded-2xl p-4 hover:border-amber/50 transition-all"
        >
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-amber/20 flex items-center justify-center flex-shrink-0">
                <Lock className="w-5 h-5 text-amber" />
              </div>
              <div>
                <p className="text-sm font-display text-text-primary">
                  Ücretsiz plandasın — günde {limits.daily_signal_limit} sinyal görüntülüyorsun.
                </p>
                <p className="text-micro text-text-secondary mt-0.5">
                  Sınırsız sinyal, Telegram bildirimleri, backtest ve daha fazlası için Pro plana yükselt.
                </p>
              </div>
            </div>
            <span className="flex items-center gap-1.5 text-xs font-display text-amber whitespace-nowrap bg-amber/10 border border-amber/30 px-3 py-1.5 rounded-xl">
              <Crown className="w-3.5 h-3.5" /> Yükselt
            </span>
          </div>
        </Link>
      )}

      {/* ── Title Row ── */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-3">
        <div>
          <h1 className="text-h2 font-display text-text-primary">
            {firstName ? `Hoş geldin, ${firstName}` : 'Gösterge Paneli'}
          </h1>
          <p className="text-sm text-text-secondary mt-0.5">Piyasaları yapay zekâ ile analiz edin, avantaj yakalayın.</p>
        </div>
        <div className="flex items-center gap-3">
          <LiveClock />
          <div className="flex bg-bg-secondary border border-border-subtle p-0.5 rounded-lg">
            {(['24s', '7g', '30g'] as const).map((r) => (
              <button
                key={r}
                onClick={() => setTimeRange(r)}
                className={`px-3 py-1 text-xs font-display rounded-md transition-all ${
                  timeRange === r ? 'bg-bg-tertiary text-text-primary' : 'text-text-muted hover:text-text-primary'
                }`}
              >
                {r === '24s' ? '24 Saat' : r === '7g' ? '7 Gün' : '30 Gün'}
              </button>
            ))}
          </div>
          <button
            onClick={() => load(true)}
            disabled={refreshing}
            className="p-2 rounded-lg bg-bg-secondary border border-border-subtle text-text-muted hover:text-text-primary transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <InvestmentDisclaimer variant="inline" />

      {/* ── Durum Bandı — 3-saniye "Şu an" özeti (DE-1, additif, mevcut veriden) ── */}
      <DurumBandi
        periodPhrase={periodPhrase}
        closedCount={periodClosedCount}
        winRate={winRate}
        avgReturn={avgReturn}
        activeCount={activeCount}
        loading={loading}
        hasData={!!perf && !dataError}
      />

      {/* ── 5 Stat Cards ── */}
      {loading ? (
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <GlassCard key={i} dense>
              <div className="h-2.5 w-24 rounded bg-white/[0.06]" />
              <div className="h-8 w-20 mt-2 rounded bg-white/[0.06]" />
              <div className="h-2 w-28 mt-2 rounded bg-white/[0.04]" />
            </GlassCard>
          ))}
        </div>
      ) : dataError && !perf ? (
        <GlassCard className="flex flex-col items-center justify-center text-center gap-3 py-8">
          <AlertTriangle className="w-6 h-6 text-bearish" />
          <div>
            <p className="text-sm font-display text-text-primary">Veriler şu an yüklenemiyor</p>
            <p className="text-xs text-text-muted mt-0.5">Sunucuya ulaşılamıyor olabilir. Lütfen tekrar deneyin.</p>
          </div>
          <button
            onClick={() => load(true)}
            disabled={refreshing}
            className="text-xs font-display text-text-primary bg-white/[0.06] hover:bg-e-2 border border-border-medium px-4 py-2 rounded-lg transition-colors disabled:opacity-50"
          >
            Tekrar dene
          </button>
        </GlassCard>
      ) : (
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        {/* Closed trades within selected period */}
        <GlassCard dense className="flex items-center justify-between group">
          <div>
            <span className="text-micro font-medium text-text-muted uppercase">Bu Dönemde Kapanan İşlem</span>
            <h3 className="text-h1 num font-num-560 mt-1 text-text-primary">{periodClosedCount}</h3>
            <span className="text-micro text-text-muted font-medium mt-1 block">
              {timeRange === '24s' ? 'son 24 saat' : timeRange === '7g' ? 'son 7 gün' : 'son 30 gün'}
            </span>
          </div>
          <div className="w-10 h-10 rounded-xl bg-amber/10 border border-amber/20 flex items-center justify-center">
            <Activity className="w-5 h-5 text-amber" />
          </div>
        </GlassCard>

        {/* Active Signals */}
        <GlassCard dense className="flex items-center justify-between group">
          <div>
            <span className="text-micro font-medium text-text-muted uppercase">Aktif Sinyaller</span>
            <h3 className="text-h1 num font-num-560 mt-1 text-text-primary">{activeCount}</h3>
            <span className="text-micro text-text-muted font-medium mt-1 block">
              şu an işlem fırsatı (LONG/SHORT)
            </span>
          </div>
          <div className="w-10 h-10 rounded-xl bg-accent-primary/10 border border-accent-primary/20 flex items-center justify-center">
            <Zap className="w-5 h-5 text-accent-primary" />
          </div>
        </GlassCard>

        {/* Win Rate */}
        <GlassCard dense className="flex items-center justify-between group">
          <div>
            <span className="text-micro font-medium text-text-muted uppercase">Başarı Oranı</span>
            <h3 className="text-h1 num font-num-560 mt-1 text-bullish">{formatPercentage(winRate, 0, false)}</h3>
            <span className="text-micro text-text-muted font-medium mt-1 block">
              {/* Win rate = win / (win + loss + breakeven) — the canonical
                  platform definition (breakeven dilutes it, which is why this
                  is below 50% even though wins outnumber losses). Show the full
                  resolved breakdown so the percentage is self-consistent. */}
              tüm zamanlar · {winCount}G / {lossCount}K / {breakevenCount}BE
            </span>
          </div>
          <div className="w-10 h-10 rounded-xl bg-bullish/10 border border-bullish/20 flex items-center justify-center">
            <CheckCircle className="w-5 h-5 text-bullish" />
          </div>
        </GlassCard>

        {/* Avg Return */}
        <GlassCard dense className="flex items-center justify-between group">
          <div>
            <span className="text-micro font-medium text-text-muted uppercase">Ortalama Getiri</span>
            <h3 className={cn("text-h1 num font-num-560 mt-1", avgReturn >= 0 ? "text-bullish" : "text-bearish")}>{formatPercentage(avgReturn)}</h3>
            <span className="text-micro text-text-muted font-medium mt-1 block">
              tüm zamanlar · işlem başına
            </span>
          </div>
          <div className="w-10 h-10 rounded-xl bg-bg-tertiary border border-border-subtle flex items-center justify-center">
            <ChartIcon className="w-5 h-5 text-accent-ui" />
          </div>
        </GlassCard>

        {/* Fear & Greed */}
        <GlassCard dense className="flex items-center justify-between group">
          <div>
            <span className="text-micro font-medium text-text-muted uppercase">Piyasa Greed Index</span>
            <h3 className="text-h1 num font-num-560 mt-1" style={{ color: fngColor(fngValue) }}>
              {fngValue}
            </h3>
            <span className="text-micro font-medium mt-1 block" style={{ color: fngColor(fngValue) }}>
              {fngLabel(fngValue)}
            </span>
          </div>
          {/* Mini gauge */}
          {/* M-0b: hover'daki JS-inline renkli-glow KALDIRILDI (Doctrine: glow yalnız CTA +
              data-lifecycle-event; gölge animate edilmez; gate-2 renkli-glow — JS'te olduğu
              için lint göremiyordu). 300ms süre borcu da bununla düştü. */}
          <div className="relative w-12 h-12 flex-shrink-0 rounded-full">
            <svg viewBox="0 0 44 44" className="w-full h-full -rotate-90">
              {/* white-alpha .05 → hl10 (D9-12); SVG attr var() çözmez → CSS stroke property */}
              <circle cx="22" cy="22" r="18" fill="none" style={{ stroke: 'var(--hl10)' }} strokeWidth="4" />
              <circle
                cx="22" cy="22" r="18" fill="none"
                stroke={fngColor(fngValue)} strokeWidth="4"
                strokeDasharray={`${(fngValue / 100) * 113} 113`}
                strokeLinecap="round"
              />
            </svg>
          </div>
        </GlassCard>
      </div>
      )}

      {/* ── AI Görüşü — aktif sinyallerden client-türetilir (DE-3). CP-DASH-A:
          Risk Dağılımı KALDIRILDI → Signal Center risk-enstrümanı (CP-SIGNAL-C;
          §03 widget-taşıma-kilidi). AI Görüşü kart-formu DASH-C'de Nabız
          sistem-sesine dönecek. ── */}
      {signals.length > 0 && (
        <AIGorusu longCount={longCount} shortCount={shortCount} avgConfidence={avgConfidence} />
      )}

      {/* ── Şu an — aktif sinyaller tam-genişlik tablo (DE-5c) ── */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-display text-text-primary flex items-center gap-2">
            <Zap className="w-4 h-4 text-accent-primary" />
            Aktif Sinyaller
          </h2>
          <div className="flex items-center gap-3">
            <DensityToggle value={density} onChange={changeDensity} />
            <Link href="/signals" className="text-xs text-accent-primary hover:text-accent-ui flex items-center gap-1">
              Tümünü Gör <ArrowRight className="w-3 h-3" />
            </Link>
          </div>
        </div>
        <LifecycleHealth counts={lifecycleCounts} />
        <SignalTable
          rows={signals}
          livePrices={livePrices}
          onSelect={handleSignalSelect}
          selectedId={selectedSignal?.id}
          loading={loading}
          showEmpty={!loading && signals.length === 0}
          emptyState={
            <EmptyState
              icon={<Zap className="w-6 h-6 text-accent-primary" />}
              title="Henüz sinyal yok"
              description="AI motorları piyasayı 7/24 tarıyor. Tüm aktif AL/SAT sinyallerini Sinyal Merkezi'nde incele."
              action={
                <Link
                  href="/signals"
                  className="focus-ring inline-flex items-center gap-1.5 text-xs font-display bg-accent-primary hover:bg-accent-hover text-white px-4 py-2 rounded-xl transition-colors"
                >
                  Sinyal Merkezi&apos;ne git <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              }
              className="my-2"
            />
          }
          density={density}
        />

        {/* ── Neden — seçili sinyalin inline detay paneli (DE-5e) ── */}
        {/* PI-2c: açılış/kapanış disclosure settle (scaleIn, PI-1a mekanizması). */}
        <ReasonPanel signal={selectedSignal} onClose={() => setSelectedSignal(null)} />
      </div>

      {/* ── Sicil — dönem performansı + gerçekleşmiş sonuçlar (DE-5f) ── */}
      <Sicil
        totalReturn={totalReturnPct}
        profitFactor={periodStats?.profit_factor ?? null}
        maxDrawdown={perf?.drawdown_analysis?.max_drawdown ?? 0}
        tpHitRate={periodStats?.tp_hit_rate ?? 0}
        slRate={periodStats?.sl_rate ?? 0}
        bestSignal={periodStats?.best_signal ?? null}
        worstSignal={periodStats?.worst_signal ?? null}
        periodLabel={periodLabel}
        loading={loading}
        hasData={!!perf && !!periodStats && !dataError}
      />

      {/* ── Piyasa Bağlamı — tek kompakt satır (CP-DASH-A · §03 widget-taşıma-kilidi).
          BTC canlı grafik (TradingView) + Varlık Dağılımı (pie) + En Çok Kazananlar
          KALDIRILDI: piyasa-tarama/enstrüman evi = /markets · Signal Center
          filtre-sayaçları (guardrail-7). Global makro yalnız sade bağlam-satırında
          kalır — pie/gauge/grafik/gömülü-enstrüman YOK. ── */}
      {global ? (
        <GlassCard dense className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <span className="text-micro text-text-muted uppercase font-medium">Piyasa Bağlamı</span>
          <span className="flex items-baseline gap-1.5">
            <span className="text-micro text-text-muted uppercase">Piyasa Değeri</span>
            <span className="text-sm num font-num-520 text-text-primary">{formatLargeNumber(global.total_market_cap_usd)}</span>
            <span className={cn('text-micro font-medium', (global.market_cap_change_24h ?? 0) >= 0 ? 'text-bullish' : 'text-bearish')}>
              {formatPercentage(global.market_cap_change_24h)}
            </span>
          </span>
          <span className="flex items-baseline gap-1.5">
            <span className="text-micro text-text-muted uppercase">24s Hacim</span>
            <span className="text-sm num font-num-520 text-text-primary">{formatLargeNumber(global.total_volume_usd)}</span>
          </span>
          <span className="flex items-baseline gap-1.5">
            <span className="text-micro text-text-muted uppercase">BTC Dom</span>
            <span className="text-sm num font-num-520 text-text-primary">{formatPercentage(global.btc_dominance, 2, false)}</span>
          </span>
          <span className="flex items-baseline gap-1.5">
            <span className="text-micro text-text-muted uppercase">ETH Dom</span>
            <span className="text-sm num font-num-520 text-text-primary">{formatPercentage(global.eth_dominance, 2, false)}</span>
          </span>
          <Link href="/markets" className="ml-auto text-xs text-accent-primary hover:text-accent-ui flex items-center gap-1">
            Piyasalar <ArrowRight className="w-3 h-3" />
          </Link>
        </GlassCard>
      ) : globalError ? (
        <p className="text-micro text-amber bg-amber/10 border border-amber/20 rounded-lg px-3 py-2">
          Piyasa verisi şu an alınamıyor (kaynak geçici sınırladı) — otomatik tekrar denenecek.
        </p>
      ) : null}
    </div>
  );
}
