'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import {
  HelpCircle, ChevronDown, Mail, Github, MessageCircle,
  Zap, Shield, BarChart3, Lock, Brain, FileDown,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { cn } from '@/lib/utils';
import {
  SUPPORT_EMAIL, SUPPORT_TELEGRAM, KUNYE_PATH,
  hasSupportEmail, hasSupportTelegram, hasAnySupportChannel, telegramUrl,
} from '@/lib/contact';

interface FaqItem {
  q: string;
  a: React.ReactNode;
  icon: React.ComponentType<{ className?: string }>;
}

const FAQS: FaqItem[] = [
  {
    icon: Zap,
    q: 'TradeMinds AI sinyalleri nasıl üretiyor?',
    a: (
      <>
        9 farklı analiz motoru paralel çalışır: <b>Teknik Analiz, Market Structure, SMC, Volume,
        CRT, Risk, Fundamental, On-Chain ve Macro</b>. Her motor 0-100 arası skor üretir; AI Karar
        Motoru ağırlıklı ortalama alarak son sinyali (AL / GÜÇLÜ AL / BEKLE / SAT / GÜÇLÜ SAT) belirler.
      </>
    ),
  },
  {
    icon: BarChart3,
    q: 'Sinyaller ne sıklıkla güncelleniyor?',
    a: (
      <>
        Mum kapanışında otomatik:
        <ul className="list-disc list-inside mt-1 space-y-0.5">
          <li>15 dakikalık sinyaller → her 15 dakikada bir</li>
          <li>1 saatlik sinyaller → her saat başı</li>
          <li>4 saatlik sinyaller → her 4 saatte bir</li>
        </ul>
        Anlık fiyatlar Binance WebSocket'ten saniyelik akar.
      </>
    ),
  },
  {
    icon: Brain,
    q: 'Kalite Skoru ne anlama geliyor?',
    a: (
      <>
        Sinyalin <b>güven skoru (0–100)</b>, 10 üzerinden bir kalite barına dönüşür:
        8–10 yeşil (yüksek kalite), 6–7 sarı, 4–5 turuncu, 0–3 kırmızı.
        Trade'lerde 7+ kalite ve uygun risk seviyesi tercih edilir.
      </>
    ),
  },
  {
    icon: Lock,
    q: 'HTF Alignment, Purge Type gibi terimler nedir?',
    a: (
      <>
        <b>HTF Alignment:</b> Üst zaman dilimi (Higher Timeframe) hizalaması — Bullish OB,
        Bearish FVG gibi SMC etiketleridir.<br/>
        <b>Purge Type:</b> Likidite süpürmesi yönü — LOW (dip likidite alındı, dönüş bekleniyor)
        / HIGH (tepe likidite alındı, düşüş bekleniyor).
      </>
    ),
  },
  {
    icon: Shield,
    q: 'Free ve Pro plan arasındaki fark nedir?',
    a: (
      <>
        <b>Free:</b> Günde 3 sinyal, temel grafikler.<br/>
        <b>Pro ($25/ay):</b> Sınırsız sinyal, tüm AI motorları, TradingView grafikleri, Telegram
        bildirimleri, Strategy Lab, Sembol Analizi, PDF raporları, backtest.<br/>
        <b>Premium ($69/ay):</b> Pro + API erişimi + sınırsız backtest + öncelikli destek.
        Yıllık planlarda %50'ye varan tasarruf var.{' '}
        <Link href="/pricing" className="text-accent-primary underline">Planları gör</Link>.
      </>
    ),
  },
  {
    icon: FileDown,
    q: 'PDF rapor nasıl alınır?',
    a: (
      <>
        Sinyal Merkezi → bir sinyale tıkla → açılan panelde "PDF İndir" butonuna bas.
        Performans sayfasının sağ üstündeki "PDF" butonu ise tüm performans özetini indirir.
        Bu özellik Pro+ abonelik gerektirir.
      </>
    ),
  },
  {
    icon: HelpCircle,
    q: 'Sinyaller yatırım tavsiyesi midir?',
    a: (
      <>
        <b>Hayır.</b> TradeMinds AI yalnızca <i>analitik özet</i> üretir. Her yatırımcı kendi
        risk yönetimini ve karar sürecini sürdürmelidir. Geçmiş performans gelecek getirileri
        garanti etmez. Kaldıraçlı ürünlerde anapara kaybı riski yüksektir.
      </>
    ),
  },
];

