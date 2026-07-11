'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  TrendingUp, Shield, BarChart3, Microscope, History, Zap, Wallet,
  ArrowRight, CheckCircle, Activity, Target, Globe, FileDown, Bell,
  Info, Layers, Eye, UserCheck, Lock,
} from 'lucide-react';
import { useAuth } from '@/lib/auth-context';
import { InvestmentDisclaimer } from '@/components/legal/InvestmentDisclaimer';
import { LIVE_STATUS_META } from '@/components/ui/LiveStatusBadge';
import {
  fetchSignalHistory, fetchPlans, fetchLandingProof,
  type ApiSignal, type Plan, type LandingProof,
} from '@/lib/api';
import { cn, formatPercentage, formatPrice } from '@/lib/utils';

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
  { n: '2', title: 'Kripto Piyasalarını Canlı İzle', desc: '9 AI motoru kripto piyasalarını 7/24 tarayıp sinyal üretir.' },
  { n: '3', title: 'Akıllı Takip Et', desc: 'Telegram\'dan anında haberdar ol, performansını Sinyal Geçmişi\'nde gör.' },
];

// CP-5b — Canlı Masa: hero'nun gerçek-veri paneli (K-D/b1: Karot'suz read-only vitrin).
// R1: bölgeler yalnız hairline ile ayrılır (kutu-içinde-kutu yok). Veri yoksa üst seviye
// paneli hiç render etmez (K1 düşüşü); yüklenirken min-h çerçeve rezervi (Rezerv-B, CLS 0).
const OUTCOME_PILL = {
  win:       { label: 'TP', cls: 'bg-bullish/15 text-bullish' },
  loss:      { label: 'SL', cls: 'bg-bearish/15 text-bearish' },
  breakeven: { label: 'BE', cls: 'bg-bg-tertiary/60 text-text-secondary' },
} as const;

function relTime(iso: string): string {
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return 'bugün';
  if (days === 1) return 'dün';
  return `${days} gün önce`;
}

function CanliMasa({ proof }: { proof: LandingProof | null }) {
  const lc = proof?.lastClosed ?? null;
  const time = proof
    ? new Date(proof.generatedAt).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })
    : null;
  return (
    <div className="glass-panel border border-border-subtle rounded-card p-4 min-h-[380px]">
      <div className="flex items-center justify-between">
        <span className="text-micro font-medium uppercase tracking-wide text-text-secondary">Canlı — gerçek sinyallerden</span>
        {time && <span className="text-micro font-mono text-text-muted">{time}</span>}
      </div>

      {lc && (
        <div className="border-t border-border-subtle mt-3 pt-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-display text-text-primary">
              {lc.symbol}
              {/* twMerge özel text-micro'yu renk sınıflarıyla çakıştırıp düşürüyor → düz birleştirme */}
              <span className={'ml-2 text-micro font-medium uppercase ' + (lc.direction === 'bullish' ? 'text-bullish' : 'text-bearish')}>
                {lc.direction === 'bullish' ? 'LONG' : 'SHORT'}
              </span>
            </span>
            <span className={'text-micro font-medium uppercase px-2 py-0.5 rounded ' + OUTCOME_PILL[lc.outcome].cls}>
              {OUTCOME_PILL[lc.outcome].label}
            </span>
          </div>
          {/* R6: yüzde panelin en büyük rakamı (text-h3 = 18px, ölçek-içi).
              NOT: cn/twMerge özel text-h3'ü renk sanıp text-bullish/bearish ile çakıştırıp
              düşürüyor → düz string birleştirme (kazananlar kartıyla aynı desen). */}
          <div className={'text-h3 num font-num-560 mt-1.5 ' + (lc.returnPct >= 0 ? 'text-bullish' : 'text-bearish')}>
            {formatPercentage(lc.returnPct)}
          </div>
          <div className="text-micro font-mono text-text-muted mt-1">
            Giriş: {formatPrice(lc.entryLow)} · {relTime(lc.closedAt)}
          </div>
          <div className="text-micro text-text-muted mt-2">Son kapanan sinyal — sonuca göre seçilmedi.</div>
        </div>
      )}

      {proof && proof.teaser.length > 0 && (
        <div className="border-t border-border-subtle mt-3 divide-y divide-border-subtle">
          {proof.teaser.map((t) => (
            <div key={t.symbol} className="flex items-center gap-3 py-2 text-xs">
              <span className="flex-1 font-display text-text-primary">{t.symbol}</span>
              <span className={'text-micro font-medium uppercase ' + (t.direction === 'bullish' ? 'text-bullish' : 'text-bearish')}>
                {t.direction === 'bullish' ? 'LONG' : 'SHORT'}
              </span>
              <span className="text-text-secondary">
                {(t.liveStatus && LIVE_STATUS_META[t.liveStatus as keyof typeof LIVE_STATUS_META]?.label) || 'Aktif'}
              </span>
            </div>
          ))}
        </div>
      )}

      {proof && proof.activeTotal > 0 && (
        <div className="border-t border-border-subtle mt-3 pt-3">
          <Link href="/register" className="text-xs font-display text-accent-primary hover:text-accent-ui transition-colors">
            {proof.activeTotal} aktif sinyalin tamamı ürün içinde →
          </Link>
        </div>
      )}
    </div>
  );
}

