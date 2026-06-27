'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  Brain, TrendingUp, Shield, BarChart3, Microscope, History, Zap, Wallet,
  ArrowRight, CheckCircle, Activity, Target, Globe, FileDown, Bell,
} from 'lucide-react';
import { useAuth } from '@/lib/auth-context';
import {
  fetchPerformanceSummary, fetchSignalHistory, fetchPlans,
  type PerformanceSummary, type ApiSignal, type Plan,
} from '@/lib/api';
import { cn } from '@/lib/utils';

const ENGINES = [
  { icon: Microscope, title: 'Teknik Analiz', desc: 'Klasik indikatörler + trend/momentum birleşimiyle çok katmanlı teknik puanlama.' },
  { icon: BarChart3, title: 'Piyasa Yapısı', desc: 'HTF trend, swing yapısı ve piyasa rejimi tespiti.' },
  { icon: Target, title: 'SMC (Akıllı Para)', desc: 'Order Block, Fair Value Gap ve likidite süpürmelerini otomatik tarar.' },
  { icon: Activity, title: 'CRT (Mum Aralığı)', desc: 'Candle Range Theory tabanlı giriş/çıkış bölgesi tespiti.' },
  { icon: TrendingUp, title: 'Hacim Analizi', desc: 'Hacim anomalileri ve teyit sinyalleri.' },
  { icon: Shield, title: 'Risk Yönetimi', desc: 'Her sinyal için otomatik risk skoru, R:R ve pozisyon büyüklüğü önerisi.' },
  { icon: FileDown, title: 'Temel Analiz', desc: 'Varlığa özgü temel veriler ve makro bağlam.' },
  { icon: Globe, title: 'On-Chain & Sentiment', desc: 'Fear & Greed, ağ aktivitesi ve coin metadata sinyalleri.' },
  { icon: Bell, title: 'Makro Görünüm', desc: 'FED faizi, TCMB kuru ve küresel risk ortamı.' },
];

const STEPS = [
  { n: '1', title: 'Ücretsiz Kaydol', desc: '30 saniyede hesap aç, kredi kartı gerekmez.' },
  { n: '2', title: '97 Varlığı Canlı İzle', desc: '9 AI motoru kripto ve BIST\'i 7/24 tarayıp sinyal üretir.' },
  { n: '3', title: 'Akıllı Takip Et', desc: 'Telegram\'dan anında haberdar ol, performansını Sinyal Geçmişi\'nde gör.' },
];

function StatBlock({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="text-center">
      <div className={cn('text-3xl md:text-4xl font-extrabold font-mono', accent ? 'text-bullish' : 'text-text-primary')}>{value}</div>
      <div className="text-xs text-text-muted uppercase font-semibold tracking-wide mt-1">{label}</div>
    </div>
  );
}