function FaqRow({ item, open, onToggle }: { item: FaqItem; open: boolean; onToggle: () => void }) {
  const Icon = item.icon;
  return (
    <div className={cn(
      'border border-border-subtle rounded-xl overflow-hidden transition-colors',
      open ? 'bg-bg-secondary/50 border-accent-primary/30' : 'bg-bg-secondary/20'
    )}>
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-white/[0.02] transition-colors"
      >
        <Icon className={cn('w-4 h-4 flex-shrink-0', open ? 'text-accent-primary' : 'text-text-muted')} />
        <span className="flex-1 text-sm font-semibold text-text-primary">{item.q}</span>
        <ChevronDown className={cn('w-4 h-4 text-text-muted transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="px-4 pb-4 pt-1 text-xs text-text-secondary leading-relaxed border-t border-border-subtle/60">
          {item.a}
        </div>
      )}
    </div>
  );
}

export default function HelpPage() {
  const [openIdx, setOpenIdx] = useState<number | null>(0);

  return (
    <div className="space-y-6 max-w-3xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-extrabold text-text-primary flex items-center gap-2">
          <HelpCircle className="w-6 h-6 text-accent-primary" /> Yardım Merkezi
        </h1>
        <p className="text-sm text-text-secondary mt-1">
          Sık sorulan sorular, terimler ve iletişim
        </p>
      </div>

      {/* FAQ */}
      <div className="space-y-2">
        {FAQS.map((item, i) => (
          <FaqRow
            key={i}
            item={item}
            open={openIdx === i}
            onToggle={() => setOpenIdx(openIdx === i ? null : i)}
          />
        ))}
      </div>

      {/* Contact */}
      <GlassCard>
        <h2 className="text-base font-bold text-text-primary mb-3">İletişim</h2>
        <p className="text-xs text-text-secondary mb-4">
          Sorularını bize ulaştır — geri dönüş süremiz Pro/Premium kullanıcılar için 24 saat içindedir.
        </p>
        {/* A2a: contact channels come from the single source (lib/contact.ts). Until
            real company info lands (B1), no channel is set → we do NOT fabricate a
            contact; we link to the legal künye instead. */}
        <div className="space-y-2">
          {hasSupportEmail() && (
            <a
              href={`mailto:${SUPPORT_EMAIL}`}
              className="flex items-center gap-3 p-3 rounded-xl bg-bg-secondary/50 border border-border-subtle hover:border-accent-primary/40 transition-colors"
            >
              <Mail className="w-4 h-4 text-accent-primary" />
              <div>
                <p className="text-sm font-semibold text-text-primary">E-posta</p>
                <p className="text-xs text-text-muted">{SUPPORT_EMAIL}</p>
              </div>
            </a>
          )}
          {hasSupportTelegram() && (
            <a
              href={telegramUrl()}
              target="_blank" rel="noreferrer"
              className="flex items-center gap-3 p-3 rounded-xl bg-bg-secondary/50 border border-border-subtle hover:border-accent-primary/40 transition-colors"
            >
              <MessageCircle className="w-4 h-4 text-accent-primary" />
              <div>
                <p className="text-sm font-semibold text-text-primary">Telegram Destek</p>
                <p className="text-xs text-text-muted">{SUPPORT_TELEGRAM}</p>
              </div>
            </a>
          )}
          {!hasAnySupportChannel() && (
            <Link
              href={KUNYE_PATH}
              className="flex items-center gap-3 p-3 rounded-xl bg-bg-secondary/50 border border-border-subtle hover:border-accent-primary/40 transition-colors"
            >
              <Mail className="w-4 h-4 text-accent-primary" />
              <div>
                <p className="text-sm font-semibold text-text-primary">İletişim & Künye</p>
                <p className="text-xs text-text-muted">Resmi iletişim bilgilerimiz künye sayfamızda yer alır.</p>
              </div>
            </Link>
          )}
        </div>
      </GlassCard>

      {/* Disclaimer */}
      <p className="text-[11px] text-text-muted leading-relaxed border-t border-border-subtle pt-4">
        TradeMinds AI yatırım tavsiyesi sunmaz. Tüm analizler bilgilendirme amaçlıdır.
        Sermaye piyasası araçları yüksek risk içerir; yatırımcılar kendi durumlarına göre
        karar vermeli ve gerekli durumlarda profesyonel danışmanlık almalıdır.
      </p>
    </div>
  );
}