export default function LandingPage() {
  const router = useRouter();
  const { user, loading } = useAuth();

  const [proof, setProof] = useState<LandingProof | null>(null);
  const [proofLoaded, setProofLoaded] = useState(false);
  const [sicilSignals, setSicilSignals] = useState<ApiSignal[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);

  useEffect(() => {
    if (!loading && user) router.replace('/dashboard');
  }, [user, loading, router]);

  useEffect(() => {
    fetchLandingProof()
      .then(setProof)
      .catch((e) => console.error('Landing: canlı-masa verisi alınamadı', e))
      .finally(() => setProofLoaded(true));
    // CP-5c — Sicil: son kapananlar, SONUCA GÖRE FİLTRESİZ (anti-cherry-pick).
    // only_resolved expired/invalidated da dönebilir → W/L/BE'ye süzülür (yön-yansız), ilk 6.
    fetchSignalHistory({ only_resolved: true, page_size: 10 })
      .then((r) => setSicilSignals(
        r.items.filter((s) => s.outcome === 'win' || s.outcome === 'loss' || s.outcome === 'breakeven').slice(0, 6),
      ))
      .catch((e) => console.error('Landing: sicil alınamadı', e));
    fetchPlans().then((r) => setPlans(r.plans.filter((p) => p.tier !== 'free'))).catch((e) => console.error('Landing: planlar alınamadı', e));
  }, []);

  if (loading || user) {
    return <div className="min-h-screen flex items-center justify-center bg-bg-primary"><div className="w-8 h-8 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" /></div>;
  }

  // Panel yalnız gerçek veri varken yaşar; yüklenme bitip veri yoksa hero K1'e düşer (fake-data yok).
  const hasProofPanel = !!proof && (!!proof.lastClosed || proof.teaser.length > 0);
  const showPanelArea = !proofLoaded || hasProofPanel;

  return (
    <div className="min-h-screen bg-bg-primary">
      {/* Nav — sticky (CP-1a): opak --e0 zemin + alt-hairline; scroll'da erisim korunur. z-10 = --z-sticky (kanonik olcek). */}
      <header className="sticky top-0 z-10 bg-bg-primary border-b border-border-subtle">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <img src="/logo-icon-square.png" alt="TradeMinds AI" className="w-8 h-8" />
            <span className="text-base font-display gradient-text-brand">TradeMinds AI</span>
            <span className="text-micro font-medium uppercase text-accent-primary bg-accent-primary/12 border border-accent-primary/30 px-1.5 py-0.5 rounded">BETA</span>
          </div>
          <div className="flex items-center gap-3">
            <Link href="/login" className="text-sm font-display text-text-secondary hover:text-text-primary transition-colors">Giriş Yap</Link>
            <Link href="/register" className="text-sm font-display bg-accent-primary hover:bg-accent-hover text-white px-4 py-2 rounded-xl transition-colors">
              Ücretsiz Başla
            </Link>
          </div>
        </div>
      </header>

      {/* Hero — CP-5b: 55/45 "Canlı Masa" (K-D/b1 + R1-R6). Rezerv-A: section relative =
          atmosfer host (CP-6 ışık katmanı buraya girer; arka-plan çocuklara gömülmez).
          Eski %-şerit + istatistik kutusu kaldırıldı (K-B2+ bandı CP-2'de hero-dışı gelir). */}
      <section className="relative max-w-6xl mx-auto px-6 pt-24 pb-12">
        <div className={cn(showPanelArea && 'md:grid md:grid-cols-[11fr_9fr] md:gap-12 lg:gap-16')}>
          {/* Sol kolon — R3: max-w sınırı; öğeler ayrık sibling (Rezerv-C: gelecek reveal hedefleri) */}
          <div className="max-w-[32rem]">
            <p className="text-micro font-medium uppercase tracking-wide text-text-secondary">
              KRİPTO SİNYAL İSTİHBARATI — BETA
            </p>
            <h1
              className="font-display text-text-primary mt-4"
              style={{ fontSize: 'clamp(32px, calc(3.5vw + 12px), 48px)', letterSpacing: '-0.03em', lineHeight: 1.04, fontWeight: 650 }}
            >{/* imza H1 (K-A kilit) + landing display band (K-H) — CP-1b'den birebir */}
              9 motor.<br />
              Tek yargı.<br />
              Gizli değil.
            </h1>
            <p className="text-base md:text-lg text-text-secondary mt-5">
              9 bağımsız AI motoru kripto piyasalarını 7/24 analiz eder. Her sinyal gerekçesi ve gerçek
              sonucu ile kayda geçer. Kazananları da kaybedenleri de aynı sicilde görürsün.
            </p>
            <p className="text-sm text-text-secondary mt-4">
              TradeMinds bir yatırım danışmanı değildir; analiz aracıdır. Karar ve risk sana aittir.
            </p>
            {/* R5: ikincil CTA çerçevesiz metin-link — sol kolonda tek kutu (squint: H1 + tek CTA).
                Mobilde dikey istif (CTA sarma-fix). CP-5c: ikincil CTA kanıta davet eder (#sicil). */}
            <div className="flex flex-col sm:flex-row sm:items-center gap-3 mt-7">
              <Link href="/register" className="inline-flex items-center justify-center gap-2 text-sm font-display bg-accent-primary hover:bg-accent-hover text-white px-6 py-3 rounded-xl transition-all hover:shadow-cta">
                Ücretsiz Başla <ArrowRight className="w-4 h-4" />
              </Link>
              <Link href="#sicil" className="inline-flex items-center gap-1.5 text-sm font-display text-text-secondary hover:text-text-primary transition-colors">
                Gerçek Sicili Gör <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
          </div>

          {/* Sağ panel — R2: 32px dikey ofset (diagonal gerilim). Yüklenirken çerçeve
              rezervi durur (CLS 0); yükleme bitip veri yoksa alan tamamen kalkar (K1). */}
          {showPanelArea && (
            <div className="mt-10 md:mt-8">
              <CanliMasa proof={proof} />
            </div>
          )}
        </div>
      </section>

      {/* Kanıt Bandı — CP-2 (K-B2+): HAM DAĞILIM + TP1, tek dipnot. Hairline üst+alt,
          kutu YOK; TAMAMEN NÖTR renk (kilitli karar: dağılıma başarı/başarısızlık hissi
          verecek yeşil-kırmızı sunum yok). Oran/ortalama-getiri metrikleri landing'e dönmez (K-B2+).
          Yüklenirken alan rezervi (CLS 0); veri yoksa bant render edilmez. */}
      {(!proofLoaded || proof?.stats) && (
        <section className="max-w-6xl mx-auto px-6 pb-4">
          {proof?.stats ? (
            <div className="border-y border-border-subtle py-5">
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-2">
                <span className="text-h3 num font-num-560 text-text-primary">{proof.stats.closedTotal.toLocaleString('tr-TR')}</span>
                <span className="text-sm font-display text-text-secondary">kapanmış sinyal¹</span>
                <span className="text-sm text-text-muted px-1" aria-hidden="true">·</span>
                <span className="text-base num font-num-560 text-text-primary">{proof.stats.winCount.toLocaleString('tr-TR')}</span>
                <span className="text-sm font-display text-text-secondary">kazanç</span>
                <span className="text-sm text-text-muted px-1" aria-hidden="true">·</span>
                <span className="text-base num font-num-560 text-text-primary">{proof.stats.lossCount.toLocaleString('tr-TR')}</span>
                <span className="text-sm font-display text-text-secondary">kayıp</span>
                <span className="text-sm text-text-muted px-1" aria-hidden="true">·</span>
                <span className="text-base num font-num-560 text-text-primary">{proof.stats.breakevenCount.toLocaleString('tr-TR')}</span>
                <span className="text-sm font-display text-text-secondary">başabaş</span>
                {proof.stats.tp1Rate != null && (
                  <>
                    <span className="text-sm text-text-muted px-1" aria-hidden="true">·</span>
                    <span className="text-sm font-display text-text-secondary">TP1'e ulaşma</span>
                    <span className="text-base num font-num-560 text-text-primary">{formatPercentage(proof.stats.tp1Rate, 0, false)}¹</span>
                  </>
                )}
              </div>
              <p className="text-micro text-text-secondary mt-3">
                ¹ Tüm zamanlar · {proof.stats.closedTotal.toLocaleString('tr-TR')} kapanmış sinyal · sonuca göre
                filtrelenmedi · geçmiş performans gelecek sonuçların göstergesi değildir.
              </p>
            </div>
          ) : (
            <div className="min-h-[64px]" />
          )}
        </section>
      )}

      {/* Sicil — CP-5c: son kapanan sinyaller, SONUCA GÖRE FİLTRESİZ (anti-cherry-pick,
          kilitli karar). Kazanan da kaybeden de aynı sicilde; "yalnız-kazanan" bölümü emekli. */}
      {sicilSignals.length > 0 && (
        <section id="sicil" className="max-w-6xl mx-auto px-6 py-12 scroll-mt-16">
          <h2 className="text-h2 font-display text-text-primary text-center">Sicil: Son Kapanan Sinyaller</h2>
          <p className="text-sm text-text-secondary text-center mt-2 max-w-xl mx-auto">
            Sonuca göre filtrelenmedi — kazanan da kaybeden de burada.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mt-8">
            {sicilSignals.map((s) => (
              <div key={s.id} className="glass-panel border border-border-subtle rounded-card p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-display text-text-primary">
                    {s.asset?.symbol}
                    <span className={'ml-2 text-micro font-medium uppercase ' + (s.direction === 'bullish' ? 'text-bullish' : 'text-bearish')}>
                      {s.direction === 'bullish' ? 'LONG' : 'SHORT'}
                    </span>
                  </span>
                  {s.outcome && s.outcome in OUTCOME_PILL && (
                    <span className={'text-micro font-medium uppercase px-2 py-0.5 rounded ' + OUTCOME_PILL[s.outcome as keyof typeof OUTCOME_PILL].cls}>
                      {OUTCOME_PILL[s.outcome as keyof typeof OUTCOME_PILL].label}
                    </span>
                  )}
                </div>
                <div className={'text-h2 num font-num-560 ' + ((s.actual_return ?? 0) >= 0 ? 'text-bullish' : 'text-bearish')}>
                  {formatPercentage(s.actual_return ?? 0)}
                </div>
                <div className="text-micro text-text-muted mt-1.5 font-mono">
                  Giriş: {formatPrice(s.entry_zone_low)} → TP: {formatPrice(s.tp1)}{s.closed_at ? ' · ' + relTime(s.closed_at) : ''}
                </div>
                <div className="text-micro text-text-muted uppercase mt-1">{s.timeframe} · {s.signal_type.replace('_', ' ')}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Engines */}
      <section className="max-w-6xl mx-auto px-6 py-16">
        <h2 className="text-h2 font-display text-text-primary text-center">İhtiyacın Olan Her Şey, Tek Platformda</h2>
        <p className="text-sm text-text-secondary text-center mt-2 max-w-xl mx-auto">
          9 bağımsız AI motoru birlikte çalışıp profesyonel düzeyde bir trading kokpiti sunar.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-10">
          {ENGINES.map((e) => (
            <div key={e.title} className="glass-panel border border-border-subtle rounded-card p-5">
              <div className="w-10 h-10 rounded-xl bg-accent-primary/10 flex items-center justify-center mb-3">
                <e.icon className="w-5 h-5 text-accent-primary" />
              </div>
              <h3 className="text-sm font-display text-text-primary">{e.title}</h3>
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
            <div key={f.label} className="flex items-center gap-2 text-sm font-display text-text-secondary">
              <CheckCircle className="w-4 h-4 text-bullish flex-shrink-0" /> {f.label}
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section className="max-w-4xl mx-auto px-6 py-16">
        <h2 className="text-h2 font-display text-text-primary text-center">Dakikalar İçinde Başla</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-10">
          {STEPS.map((s) => (
            <div key={s.n} className="text-center">
              <div className="w-12 h-12 rounded-xl gradient-bg-brand flex items-center justify-center text-white font-display text-lg mx-auto mb-3">
                {s.n}
              </div>
              <h3 className="text-sm font-display text-text-primary">{s.title}</h3>
              <p className="text-xs text-text-secondary mt-1.5">{s.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Transparency: how it works + honest limits + key messages (all verifiable) */}
      <section className="max-w-6xl mx-auto px-6 py-16 border-t border-border-subtle">
        <h2 className="text-h2 font-display text-text-primary text-center">Şeffaflık: Nasıl Çalışır, Neyi Vaat Etmez</h2>
        <p className="text-sm text-text-secondary text-center mt-2 max-w-2xl mx-auto">
          Güçlü bir karar destek aracı sunuyoruz — sihirli bir kutu değil. Sistemin nasıl çalıştığını da, sınırlarını da açıkça paylaşıyoruz.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mt-10">
          {/* How it works — honest mechanics */}
          <div className="glass-panel border border-border-subtle rounded-card p-6">
            <div className="flex items-center gap-2 mb-4">
              <Layers className="w-5 h-5 text-accent-primary" />
              <h3 className="text-sm font-display text-text-primary">Nasıl çalışır</h3>
            </div>
            <ul className="space-y-3 text-xs text-text-secondary leading-relaxed">
              <li className="flex gap-2"><CheckCircle className="w-4 h-4 text-accent-primary flex-shrink-0 mt-0.5" /> 9 bağımsız AI motoru her sinyali ayrı puanlar; sonuçlar birleşik bir güven skorunda toplanır.</li>
              <li className="flex gap-2"><CheckCircle className="w-4 h-4 text-accent-primary flex-shrink-0 mt-0.5" /> Piyasa rejimi (trend/range/volatilite) tespit edilir; ağırlıklar coin bazında geçmiş performansa göre uyarlanır.</li>
              <li className="flex gap-2"><CheckCircle className="w-4 h-4 text-accent-primary flex-shrink-0 mt-0.5" /> Her sinyal canlı izlenir; başarı metrikleri yalnızca gerçek, kapanmış sinyallerden hesaplanır.</li>
            </ul>
          </div>

          {/* Honest limits — clear but not scary */}
          <div className="glass-panel border border-border-subtle rounded-card p-6">
            <div className="flex items-center gap-2 mb-4">
              <Eye className="w-5 h-5 text-text-secondary" />
              <h3 className="text-sm font-display text-text-primary">Dürüst sınırlar</h3>
            </div>
            <ul className="space-y-3 text-xs text-text-secondary leading-relaxed">
              <li className="flex gap-2"><Info className="w-4 h-4 text-text-muted flex-shrink-0 mt-0.5" /> AI çıktıları yanlış veya eksik olabilir; tek başına değil, kendi araştırmanla birlikte değerlendirilmelidir.</li>
              <li className="flex gap-2"><Info className="w-4 h-4 text-text-muted flex-shrink-0 mt-0.5" /> Veriler üçüncü taraf sağlayıcılardan gelir (Binance, CoinGecko); gecikme veya hata olabilir.</li>
              <li className="flex gap-2"><Info className="w-4 h-4 text-text-muted flex-shrink-0 mt-0.5" /> Geçmiş performans geleceği garanti etmez; kesintisiz veya hatasız hizmet garantisi verilmez.</li>
            </ul>
          </div>
        </div>

        {/* 3 key messages — prominent, professional */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6">
          {[
            { icon: Info, title: 'Yatırım tavsiyesi değildir', desc: 'Tüm analizler bilgilendirme amaçlıdır; bireysel yatırım tavsiyesi sunmaz.' },
            { icon: UserCheck, title: 'Nihai karar senindir', desc: 'Uygunluk analizi yapılmaz; kararı kendi bilgin ve risk profiline göre verirsin.' },
            { icon: Lock, title: 'Senin adına işlem yapmaz', desc: 'TradeMinds yalnızca analiz ve karar desteği sunar; hesabında emir göndermez.' },
          ].map((m) => (
            <div key={m.title} className="rounded-card border border-border-subtle bg-bg-secondary/40 p-5">
              <div className="w-9 h-9 rounded-xl bg-accent-primary/10 flex items-center justify-center mb-3">
                <m.icon className="w-5 h-5 text-accent-primary" />
              </div>
              <h3 className="text-sm font-display text-text-primary">{m.title}</h3>
              <p className="text-xs text-text-secondary mt-1.5 leading-relaxed">{m.desc}</p>
            </div>
          ))}
        </div>

        <div className="max-w-3xl mx-auto mt-8">
          <InvestmentDisclaimer variant="inline" />
        </div>
      </section>

      {/* Security & data transparency — every claim is verifiable / implemented */}
      <section className="max-w-6xl mx-auto px-6 py-16 border-t border-border-subtle">
        <h2 className="text-h2 font-display text-text-primary text-center">Güvenlik ve Veri Şeffaflığı</h2>
        <p className="text-sm text-text-secondary text-center mt-2 max-w-2xl mx-auto">
          Verinin nereden geldiğini, nasıl korunduğunu ve gizliliği nasıl ele aldığımızı açıkça paylaşıyoruz.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mt-10">
          {/* Data sources */}
          <div className="glass-panel border border-border-subtle rounded-card p-6">
            <div className="w-10 h-10 rounded-xl bg-accent-primary/10 flex items-center justify-center mb-3"><Globe className="w-5 h-5 text-accent-primary" /></div>
            <h3 className="text-sm font-display text-text-primary">Gerçek veri kaynakları</h3>
            <p className="text-xs text-text-secondary mt-1.5 leading-relaxed">Fiyat ve piyasa verileri tanınmış sağlayıcılardan gelir:</p>
            <ul className="mt-3 space-y-1.5 text-xs text-text-secondary">
              <li className="flex gap-2"><CheckCircle className="w-3.5 h-3.5 text-bullish flex-shrink-0 mt-0.5" /> Binance — kripto fiyat/mum verisi</li>
              <li className="flex gap-2"><CheckCircle className="w-3.5 h-3.5 text-bullish flex-shrink-0 mt-0.5" /> CoinGecko — piyasa metadata & Fear/Greed</li>
            </ul>
          </div>
          {/* Security */}
          <div className="glass-panel border border-border-subtle rounded-card p-6">
            <div className="w-10 h-10 rounded-xl bg-accent-primary/10 flex items-center justify-center mb-3"><Shield className="w-5 h-5 text-accent-primary" /></div>
            <h3 className="text-sm font-display text-text-primary">Güvenlik yaklaşımı</h3>
            <ul className="mt-3 space-y-1.5 text-xs text-text-secondary">
              <li className="flex gap-2"><CheckCircle className="w-3.5 h-3.5 text-bullish flex-shrink-0 mt-0.5" /> Tüm trafik HTTPS/TLS ile şifrelenir</li>
              <li className="flex gap-2"><CheckCircle className="w-3.5 h-3.5 text-bullish flex-shrink-0 mt-0.5" /> Modern güvenlik başlıkları (CSP, HSTS) etkin</li>
              <li className="flex gap-2"><CheckCircle className="w-3.5 h-3.5 text-bullish flex-shrink-0 mt-0.5" /> Kötüye kullanıma karşı hız sınırlama (rate limiting)</li>
              <li className="flex gap-2"><CheckCircle className="w-3.5 h-3.5 text-bullish flex-shrink-0 mt-0.5" /> Şifreler güçlü algoritmayla saklanır; düz metin tutulmaz</li>
            </ul>
          </div>
          {/* Privacy / KVKK */}
          <div className="glass-panel border border-border-subtle rounded-card p-6">
            <div className="w-10 h-10 rounded-xl bg-accent-primary/10 flex items-center justify-center mb-3"><Lock className="w-5 h-5 text-accent-primary" /></div>
            <h3 className="text-sm font-display text-text-primary">Gizlilik &amp; KVKK</h3>
            <ul className="mt-3 space-y-1.5 text-xs text-text-secondary">
              <li className="flex gap-2"><CheckCircle className="w-3.5 h-3.5 text-bullish flex-shrink-0 mt-0.5" /> KVKK uyumlu çerez yönetimi; analitik çerezler varsayılan kapalı</li>
              <li className="flex gap-2"><CheckCircle className="w-3.5 h-3.5 text-bullish flex-shrink-0 mt-0.5" /> Onaylar kayıt altına alınır; tercihini istediğin an değiştirebilirsin</li>
              <li className="flex gap-2"><CheckCircle className="w-3.5 h-3.5 text-bullish flex-shrink-0 mt-0.5" /> Verilerin yalnızca hizmeti sunmak için işlenir</li>
            </ul>
            <Link href="/yasal" className="inline-block mt-3 text-xs font-display text-accent-primary hover:underline">Yasal belgeleri incele →</Link>
          </div>
        </div>
      </section>

      {/* Pricing teaser */}
      {plans.length > 0 && (
        <section className="max-w-6xl mx-auto px-6 py-16">
          <h2 className="text-h2 font-display text-text-primary text-center">Basit, Şeffaf Fiyatlandırma</h2>
          <p className="text-sm text-text-secondary text-center mt-2">Şeffaf fiyatlandırma, gizli ücret yok — dilediğin an yükselt veya iptal et.</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mt-10 max-w-3xl mx-auto">
            {plans.map((p) => {
              const monthly = p.pricing.find((pr) => pr.cycle === 'monthly');
              return (
                <div key={p.tier} className={cn('glass-panel border rounded-card p-6', p.recommended ? 'border-accent-primary/40' : 'border-border-subtle')}>
                  <h3 className="text-base font-display text-text-primary">{p.name}</h3>
                  <p className="text-xs text-text-secondary mt-1">{p.description}</p>
                  <div className="text-h1 num font-num-560 text-text-primary mt-3">
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
            <Link href="/pricing" className="text-sm font-display text-accent-primary hover:text-accent-ui">
              Tüm planları ve süre seçeneklerini gör →
            </Link>
          </div>
        </section>
      )}

      {/* Final CTA */}
      <section className="max-w-4xl mx-auto px-6 py-20 text-center">
        <h2 className="text-h2 md:text-h1 font-display text-text-primary">Trading Avantajını Bugün İnşa Et</h2>
        <p className="text-sm text-text-secondary mt-3">Kayıt sonrası dashboard'a anında erişim — kredi kartı gerekmez.</p>
        <Link href="/register" className="inline-flex items-center gap-2 text-sm font-display bg-accent-primary hover:bg-accent-hover text-white px-7 py-3.5 rounded-xl transition-all hover:shadow-cta mt-6">
          Ücretsiz Hesap Oluştur <ArrowRight className="w-4 h-4" />
        </Link>
      </section>

      {/* Footer is provided globally by LayoutShell (<Footer />): single-source
          investment disclaimer + legal links + cookie settings. No page-local
          footer here, to avoid a duplicate footer for logged-out visitors. */}
    </div>
  );
}
