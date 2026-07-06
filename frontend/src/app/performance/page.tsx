'use client';

import React, { useState, useEffect } from 'react';
import { chartColor } from '@/lib/chartColors';
import { useLanguage } from '@/lib/language-context';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import { ScoreRing } from '@/components/ui/ScoreRing';
import {
  TrendingUp, Play, Activity, CheckCircle,
  TrendingDown, PieChart as ChartIcon, Briefcase, FileDown, AlertTriangle,
} from 'lucide-react';
import { fetchPerformanceSummary, runBacktest, downloadPerformancePdf, type PerformanceSummary, type BacktestResult } from '@/lib/api';
import { formatPrice, formatPercentage } from '@/lib/utils';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  BarChart,
  Bar,
  Cell,
  PieChart as RechartsPieChart,
  Pie,
  Legend
} from 'recharts';
import { InvestmentDisclaimer } from '@/components/legal/InvestmentDisclaimer';

export default function PerformancePage() {
  const { tr } = useLanguage();
  const [activeTab, setActiveTab] = useState<'analytics' | 'backtest'>('analytics');
  
  const [stats, setStats] = useState<PerformanceSummary | null>(null);
  const [loadingStats, setLoadingStats] = useState(true);
  const [statsError, setStatsError] = useState<string | null>(null);

  const [symbol, setSymbol] = useState('BTCUSDT');
  const [timeframe, setTimeframe] = useState('1h');
  const [initialCapital, setInitialCapital] = useState('10000');
  const [riskPct, setRiskPct] = useState('2.0');
  const [maxAge, setMaxAge] = useState('48');
  const [executionModel, setExecutionModel] = useState('conservative');
  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null);
  const [runningBacktest, setRunningBacktest] = useState(false);
  const [backtestError, setBacktestError] = useState<string | null>(null);

  const fetchStats = async () => {
    setLoadingStats(true);
    setStatsError(null);
    try {
      const data = await fetchPerformanceSummary();
      setStats(data);
    } catch (err: any) {
      // No fake fallback — if the backend is unreachable, say so plainly
      // instead of showing invented numbers that look like real platform stats.
      setStats(null);
      setStatsError(err?.message?.includes('Failed to fetch') || err?.message?.includes('NetworkError')
        ? 'Sunucuya şu an ulaşılamıyor. Lütfen birazdan tekrar deneyin.'
        : 'Performans verileri yüklenemedi.');
    } finally {
      setLoadingStats(false);
    }
  };

  useEffect(() => {
    fetchStats();
  }, []);

  const handleRunBacktest = async (e: React.FormEvent) => {
    e.preventDefault();
    setRunningBacktest(true);
    setBacktestError(null);
    setBacktestResult(null);

    try {
      const data = await runBacktest({
        symbol: symbol.trim(),
        timeframe,
        initial_capital: parseFloat(initialCapital) || 10000.0,
        risk_pct: parseFloat(riskPct) || 2.0,
        max_age: parseInt(maxAge) || 48,
        execution_model: executionModel,
      });
      setBacktestResult(data);
    } catch (err: any) {
      console.error(err);
      // No fake fallback — a failed backtest must show an error, not an
      // invented result that looks like a real simulation outcome.
      setBacktestError(err.message || 'Backtest çalıştırılamadı.');
      setBacktestResult(null);
    } finally {
      setRunningBacktest(false);
    }
  };

  const chartColors = {
    bullish: chartColor('bull'),
    bearish: chartColor('bear'),   // 3.-kirmizi emekli
    accent: chartColor('accentUi'),   // equity CIZGI-iz (COL-04: accent yalniz dolgu)
    accentSecondary: chartColor('cyan'),   // backtest cizgisi (2.-cyan emekli; cizgi izinli)
    neutral: chartColor('tx3'),
    axis: chartColor('tx2')   // eksen etiketi >=tx2 (DoD)
  };

  return (
    <div className="space-y-6">
      <InvestmentDisclaimer variant="backtest" />
      {/* Title Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-text-primary">
            Performans & Test Merkezi
          </h1>
          <p className="text-sm text-text-secondary">
            Sinyal performans analizleri, başarı oranları ve geçmişe dönük simülasyonlar
          </p>
        </div>
        
        {/* Navigation Tabs + PDF */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => downloadPerformancePdf().catch(() =>
              alert('PDF indirilemedi. Pro/Premium aboneliği gerekir.'))}
            className="flex items-center gap-1.5 text-xs font-semibold text-text-muted hover:text-text-primary border border-border-subtle hover:border-accent-primary/40 px-3 py-2 rounded-lg transition-all"
          >
            <FileDown className="w-3.5 h-3.5" /> PDF
          </button>
        <div className="flex bg-bg-secondary border border-border-subtle p-1 rounded-xl">
          <button
            onClick={() => setActiveTab('analytics')}
            className={`px-4 py-2 text-xs font-semibold rounded-lg transition-all ${
              activeTab === 'analytics' ? 'bg-bg-tertiary text-text-primary ' : 'text-text-secondary hover:text-text-primary'
            }`}
          >
            <Activity className="w-3.5 h-3.5 inline mr-1.5" />
            Metrikler & Analitikler
          </button>
          <button
            onClick={() => setActiveTab('backtest')}
            className={`px-4 py-2 text-xs font-semibold rounded-lg transition-all ${
              activeTab === 'backtest' ? 'bg-bg-tertiary text-text-primary ' : 'text-text-secondary hover:text-text-primary'
            }`}
          >
            <Play className="w-3.5 h-3.5 inline mr-1.5" />
            Walk-Forward Backtest
          </button>
        </div>
        </div>
      </div>

      {activeTab === 'analytics' ? (
        <>
          {loadingStats ? (
            <div className="flex flex-col items-center justify-center p-20 space-y-4">
              <div className="w-10 h-10 border-4 border-accent-primary border-t-transparent rounded-full animate-spin" />
              <p className="text-sm text-text-secondary">Yükleniyor...</p>
            </div>
          ) : statsError || !stats ? (
            <GlassCard className="flex flex-col items-center justify-center p-20 text-center">
              <AlertTriangle className="w-12 h-12 text-bearish/60 mb-3" />
              <h4 className="text-sm font-bold text-text-secondary">{statsError ?? 'Veri bulunamadı'}</h4>
              <button onClick={fetchStats} className="mt-4 text-xs font-semibold text-accent-primary hover:underline">
                Yeniden dene →
              </button>
            </GlassCard>
          ) : (
            <div className="space-y-6">
              {/* Analytics Summary Cards */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <GlassCard className="flex justify-between items-center">
                  <div>
                    <span className="text-xs font-semibold text-text-secondary uppercase">Başarı Oranı (Win Rate)</span>
                    <h3 className="text-3xl font-extrabold font-mono mt-1 text-bullish">{formatPercentage(stats.win_rate, 0, false)}</h3>
                    <p className="text-[10px] text-text-muted mt-1">
                      {stats.win_count} Win / {stats.loss_count} Loss / {stats.breakeven_count} BE
                    </p>
                  </div>
                  <div className="w-10 h-10 rounded-lg bg-bullish/10 border border-bullish/20 flex items-center justify-center text-bullish">
                    <CheckCircle className="w-5 h-5" />
                  </div>
                </GlassCard>

                <GlassCard className="flex justify-between items-center">
                  <div>
                    <span className="text-xs font-semibold text-text-secondary uppercase">Ort. Sinyal Getirisi</span>
                    <h3 className="text-3xl font-extrabold font-mono mt-1 text-accent-primary">{formatPercentage(stats.average_return ?? 0)}</h3>
                    <p className="text-[10px] text-text-muted mt-1">İşlem başına ortalama kâr/zarar</p>
                  </div>
                  <div className="w-10 h-10 rounded-lg bg-accent-primary/10 border border-accent-primary/20 flex items-center justify-center text-accent-primary">
                    <TrendingUp className="w-5 h-5" />
                  </div>
                </GlassCard>

                <GlassCard className="flex justify-between items-center">
                  <div>
                    <span className="text-xs font-semibold text-text-secondary uppercase">Maksimum Drawdown</span>
                    <h3 className="text-3xl font-extrabold font-mono mt-1 text-bearish">-{formatPercentage(stats.drawdown_analysis.max_drawdown, 2, false)}</h3>
                    <p className="text-[10px] text-text-muted mt-1">Geçmiş sermaye zirvesinden düşüş</p>
                  </div>
                  <div className="w-10 h-10 rounded-lg bg-bearish/10 border border-bearish/20 flex items-center justify-center text-bearish">
                    <TrendingDown className="w-5 h-5" />
                  </div>
                </GlassCard>

                <GlassCard className="flex justify-between items-center">
                  <div>
                    <span className="text-xs font-semibold text-text-secondary uppercase">Aktif Sinyaller</span>
                    <h3 className="text-3xl font-extrabold font-mono mt-1 text-text-primary">{stats.active_count}</h3>
                    <p className="text-[10px] text-text-muted mt-1">Piyasada takip edilen aktif işlem</p>
                  </div>
                  <div className="w-10 h-10 rounded-lg bg-bg-tertiary border border-border-subtle flex items-center justify-center text-accent-ui">
                    <Briefcase className="w-5 h-5" />
                  </div>
                </GlassCard>
              </div>

              {/* Equity Curve Graph */}
              <GlassCard className="p-5">
                <h3 className="text-base font-bold text-text-primary mb-4 flex items-center">
                  <TrendingUp className="w-5 h-5 text-accent-primary mr-2" />
                  Kümülatif Getiri Eğrisi (Equity Curve)
                </h3>
                <div className="h-72 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={stats.historical_equity_curve} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                      <defs>
                        <linearGradient id="colorCapital" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor={chartColors.accent} stopOpacity={0.4} />
                          <stop offset="95%" stopColor={chartColors.accent} stopOpacity={0.0} />
                        </linearGradient>
                      </defs>
                      <XAxis dataKey="time" stroke={chartColors.axis} fontSize={10} tickLine={false} />
                      <YAxis stroke={chartColors.axis} fontSize={10} domain={['dataMin - 500', 'dataMax + 500']} tickLine={false} />
                      <Tooltip
                        contentStyle={{ backgroundColor: 'var(--e3)', borderColor: 'var(--hl10)', borderRadius: '8px' }}
                        labelStyle={{ color: 'var(--tx2)' }}
                        itemStyle={{ color: 'var(--tx)', fontWeight: 'bold' }}
                      />
                      <Area type="monotone" dataKey="capital" stroke={chartColors.accent} strokeWidth={2} fillOpacity={1} fill="url(#colorCapital)" />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </GlassCard>

              {/* Breakdowns section */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Win rate by strategy */}
                <GlassCard className="p-5">
                  <h3 className="text-base font-bold text-text-primary mb-4">Strateji Sinyal Tipi Performansı</h3>
                  <div className="space-y-4">
                    {Object.entries(stats.performance_by_signal_type).map(([key, value]: any) => (
                      <div key={key} className="space-y-2">
                        <div className="flex justify-between items-center">
                          <span className="text-xs font-semibold uppercase text-text-secondary">{key.replace('_', ' ')}</span>
                          <span className="text-xs font-bold font-mono text-text-primary">
                            {formatPercentage(value.win_rate, 0, false)} Win Rate | {value.total} İşlem
                          </span>
                        </div>
                        <div className="w-full h-2 rounded-full bg-bg-tertiary overflow-hidden">
                          <div
                            className="h-full rounded-full bg-accent-primary"
                            style={{ width: `${value.win_rate}%` }}
                          />
                        </div>
                        <p className="text-[10px] text-text-muted">
                          Ortalama Kâr: <span className="text-bullish font-bold">{formatPercentage(value.average_return)}</span>
                        </p>
                      </div>
                    ))}
                  </div>
                </GlassCard>

                {/* Target Hit Rates & Sentiment */}
                <GlassCard className="p-5 flex flex-col justify-between">
                  <div>
                    <h3 className="text-base font-bold text-text-primary mb-4">Hedef Gerçekleşme Oranları</h3>
                    <div className="grid grid-cols-3 gap-4 text-center mt-2">
                      <div className="p-4 bg-bg-secondary/40 border border-border-subtle rounded-xl flex flex-col items-center">
                        <span className="text-[10px] font-bold text-text-muted uppercase">Hedef 1 (TP1)</span>
                        <div className="mt-2 text-2xl font-extrabold font-mono text-bullish">{formatPercentage(stats.tp1_hit_rate, 0, false)}</div>
                      </div>
                      <div className="p-4 bg-bg-secondary/40 border border-border-subtle rounded-xl flex flex-col items-center">
                        <span className="text-[10px] font-bold text-text-muted uppercase">Hedef 2 (TP2)</span>
                        <div className="mt-2 text-2xl font-extrabold font-mono text-bullish">{formatPercentage(stats.tp2_hit_rate, 0, false)}</div>
                      </div>
                      <div className="p-4 bg-bg-secondary/40 border border-border-subtle rounded-xl flex flex-col items-center">
                        <span className="text-[10px] font-bold text-text-muted uppercase">Hedef 3 (TP3)</span>
                        <div className="mt-2 text-2xl font-extrabold font-mono text-bullish">{formatPercentage(stats.tp3_hit_rate, 0, false)}</div>
                      </div>
                    </div>
                  </div>

                  <div className="border-t border-border-subtle pt-4 mt-4">
                    <h4 className="text-xs font-bold text-text-secondary uppercase mb-3">Yön Bazlı Başarı</h4>
                    <div className="flex justify-between items-center text-sm font-semibold text-text-primary">
                      <div className="flex items-center">
                        <div className="w-2.5 h-2.5 rounded-full bg-bullish mr-2" />
                        <span>Bullish (Long): {formatPercentage(stats.win_rate_by_direction.bullish, 0, false)}</span>
                      </div>
                      <div className="flex items-center">
                        <div className="w-2.5 h-2.5 rounded-full bg-bearish mr-2" />
                        <span>Bearish (Short): {formatPercentage(stats.win_rate_by_direction.bearish, 0, false)}</span>
                      </div>
                    </div>
                  </div>
                </GlassCard>
              </div>

              {/* Asset Specific Stats */}
              <GlassCard className="p-5">
                <h3 className="text-base font-bold text-text-primary mb-4">Varlık Bazlı Başarı Oranları</h3>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                  {Object.entries(stats.win_rate_by_asset).map(([key, val]: any) => (
                    <div key={key} className="p-4 bg-bg-secondary/50 border border-border-subtle rounded-xl text-center">
                      <h4 className="text-xs font-bold text-text-primary">{key}</h4>
                      <div className="text-lg font-extrabold font-mono mt-1 text-bullish">{formatPercentage(val, 0, false)}</div>
                      <span className="text-[9px] text-text-muted">Win Rate</span>
                    </div>
                  ))}
                </div>
              </GlassCard>
            </div>
          )}
        </>
      ) : (
        /* Backtesting Tab View */
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Form parameters */}
          <GlassCard className="p-5 lg:col-span-1 h-fit">
            <h3 className="text-base font-bold text-text-primary mb-4">Backtest Ayarları</h3>
            <form onSubmit={handleRunBacktest} className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-text-secondary uppercase">Hisse / Kripto Kodu</label>
                <input
                  type="text"
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                  className="w-full bg-bg-secondary border border-border-medium rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent-primary"
                  placeholder="BTCUSDT, THYAO.IS"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-text-secondary uppercase">Zaman Dilimi</label>
                  <select
                    value={timeframe}
                    onChange={(e) => setTimeframe(e.target.value)}
                    className="w-full bg-bg-secondary border border-border-medium rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent-primary"
                  >
                    <option value="15m">15m</option>
                    <option value="1h">1h</option>
                    <option value="4h">4h</option>
                    <option value="1d">1d</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-semibold text-text-secondary uppercase">Başlangıç Bakiye</label>
                  <input
                    type="number"
                    value={initialCapital}
                    onChange={(e) => setInitialCapital(e.target.value)}
                    className="w-full bg-bg-secondary border border-border-medium rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none"
                    placeholder="10000"
                    required
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-text-secondary uppercase">Risk Oranı (%)</label>
                  <input
                    type="number"
                    step="0.1"
                    value={riskPct}
                    onChange={(e) => setRiskPct(e.target.value)}
                    className="w-full bg-bg-secondary border border-border-medium rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none"
                    required
                  />
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-semibold text-text-secondary uppercase">Maksimum Yaş</label>
                  <input
                    type="number"
                    value={maxAge}
                    onChange={(e) => setMaxAge(e.target.value)}
                    className="w-full bg-bg-secondary border border-border-medium rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none"
                    required
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-text-secondary uppercase">Emir Eşleşme Modeli</label>
                <select
                  value={executionModel}
                  onChange={(e) => setExecutionModel(e.target.value)}
                  className="w-full bg-bg-secondary border border-border-medium rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent-primary"
                >
                  <option value="conservative">Conservative (SL öncelikli)</option>
                  <option value="neutral">Neutral (Dengeli)</option>
                  <option value="optimistic">Optimistic (TP öncelikli)</option>
                </select>
              </div>

              <Button
                type="submit"
                variant="primary"
                className="w-full flex items-center justify-center space-x-2 py-2.5 font-bold"
                disabled={runningBacktest}
              >
                {runningBacktest ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    <span>Backtest Koşuluyor...</span>
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4" />
                    <span>Backtest'i Başlat</span>
                  </>
                )}
              </Button>
            </form>
            {backtestError && (
              <p className="text-xs font-semibold text-bearish bg-bearish/10 border border-bearish/20 p-3 rounded-lg mt-4">
                {backtestError}
              </p>
            )}
          </GlassCard>

          {/* Results section */}
          <div className="lg:col-span-2 space-y-6">
            {!backtestResult ? (
              <div className="flex flex-col items-center justify-center p-20 border border-dashed border-border-medium rounded-2xl text-center text-text-muted">
                <Play className="w-12 h-12 text-border-medium mb-3" />
                <h4 className="text-sm font-bold text-text-secondary">Simülasyon Bekleniyor</h4>
                <p className="text-xs text-text-muted max-w-[280px] mt-1">
                  Hisse veya coin belirterek walk-forward geçmiş simülasyonu başlatın.
                </p>
              </div>
            ) : (
              <div className="space-y-6">
                {/* Backtest stats grid */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <GlassCard className="text-center p-4">
                    <span className="text-[10px] font-bold text-text-muted uppercase">Toplam İşlem</span>
                    <div className="text-2xl font-extrabold font-mono mt-1 text-text-primary">{backtestResult.total_trades}</div>
                    <span className="text-[9px] text-text-muted">{backtestResult.wins} Win | {backtestResult.losses} Loss</span>
                  </GlassCard>

                  <GlassCard className="text-center p-4">
                    <span className="text-[10px] font-bold text-text-muted uppercase font-semibold">Kazanma Oranı</span>
                    <div className="text-2xl font-extrabold font-mono mt-1 text-bullish">{formatPercentage(backtestResult.win_rate, 0, false)}</div>
                  </GlassCard>

                  <GlassCard className="text-center p-4">
                    <span className="text-[10px] font-bold text-text-muted uppercase">Kâr Faktörü</span>
                    <div className="text-2xl font-extrabold font-mono mt-1 text-accent-primary">{backtestResult.profit_factor}</div>
                  </GlassCard>

                  <GlassCard className="text-center p-4">
                    <span className="text-[10px] font-bold text-text-muted uppercase">Max Drawdown</span>
                    <div className="text-2xl font-extrabold font-mono mt-1 text-bearish">-{formatPercentage(backtestResult.max_drawdown_pct, 2, false)}</div>
                  </GlassCard>
                </div>

                {/* Sharpe & Sortino ratios details */}
                <div className="grid grid-cols-2 gap-4">
                  <GlassCard className="p-4 flex justify-between items-center">
                    <div>
                      <span className="text-[10px] font-bold text-text-muted uppercase">Sharpe Oranı</span>
                      <h4 className="text-xl font-bold font-mono text-text-primary mt-1">{backtestResult.sharpe_ratio}</h4>
                    </div>
                  </GlassCard>

                  <GlassCard className="p-4 flex justify-between items-center">
                    <div>
                      <span className="text-[10px] font-bold text-text-muted uppercase">Sortino Oranı</span>
                      <h4 className="text-xl font-bold font-mono text-text-primary mt-1">{backtestResult.sortino_ratio ?? '—'}</h4>
                    </div>
                    <div className="text-xs font-semibold text-bullish bg-bullish/10 px-2.5 py-1 rounded-lg">
                      Düşük Risk
                    </div>
                  </GlassCard>
                </div>

                {/* Backtest Equity curve */}
                <GlassCard className="p-5">
                  <h3 className="text-base font-bold text-text-primary mb-4">Backtest Sermaye Gelişimi</h3>
                  <div className="h-60 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={backtestResult.equity_curve} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                        <defs>
                          <linearGradient id="colorBacktest" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor={chartColors.accentSecondary} stopOpacity={0.4} />
                            <stop offset="95%" stopColor={chartColors.accentSecondary} stopOpacity={0.0} />
                          </linearGradient>
                        </defs>
                        <XAxis dataKey="time" stroke={chartColors.axis} fontSize={10} tickLine={false} />
                        <YAxis stroke={chartColors.axis} fontSize={10} tickLine={false} />
                        <Tooltip
                          contentStyle={{ backgroundColor: 'var(--e3)', borderColor: 'var(--hl10)', borderRadius: '8px' }}
                          labelStyle={{ color: 'var(--tx2)' }}
                          itemStyle={{ color: 'var(--tx)', fontWeight: 'bold' }}
                        />
                        <Area type="monotone" dataKey="capital" stroke={chartColors.accentSecondary} strokeWidth={2} fillOpacity={1} fill="url(#colorBacktest)" />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </GlassCard>

                {/* Trades log */}
                <GlassCard className="p-5">
                  <h3 className="text-base font-bold text-text-primary mb-3">İşlem Günlüğü</h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse text-xs">
                      <thead>
                        <tr className="border-b border-border-medium text-text-secondary uppercase">
                          <th className="py-2">ID</th>
                          <th className="py-2">Yön</th>
                          <th className="py-2">Giriş</th>
                          <th className="py-2">Çıkış</th>
                          <th className="py-2 text-right">Getiri</th>
                          <th className="py-2 text-right">Sonuç</th>
                        </tr>
                      </thead>
                      <tbody>
                        {backtestResult.trades_log.map((trade: any) => (
                          <tr key={trade.trade_id} className="border-b border-border-subtle last:border-none text-text-primary">
                            <td className="py-2.5 font-bold font-mono">{trade.trade_id}</td>
                            <td className="py-2.5">
                              <span className={`font-semibold ${trade.direction === 'bullish' ? 'text-bullish' : 'text-bearish'}`}>
                                {trade.direction.toUpperCase()}
                              </span>
                            </td>
                            <td className="py-2.5 font-mono">{formatPrice(trade.entry_price)}</td>
                            <td className="py-2.5 font-mono">{formatPrice(trade.exit_price)}</td>
                            <td className={`py-2.5 text-right font-bold font-mono ${trade.return_pct > 0 ? 'text-bullish' : 'text-bearish'}`}>
                              {formatPercentage(trade.return_pct)}
                            </td>
                            <td className="py-2.5 text-right">
                              <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                trade.outcome === 'win' ? 'bg-bullish/10 text-bullish' : 'bg-bearish/10 text-bearish'
                              }`}>
                                {trade.outcome.toUpperCase()}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </GlassCard>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
