'use client';

import React, { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import {
  TrendingUp, TrendingDown, Zap, CheckCircle, AlertTriangle,
  LineChart as ChartIcon, ArrowRight, RefreshCw, Activity,
} from 'lucide-react';
import {
  ResponsiveContainer, PieChart, Pie, Cell,
} from 'recharts';
import { GlassCard } from '@/components/ui/GlassCard';
import { CoinIcon } from '@/components/ui/CoinIcon';
import { SignalBadge } from '@/components/ui/SignalBadge';
import { ScoreRing } from '@/components/ui/ScoreRing';
import {
  fetchActiveSignals, fetchPerformanceSummary, fetchSignalHistoryStats,
  fetchGlobalMarket, fetchFearGreed, fetchTopGainers,
  type ApiSignal, type PerformanceSummary, type GlobalMarketData,
  type FearGreedData, type CoinMarket,
} from '@/lib/api';
import { formatLargeNumber, formatPercentage, cn, formatPrice } from '@/lib/utils';
import { PAYMENTS_ENABLED } from '@/lib/config';
import { InvestmentDisclaimer } from '@/components/legal/InvestmentDisclaimer';
import { SignalType, RiskLevel } from '@/types';
import { useLivePrices } from '@/hooks/useLivePrices';
import { useTierLimits } from '@/hooks/useTierLimits';
import { useAuth } from '@/lib/auth-context';
import { EmptyState } from '@/components/ui/EmptyState';
import OnboardingChecklist from '@/components/dashboard/OnboardingChecklist';
import CoachmarkTour from '@/components/dashboard/CoachmarkTour';
import { Crown, Lock } from 'lucide-react';
import TradingViewChart from '@/components/charts/TradingViewChart';
import { chartColor } from '@/lib/chartColors';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// Renk migration (P9.7/D9-09): pie DOLGU — cyan-yüzey yasak (COL-07/D9-11) →
// cyan'sız owned dizi: accent-ailesi + nötr metin-tonları (kategorik ayrım).
const PIE_COLORS = [chartColor('accent'), chartColor('accentUi'), chartColor('tx2'), chartColor('tx3')];

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
// Main Dashboard
// ---------------------------------------------------------------------------

export default function DashboardPage() {
  const [timeRange, setTimeRange] = useState<'24s' | '7g' | '30g'>('24s');

  const [signals, setSignals] = useState<ApiSignal[]>([]);
  const [perf, setPerf] = useState<PerformanceSummary | null>(null);
  const [global, setGlobal] = useState<GlobalMarketData | null>(null);
  const [fng, setFng] = useState<FearGreedData | null>(null);
  const [gainers, setGainers] = useState<CoinMarket[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  // CoinGecko's free API rate-limits (503) under repeated calls — when that
  // happens we keep showing the last successfully fetched values (if any)
  // instead of wiping them, and surface a clear message instead of leaving
  // the cards stuck on "—" / "Yükleniyor..." forever with no explanation.
  const [globalError, setGlobalError] = useState(false);
  const [gainersError, setGainersError] = useState(false);
  // Core platform data (signals + performance) unreachable — surface an honest
  // error + retry instead of rendering misleading zeros as if they were real.
  const [dataError, setDataError] = useState(false);
  // Actual count of actionable (non-HOLD) active signals — matches what
  // Sinyal Merkezi shows by default ("SADECE AL/SAT"), unlike perf.active_count
  // which includes HOLD and so reads much higher than what's really tradeable.
  const [actionableActiveCount, setActionableActiveCount] = useState(0);
  // Closed trades within the selected 24s/7g/30g window — replaces the old
  // "Toplam Sinyal" (all-time, ignored the period selector entirely).
  const [periodClosedCount, setPeriodClosedCount] = useState(0);

  const signalSymbols = signals.slice(0, 6).map((s) => s.asset?.symbol ?? '').filter(Boolean);
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

    const [signalsRes, actionableRes, perfRes, periodRes, globalRes, fngRes, gainersRes] = await Promise.allSettled([
      fetchActiveSignals({ page_size: 100 }),
      fetchActiveSignals({ only_actionable: true, page_size: 1 }),
      fetchPerformanceSummary(),
      fetchSignalHistoryStats({ date_from: dateFrom }),
      fetchGlobalMarket(),
      fetchFearGreed(),
      fetchTopGainers(5),
    ]);

    if (signalsRes.status === 'fulfilled') setSignals(signalsRes.value.items);
    if (actionableRes.status === 'fulfilled') setActionableActiveCount(actionableRes.value.total);
    if (perfRes.status === 'fulfilled') setPerf(perfRes.value);
    if (periodRes.status === 'fulfilled') setPeriodClosedCount(periodRes.value.closed_count);
    if (globalRes.status === 'fulfilled') {
      const g = globalRes.value;
      setGlobal(g);
      setGlobalError(false);
    } else {
      setGlobalError(true);
    }
    if (fngRes.status === 'fulfilled') setFng(fngRes.value);
    if (gainersRes.status === 'fulfilled') {
      setGainers(gainersRes.value);
      setGainersError(false);
    } else {
      setGainersError(true);
    }

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

  // Derived stats
  const activeCount = actionableActiveCount;
  const winRate = perf?.win_rate ?? 0;
  const avgReturn = perf?.average_return ?? 0;
  const fngValue = fng?.value ?? 50;

  // Win rate's true denominator is win + loss + breakeven (the canonical
  // platform definition). Derive shares from the SAME denominator so the cards
  // are internally consistent: wins are `winRate`% of resolved, losses are
  // `lossShare`% — they don't sum to 100 because breakeven takes the rest.
  const winCount = perf?.win_count ?? 0;
  const lossCount = perf?.loss_count ?? 0;
  const breakevenCount = perf?.breakeven_count ?? 0;
  const resolvedCount = winCount + lossCount + breakevenCount;
  const lossShare = resolvedCount ? Math.round((lossCount / resolvedCount) * 100) : 0;

  // "Son Sinyaller" widget only needs the newest 6, but the asset-distribution
  // pie needs a much larger sample — otherwise it's just 6 equally-weighted
  // slices that look like a real allocation but aren't.
  const recentSignals = signals.slice(0, 6);

  const assetCounts: Record<string, number> = {};
  signals.forEach((s) => {
    const sym = s.asset?.symbol ?? 'Other';
    assetCounts[sym] = (assetCounts[sym] ?? 0) + 1;
  });
  const pieData = Object.entries(assetCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([name, value]) => ({ name, value }));
  if (pieData.length === 0) {
    pieData.push({ name: 'Veri Yok', value: 1 });
  }

  // Real compounded total return from the backend's resolved-trade equity
  // curve (10000 starting capital), instead of avgReturn * totalSignals —
  // that multiplication produces a meaningless number once totalSignals is
  // in the thousands (e.g. "+12214%").
  const equityCurve = perf?.historical_equity_curve ?? [];
  const totalReturnPct = equityCurve.length > 1
    ? ((equityCurve[equityCurve.length - 1].capital - equityCurve[0].capital) / equityCurve[0].capital) * 100
    : 0;

  const perfCards = [
    { label: 'Toplam Getiri', value: formatPercentage(totalReturnPct), color: totalReturnPct >= 0 ? 'text-bullish' : 'text-bearish' },
    { label: 'Kazanılan İşlemler', value: `${winCount}`, sub: `↗ ${formatPercentage(winRate, 0, false)}`, color: 'text-bullish' },
    { label: 'Kaybedilen İşlemler', value: `${lossCount}`, sub: `↘ ${formatPercentage(lossShare, 0, false)}`, color: 'text-bearish' },
    { label: 'Ortalama Getiri', value: formatPercentage(avgReturn), color: 'text-accent-secondary' },
  ];

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
                <p className="text-sm font-bold text-text-primary">
                  Ücretsiz plandasın — günde {limits.daily_signal_limit} sinyal görüntülüyorsun.
                </p>
                <p className="text-[11px] text-text-secondary mt-0.5">
                  Sınırsız sinyal, Telegram bildirimleri, backtest ve daha fazlası için Pro plana yükselt.
                </p>
              </div>
            </div>
            <span className="flex items-center gap-1.5 text-xs font-bold text-amber whitespace-nowrap bg-amber/10 border border-amber/30 px-3 py-1.5 rounded-xl">
              <Crown className="w-3.5 h-3.5" /> Yükselt
            </span>
          </div>
        </Link>
      )}

      {/* ── Title Row ── */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-3">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-text-primary">
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
                className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${
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

      {/* ── 5 Stat Cards ── */}
      {loading ? (
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <GlassCard key={i} className="p-4">
              <div className="h-2.5 w-24 rounded bg-white/[0.06] animate-pulse" />
              <div className="h-8 w-20 mt-2 rounded bg-white/[0.06] animate-pulse" />
              <div className="h-2 w-28 mt-2 rounded bg-white/[0.04] animate-pulse" />
            </GlassCard>
          ))}
        </div>
      ) : dataError && !perf ? (
        <GlassCard className="flex flex-col items-center justify-center text-center gap-3 py-8">
          <AlertTriangle className="w-6 h-6 text-bearish" />
          <div>
            <p className="text-sm font-semibold text-text-primary">Veriler şu an yüklenemiyor</p>
            <p className="text-xs text-text-muted mt-0.5">Sunucuya ulaşılamıyor olabilir. Lütfen tekrar deneyin.</p>
          </div>
          <button
            onClick={() => load(true)}
            disabled={refreshing}
            className="text-xs font-semibold text-text-primary bg-white/[0.06] hover:bg-white/[0.1] border border-border-medium px-4 py-2 rounded-lg transition-colors disabled:opacity-50"
          >
            Tekrar dene
          </button>
        </GlassCard>
      ) : (
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        {/* Closed trades within selected period */}
        <GlassCard className="flex items-center justify-between p-4 group" glowEffect glowColor="primary">
          <div>
            <span className="text-[10px] font-semibold text-text-muted uppercase tracking-wide">Bu Dönemde Kapanan İşlem</span>
            <h3 className="text-3xl font-bold font-mono mt-1 text-text-primary">{periodClosedCount}</h3>
            <span className="text-[10px] text-text-muted font-semibold mt-1 block">
              {timeRange === '24s' ? 'son 24 saat' : timeRange === '7g' ? 'son 7 gün' : 'son 30 gün'}
            </span>
          </div>
          <div className="w-10 h-10 rounded-xl bg-amber/10 border border-amber/20 flex items-center justify-center">
            <Activity className="w-5 h-5 text-amber" />
          </div>
        </GlassCard>

        {/* Active Signals */}
        <GlassCard className="flex items-center justify-between p-4 group" glowEffect glowColor="primary">
          <div>
            <span className="text-[10px] font-semibold text-text-muted uppercase tracking-wide">Aktif Sinyaller</span>
            <h3 className="text-3xl font-bold font-mono mt-1 text-text-primary">{activeCount}</h3>
            <span className="text-[10px] text-text-muted font-semibold mt-1 block">
              şu an işlem fırsatı (LONG/SHORT)
            </span>
          </div>
          <div className="w-10 h-10 rounded-xl bg-accent-primary/10 border border-accent-primary/20 flex items-center justify-center transition-shadow duration-300 group-hover:shadow-glow-md">
            <Zap className="w-5 h-5 text-accent-primary" />
          </div>
        </GlassCard>

        {/* Win Rate */}
        <GlassCard className="flex items-center justify-between p-4 group" glowEffect glowColor="bullish">
          <div>
            <span className="text-[10px] font-semibold text-text-muted uppercase tracking-wide">Başarı Oranı</span>
            <h3 className="text-3xl font-bold font-mono mt-1 text-bullish">{formatPercentage(winRate, 0, false)}</h3>
            <span className="text-[10px] text-text-muted font-semibold mt-1 block">
              {/* Win rate = win / (win + loss + breakeven) — the canonical
                  platform definition (breakeven dilutes it, which is why this
                  is below 50% even though wins outnumber losses). Show the full
                  resolved breakdown so the percentage is self-consistent. */}
              tüm zamanlar · {winCount}G / {lossCount}K / {breakevenCount}BE
            </span>
          </div>
          <div className="w-10 h-10 rounded-xl bg-bullish/10 border border-bullish/20 flex items-center justify-center transition-shadow duration-300 group-hover:shadow-glow-bullish">
            <CheckCircle className="w-5 h-5 text-bullish" />
          </div>
        </GlassCard>

        {/* Avg Return */}
        <GlassCard className="flex items-center justify-between p-4 group" glowEffect glowColor={avgReturn >= 0 ? 'bullish' : 'bearish'}>
          <div>
            <span className="text-[10px] font-semibold text-text-muted uppercase tracking-wide">Ortalama Getiri</span>
            <h3 className="text-3xl font-bold font-mono mt-1 text-accent-secondary">{formatPercentage(avgReturn)}</h3>
            <span className="text-[10px] text-text-muted font-semibold mt-1 block">
              tüm zamanlar · işlem başına
            </span>
          </div>
          <div className="w-10 h-10 rounded-xl bg-accent-secondary/10 border border-accent-secondary/20 flex items-center justify-center transition-shadow duration-300 group-hover:shadow-glow-md">
            <ChartIcon className="w-5 h-5 text-accent-secondary" />
          </div>
        </GlassCard>

        {/* Fear & Greed */}
        <GlassCard className="flex items-center justify-between p-4 group">
          <div>
            <span className="text-[10px] font-semibold text-text-muted uppercase tracking-wide">Piyasa Greed Index</span>
            <h3 className="text-3xl font-bold font-mono mt-1" style={{ color: fngColor(fngValue) }}>
              {fngValue}
            </h3>
            <span className="text-[10px] font-semibold mt-1 block" style={{ color: fngColor(fngValue) }}>
              {fngLabel(fngValue)}
            </span>
          </div>
          {/* Mini gauge */}
          <div
            className="relative w-12 h-12 flex-shrink-0 rounded-full transition-shadow duration-300"
            style={{ '--tw-shadow-color': fngColor(fngValue) } as React.CSSProperties}
            onMouseEnter={(e) => { e.currentTarget.style.boxShadow = `0 0 16px ${fngColor(fngValue)}55`; }}
            onMouseLeave={(e) => { e.currentTarget.style.boxShadow = 'none'; }}
          >
            <svg viewBox="0 0 44 44" className="w-full h-full -rotate-90">
              <circle cx="22" cy="22" r="18" fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="4" />
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

      {/* ── Main Grid ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Market Overview — left 2/3 */}
        <div className="lg:col-span-2 space-y-5">
          <GlassCard className="p-5">
            {/* Card header */}
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-bold text-text-primary flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-accent-primary" />
                Piyasa Genel Bakış
              </h2>
            </div>

            {globalError && (
              <p className="text-[11px] text-amber bg-amber/10 border border-amber/20 rounded-lg px-3 py-2 mb-3">
                Piyasa verisi şu an alınamıyor (kaynak geçici olarak sınırlandırıyor — CoinGecko rate limit).
                {global ? ' Aşağıda son bilinen değerler gösteriliyor.' : ' 30 saniye içinde otomatik tekrar denenecek.'}
              </p>
            )}
            {/* Market stats row */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-5">
              <div>
                <p className="text-[10px] text-text-muted uppercase font-semibold">Toplam Piyasa Değeri</p>
                <p className="text-base font-bold font-mono text-text-primary mt-0.5">
                  {global ? formatLargeNumber(global.total_market_cap_usd) : '—'}
                </p>
                <p className={`text-[11px] font-semibold ${(global?.market_cap_change_24h ?? 0) >= 0 ? 'text-bullish' : 'text-bearish'}`}>
                  {global ? formatPercentage(global.market_cap_change_24h) : '—'}
                </p>
              </div>
              <div>
                <p className="text-[10px] text-text-muted uppercase font-semibold">24s Hacim</p>
                <p className="text-base font-bold font-mono text-text-primary mt-0.5">
                  {global ? formatLargeNumber(global.total_volume_usd) : '—'}
                </p>
              </div>
              <div>
                <p className="text-[10px] text-text-muted uppercase font-semibold">BTC Dominance</p>
                <p className="text-base font-bold font-mono text-text-primary mt-0.5">
                  {global ? formatPercentage(global.btc_dominance, 2, false) : '—'}
                </p>
              </div>
              <div>
                <p className="text-[10px] text-text-muted uppercase font-semibold">ETH Dominance</p>
                <p className="text-base font-bold font-mono text-text-primary mt-0.5">
                  {global ? formatPercentage(global.eth_dominance, 2, false) : '—'}
                </p>
              </div>
            </div>

          </GlassCard>

          {/* Featured Live Chart */}
          <GlassCard className="p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-bold text-text-primary flex items-center gap-2">
                <ChartIcon className="w-4 h-4 text-accent-primary" />
                Canlı Grafik — BTC/USDT
              </h2>
              <Link href="/markets/BTCUSDT" className="text-xs text-accent-primary hover:text-accent-ui flex items-center gap-1">
                Detay <ArrowRight className="w-3 h-3" />
              </Link>
            </div>
            <TradingViewChart symbol="BTCUSDT" timeframe="1h" height={360} compact />
          </GlassCard>

          {/* Performance Summary */}
          <GlassCard className="p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-bold text-text-primary flex items-center gap-2">
                <Activity className="w-4 h-4 text-accent-primary" />
                Performans Özeti
              </h2>
              <Link href="/performance" className="text-xs text-accent-primary hover:text-accent-ui flex items-center gap-1">
                Tümünü Gör <ArrowRight className="w-3 h-3" />
              </Link>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {perfCards.map((c, i) => (
                <div key={i} className="p-3 bg-bg-secondary/60 border border-border-subtle rounded-xl">
                  <p className="text-[10px] text-text-muted uppercase font-semibold">{c.label}</p>
                  <p className={`text-xl font-bold font-mono mt-1 ${c.color}`}>{c.value}</p>
                  {c.sub && <p className="text-[10px] text-text-muted mt-0.5">{c.sub}</p>}
                </div>
              ))}
            </div>
          </GlassCard>
        </div>

        {/* Right column — Signals + extras */}
        <div className="space-y-5">
          {/* Recent Signals */}
          <GlassCard className="p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-bold text-text-primary flex items-center gap-2">
                <Zap className="w-4 h-4 text-accent-primary" />
                Son Sinyaller
              </h2>
              <Link href="/signals" className="text-xs text-accent-primary hover:text-accent-ui flex items-center gap-1">
                Tümünü Gör <ArrowRight className="w-3 h-3" />
              </Link>
            </div>

            {loading ? (
              <div className="py-8 flex justify-center">
                <div className="w-6 h-6 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" />
              </div>
            ) : recentSignals.length === 0 ? (
              <EmptyState
                icon={<Zap className="w-6 h-6 text-accent-primary" />}
                title="Henüz sinyal yok"
                description="AI motorları piyasayı 7/24 tarıyor. Tüm aktif AL/SAT sinyallerini Sinyal Merkezi'nde incele."
                action={
                  <Link
                    href="/signals"
                    className="focus-ring inline-flex items-center gap-1.5 text-xs font-bold bg-accent-primary hover:bg-accent-hover text-white px-4 py-2 rounded-xl transition-colors"
                  >
                    Sinyal Merkezi&apos;ne git <ArrowRight className="w-3.5 h-3.5" />
                  </Link>
                }
                className="my-2"
              />
            ) : (
              <div className="space-y-3">
                {recentSignals.map((sig) => {
                  const dir = sig.signal_type?.toLowerCase() ?? '';
                  const isBullish = dir.includes('buy');
                  const isBearish = dir.includes('sell');
                  const hoverGlow = isBullish
                    ? 'hover:shadow-glow-bullish hover:border-bullish/30'
                    : isBearish
                    ? 'hover:shadow-glow-bearish hover:border-bearish/30'
                    : 'hover:shadow-glow-sm hover:border-border-medium';
                  return (
                  <div
                    key={sig.id}
                    className={cn(
                      "flex items-center gap-3 p-3 bg-bg-secondary/40 border border-border-subtle rounded-xl transition-all duration-300",
                      hoverGlow
                    )}
                  >
                    {/* Icon */}
                    <div className="w-8 h-8 rounded-lg bg-bg-tertiary border border-border-subtle flex items-center justify-center font-bold font-mono text-xs text-accent-primary flex-shrink-0 overflow-hidden">
                      {sig.asset?.symbol ? <CoinIcon symbol={sig.asset.symbol} assetType={sig.asset.asset_type} /> : '??'}
                    </div>

                    {/* Symbol + badge */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-text-primary">{sig.asset?.symbol}</span>
                        <SignalBadge type={sig.signal_type as SignalType} />
                      </div>
                      <div className="flex gap-3 mt-0.5">
                        {livePrices[sig.asset?.symbol ?? ''] ? (
                          <>
                            <span className="text-[10px] font-mono text-text-primary font-bold">
                              {formatPrice(livePrices[sig.asset?.symbol ?? ''].price)}
                            </span>
                            <span className={cn('text-[10px] font-mono font-semibold',
                              (livePrices[sig.asset?.symbol ?? ''].changePct24h ?? 0) >= 0 ? 'text-bullish' : 'text-bearish')}>
                              {formatPercentage(livePrices[sig.asset?.symbol ?? ''].changePct24h ?? 0)}
                            </span>
                          </>
                        ) : (
                          <>
                            <span className="text-[10px] text-text-muted">
                              TP: <span className="text-bullish font-mono">{sig.tp1 ? formatPrice(sig.tp1) : '—'}</span>
                            </span>
                            <span className="text-[10px] text-text-muted">
                              SL: <span className="text-bearish font-mono">{sig.stop_loss ? formatPrice(sig.stop_loss) : '—'}</span>
                            </span>
                          </>
                        )}
                      </div>
                    </div>

                    {/* Score ring */}
                    <ScoreRing score={sig.confidence_score} size={52} strokeWidth={4} />
                  </div>
                  );
                })}
              </div>
            )}
          </GlassCard>

          {/* Asset Distribution Pie */}
          <GlassCard className="p-5">
            <h2 className="text-base font-bold text-text-primary mb-4 flex items-center gap-2">
              <ChartIcon className="w-4 h-4 text-accent-primary" />
              Varlık Dağılımı
            </h2>
            <div className="flex items-center gap-4">
              <div className="w-28 h-28 flex-shrink-0">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={pieData} cx="50%" cy="50%" innerRadius={28} outerRadius={52} dataKey="value" paddingAngle={3}>
                      {pieData.map((_, i) => (
                        <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="flex-1 space-y-1.5">
                {pieData.map((entry, i) => (
                  <div key={i} className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full" style={{ backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }} />
                      <span className="text-xs text-text-secondary">{entry.name}</span>
                    </div>
                    <span className="text-xs font-semibold text-text-primary">
                      {formatPercentage((entry.value / pieData.reduce((a, b) => a + b.value, 0)) * 100, 0, false)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </GlassCard>

          {/* Top Gainers */}
          <GlassCard className="p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-bold text-text-primary flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-bullish" />
                En Çok Kazananlar
              </h2>
              <span className="text-[10px] text-text-muted bg-bg-secondary px-2 py-0.5 rounded">24 Saat</span>
            </div>
            {gainers.length === 0 ? (
              <p className="text-xs text-text-muted text-center py-4">
                {gainersError ? 'Veri şu an alınamıyor (kaynak sınırlandı) — otomatik tekrar denenecek.' : 'Yükleniyor...'}
              </p>
            ) : (
              <div className="space-y-2">
                {gainers.map((coin) => (
                  <div key={coin.id} className="flex items-center justify-between py-1.5 border-b border-border-subtle last:border-none">
                    <div className="flex items-center gap-2">
                      {coin.image ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={coin.image} alt={coin.symbol} className="w-5 h-5 rounded-full" />
                      ) : (
                        <div className="w-5 h-5 rounded-full bg-bg-tertiary border border-border-subtle" />
                      )}
                      <span className="text-xs font-bold text-text-primary uppercase">{coin.symbol}/USDT</span>
                    </div>
                    <span className={`text-xs font-bold font-mono ${(coin.price_change_percentage_24h ?? 0) >= 0 ? 'text-bullish' : 'text-bearish'}`}>
                      {formatPercentage(coin.price_change_percentage_24h ?? 0)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </GlassCard>
        </div>
      </div>
    </div>
  );
}