export default function LandingPage() {
  const router = useRouter();
  const { user, loading } = useAuth();

  const [stats, setStats] = useState<PerformanceSummary | null>(null);
  const [winSignals, setWinSignals] = useState<ApiSignal[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);

  useEffect(() => {
    if (!loading && user) router.replace('/dashboard');
  }, [user, loading, router]);

  useEffect(() => {
    fetchPerformanceSummary().then(setStats).catch((e) => console.error('Landing: performans özeti alınamadı', e));
    fetchSignalHistory({ outcome: 'win', page_size: 4 }).then((r) => setWinSignals(r.items)).catch((e) => console.error('Landing: kazanan sinyaller alınamadı', e));
    fetchPlans().then((r) => setPlans(r.plans.filter((p) => p.tier !== 'free'))).catch((e) => console.error('Landing: planlar alınamadı', e));
  }, []);

  if (loading || user) {
    return <div className="min-h-screen flex items-center justify-center bg-bg-primary"><div className="w-8 h-8 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" /></div>;
  }

  const resolved = (stats?.win_count ?? 0) + (stats?.loss_count ?? 0) + (stats?.breakeven_count ?? 0);

  return (
    <div className="min-h-screen bg-bg-primary">
      {/* Nav */}
      <header className="border-b border-border-subtle">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <img src="/logo-icon-square.png" alt="TradeMinds AI" className="w-8 h-8" />
            <span className="text-base font-bold gradient-text-brand">TradeMinds AI</span>
          </div>
          <div className="flex items-center gap-3">
            <Link href="/login" className="text-sm font-semibold text-text-secondary hover:text-text-primary transition-colors">Giriş Yap</Link>
            <Link href="/register" className="text-sm font-bold bg-accent-primary hover:bg-accent-secondary text-white px-4 py-2 rounded-xl transition-colors">
              Ücretsiz Başla
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="max-w-6xl mx-auto px-6 pt-16 pb-12 text-center">
        <h1 className="text-3xl md:text-5xl font-extrabold text-text-primary leading-tight max-w-3xl mx-auto">
          9 AI motoru kripto ve BIST'i 7/24 tarar,{' '}
          <span className="gradient-text-brand">kanıtlanmış sinyaller</span> üretir
        </h1>
        <p className="text-base md:text-lg text-text-secondary mt-5 max-w-2xl mx-auto">
          Akıllı Para (SMC), otomatik risk skorlaması ve gerçek zamanlı performans takibiyle
          duygusal kararları geride bırak — veriye dayalı işlem yap.
        </p>

        {/* Canlı kanıt (fold üstü) — gerçek veriden beslenir; veri yoksa statik güven rozetleri */}
        {stats && resolved > 0 ? (
          <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2 mt-6 text-sm">
            <span className="inline-flex items-center gap-1.5 font-semibold text-text-secondary">
              <CheckCircle className="w-4 h-4 text-bullish" />
              <span className="font-mono font-bold text-bullish">%{stats.win_rate}</span> başarı oranı
            </span>
            <span className="inline-flex items-center gap-1.5 font-semibold text-text-secondary">
              <Activity className="w-4 h-4 text-accent-primary" />
              <span className="font-mono font-bold text-text-primary">{resolved.toLocaleString('tr-TR')}</span> kapanan sinyal
            </span>
            {stats.average_return != null && (
              <span className="inline-flex items-center gap-1.5 font-semibold text-text-secondary">
                <TrendingUp className={cn('w-4 h-4', stats.average_return >= 0 ? 'text-bullish' : 'text-bearish')} />
                <span className={cn('font-mono font-bold', stats.average_return >= 0 ? 'text-bullish' : 'text-bearish')}>
                  {stats.average_return >= 0 ? '+' : ''}{stats.average_return.toFixed(2)}%
                </span> ort. getiri
              </span>
            )}
          </div>
        ) : (
          <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2 mt-6 text-sm text-text-secondary">
            <span className="inline-flex items-center gap-1.5 font-semibold"><Brain className="w-4 h-4 text-accent-primary" /> 9 AI motoru</span>
            <span className="inline-flex items-center gap-1.5 font-semibold"><Activity className="w-4 h-4 text-accent-primary" /> 7/24 tarama</span>
            <span className="inline-flex items-center gap-1.5 font-semibold"><Shield className="w-4 h-4 text-accent-primary" /> Otomatik risk yönetimi</span>
          </div>
        )}

        <div className="flex items-center justify-center gap-3 mt-7">
          <Link href="/register" className="flex items-center gap-2 text-sm font-bold bg-accent-primary hover:bg-accent-secondary text-white px-6 py-3 rounded-xl shadow-glow-sm transition-colors">
            Ücretsiz Başla <ArrowRight className="w-4 h-4" />
          </Link>
          <Link href="/pricing" className="text-sm font-bold text-text-secondary hover:text-text-primary border border-border-subtle hover:border-accent-primary/40 px-6 py-3 rounded-xl transition-colors">
            Fiyatlandırmayı Gör
          </Link>
        </div>

        {/* Live stats strip — real data, no placeholders */}
        {stats && resolved > 0 && (
          <div className="max-w-3xl mx-auto mt-14">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-6 p-6 glass-panel border border-border-subtle rounded-2xl">
              <StatBlock label="Başarı Oranı" value={`${stats.win_rate}%`} accent />
              <StatBlock label="Kapanan Sinyal" value={resolved.toLocaleString('tr-TR')} />
              <StatBlock label="Ort. Getiri" value={`${(stats.average_return ?? 0) >= 0 ? '+' : ''}${(stats.average_return ?? 0).toFixed(2)}%`} accent={(stats.average_return ?? 0) >= 0} />
              <StatBlock label="TP1 Vuruş" value={`${stats.tp1_hit_rate}%`} />
            </div>
            <p className="text-[11px] text-text-muted text-center mt-3">
              Tüm zamanlar · yalnızca gerçek, kapanmış sinyallerden hesaplanır
            </p>
          </div>
        )}
      </section>

      {/* Latest winning signals — only real, resolved WIN signals */}
      {winSignals.length > 0 && (
        <section className="max-w-6xl mx-auto px-6 py-12">
          <h2 className="text-2xl font-extrabold text-text-primary text-center">Son Kazanan Sinyaller</h2>
          <p className="text-sm text-text-secondary text-center mt-2 max-w-xl mx-auto">
            Sistemin gerçek zamanlı ürettiği ve TP'ye ulaşmış kapanmış sinyallerden bir kesit.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mt-8">
            {winSignals.map((s) => (
              <div key={s.id} className="glass-panel border border-border-subtle rounded-2xl p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-bold text-text-primary">{s.asset?.symbol}</span>
                  <span className="text-[10px] font-bold uppercase bg-bullish/15 text-bullish px-2 py-0.5 rounded">
                    {s.direction === 'bullish' ? 'LONG' : 'SHORT'}
                  </span>
                </div>
                <div className="text-2xl font-extrabold font-mono text-bullish">
                  +{(s.actual_return ?? 0).toFixed(2)}%
                </div>
                <div className="text-[11px] text-text-muted mt-1.5 font-mono">
                  Giriş: {s.entry_zone_low?.toFixed(4)} → TP: {s.tp1?.toFixed(4)}
                </div>
                <div className="text-[10px] text-text-muted uppercase mt-1">{s.timeframe} · {s.signal_type.replace('_', ' ')}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Engines */}
      <section className="max-w-6xl mx-auto px-6 py-16">
        <h2 className="text-2xl font-extrabold text-text-primary text-center">İhtiyacın Olan Her Şey, Tek Platformda</h2>
        <p className="text-sm text-text-secondary text-center mt-2 max-w-xl mx-auto">
          9 bağımsız AI motoru birlikte çalışıp profesyonel düzeyde bir trading kokpiti sunar.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-10">
          {ENGINES.map((e) => (
            <div key={e.title} className="glass-panel border border-border-subtle rounded-2xl p-5">
              <div className="w-10 h-10 rounded-xl bg-accent-primary/10 flex items-center justify-center mb-3">
                <e.icon className="w-5 h-5 text-accent-primary" />
              </div>
              <h3 className="text-sm font-bold text-text-primary">{e.title}</h3>
              <p className="text-xs text-text-secondary mt-1.5 leading-relaxed">{e.desc}</p>
            </div>
          ))}
        </div>

        {/* Beyond signals: platform tools */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
          {[
            { icon: History, label: 'Sinyal Geçmişi' },
            { icon: Microscope, label: 'Strategy Lab' },
            { icon: BarChart3, label: 'Sembol Analizi' },
            { icon: Wallet, label: 'Portföy Takibi' },
          ].map((f) => (
            <div key={f.label} className="flex items-center gap-2 text-sm font-semibold text-text-secondary">
              <CheckCircle className="w-4 h-4 text-bullish flex-shrink-0" /> {f.label}
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section className="max-w-4xl mx-auto px-6 py-16">
        <h2 className="text-2xl font-extrabold text-text-primary text-center">Dakikalar İçinde Başla</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-10">
          {STEPS.map((s) => (
            <div key={s.n} className="text-center">
              <div className="w-12 h-12 rounded-2xl gradient-bg-brand flex items-center justify-center text-white font-extrabold text-lg mx-auto mb-3">
                {s.n}
              </div>
              <h3 className="text-sm font-bold text-text-primary">{s.title}</h3>
              <p className="text-xs text-text-secondary mt-1.5">{s.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Pricing teaser */}
      {plans.length > 0 && (
        <section className="max-w-6xl mx-auto px-6 py-16">
          <h2 className="text-2xl font-extrabold text-text-primary text-center">Basit, Şeffaf Fiyatlandırma</h2>
          <p className="text-sm text-text-secondary text-center mt-2">Şeffaf fiyatlandırma, gizli ücret yok — dilediğin an yükselt veya iptal et.</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mt-10 max-w-3xl mx-auto">
            {plans.map((p) => {
              const monthly = p.pricing.find((pr) => pr.cycle === 'monthly');
              return (
                <div key={p.tier} className={cn('glass-panel border rounded-2xl p-6', p.recommended ? 'border-accent-primary/40 shadow-glow-sm' : 'border-border-subtle')}>
                  <h3 className="text-base font-bold text-text-primary">{p.name}</h3>
                  <p className="text-xs text-text-secondary mt-1">{p.description}</p>
                  <div className="text-3xl font-extrabold font-mono text-text-primary mt-3">
                    ${monthly?.amount_usd ?? 0}<span className="text-sm text-text-muted font-normal">/ay</span>
                  </div>
                  <ul className="space-y-1.5 mt-4">
                    {p.features.filter((f) => f.included).slice(0, 5).map((f) => (
                      <li key={f.label} className="flex items-center gap-2 text-xs text-text-secondary">
                        <CheckCircle className="w-3.5 h-3.5 text-bullish flex-shrink-0" /> {f.label}
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
          <div className="text-center mt-8">
            <Link href="/pricing" className="text-sm font-bold text-accent-primary hover:text-accent-secondary">
              Tüm planları ve süre seçeneklerini gör →
            </Link>
          </div>
        </section>
      )}

      {/* Final CTA */}
      <section className="max-w-4xl mx-auto px-6 py-20 text-center">
        <h2 className="text-2xl md:text-3xl font-extrabold text-text-primary">Trading Avantajını Bugün İnşa Et</h2>
        <p className="text-sm text-text-secondary mt-3">Kayıt sonrası dashboard'a anında erişim — kredi kartı gerekmez.</p>
        <Link href="/register" className="inline-flex items-center gap-2 text-sm font-bold bg-accent-primary hover:bg-accent-secondary text-white px-7 py-3.5 rounded-xl shadow-glow-sm transition-colors mt-6">
          Ücretsiz Hesap Oluştur <ArrowRight className="w-4 h-4" />
        </Link>
      </section>

      {/* Footer */}
      <footer className="border-t border-border-subtle py-10">
        <div className="max-w-6xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <img src="/logo-icon-square.png" alt="TradeMinds AI" className="w-6 h-6" />
            <span className="text-sm font-bold text-text-primary">TradeMinds AI</span>
          </div>
          <p className="text-xs text-text-muted text-center md:text-left">
            Kurumsal düzeyde sinyal istihbaratı, performans analitiği ve risk araçları — disiplinli işlem icrası için.
          </p>
          <p className="text-xs text-text-muted">© {new Date().getFullYear()} TradeMinds AI</p>
        </div>
        <p className="max-w-6xl mx-auto px-6 mt-6 pt-5 border-t border-border-subtle text-[11px] text-text-muted leading-relaxed text-center md:text-left">
          TradeMinds AI yatırım tavsiyesi sunmaz; tüm analizler bilgilendirme amaçlıdır.
          Geçmiş performans gelecekteki getiriyi garanti etmez. Yatırım kararlarını kendi risk profiline göre ver.
        </p>
      </footer>
    </div>
  );
}
