'use client';

import React, { useState, useEffect } from 'react';
import { ScoreRing } from './ScoreRing';
import { GlassCard } from './GlassCard';
import { Modal } from '@/components/ui/Modal';
import { cn, formatRelativeTime, formatAbsoluteTimeTR, formatPrice, formatNumber } from '@/lib/utils';
import { ApiSignal } from '@/lib/api';
import { track } from '@/lib/analytics';
import { AnalyticsEvent } from '@/lib/analytics-events';
import { InvestmentDisclaimer } from '@/components/legal/InvestmentDisclaimer';
import {
  Target, TrendingUp, TrendingDown, Activity, ShieldAlert,
  Info, X, Scale, FileText, BarChart3, Check,
} from 'lucide-react';
import { EngineMiniChart } from '@/components/charts/EngineMiniChart';
import { CoinIcon } from '@/components/ui/CoinIcon';
import { IntelligencePanel } from '@/components/ui/IntelligencePanel';
import { ProvenanceReceipt } from '@/components/ui/Tooltip';
import { signalToKarotConfs } from '@/lib/karot-adapter';

// Engines whose supporting_data carries real chart-able coordinates (S/R
// levels, premium/discount zones, OB/FVG boxes, pattern indices). The rest
// (risk, fundamental, on-chain, macro) are purely numeric/textual — forcing
// a chart on them would be a hollow visual, not an insight.
const CHART_ENGINES = new Set([
  'technical_analysis', 'market_structure', 'smart_money_concepts', 'candle_range_theory',
]);

// ─── i18n / label maps ──────────────────────────────────────────────────────
const ENGINE_LABELS: Record<string, string> = {
  technical_analysis:     'Teknik Analiz',
  market_structure:       'Piyasa Yapısı',
  smart_money_concepts:   'SMC (Akıllı Para)',
  candle_range_theory:    'CRT (Mum Aralığı)',
  volume_analysis:        'Hacim Analizi',
  risk_management:        'Risk Yönetimi',
  fundamental_analysis:   'Temel Analiz',
  onchain_analysis:       'On-Chain & Sentiment',
  macro_analysis:         'Makro Görünüm',
};

// ─── Helpers ─────────────────────────────────────────────────────────────────
interface EngineRow {
  name: string;
  label: string;
  score: number;
  bias: 'bullish' | 'bearish' | 'neutral';
  findings: string[];
  supportingData: any;
}

function parseEngines(enginesData: any): EngineRow[] {
  if (!enginesData) return [];
  const list: any[] = Array.isArray(enginesData) ? enginesData : Object.values(enginesData);
  return list
    .filter((e) => e && typeof e === 'object')
    .map((e) => ({
      name:     e.engine_name ?? e.name ?? '—',
      label:    ENGINE_LABELS[e.engine_name ?? ''] ?? (e.engine_name ?? '—').replace(/_/g, ' '),
      score:    Number(e.score ?? 50),
      bias:     String(e.bias ?? 'neutral').toLowerCase().includes('bull') ? 'bullish'
              : String(e.bias ?? 'neutral').toLowerCase().includes('bear') ? 'bearish'
              : 'neutral',
      findings: Array.isArray(e.key_findings) ? e.key_findings : [],
      supportingData: e.supporting_data ?? null,
    }));
}

function calculateRR(signal: ApiSignal): string {
  const entryLow = signal.entry_zone_low;
  const entryHigh = signal.entry_zone_high;
  const sl = signal.stop_loss;
  const tp = signal.tp3 || signal.tp2 || signal.tp1;
  if (!entryLow || !entryHigh || !sl || !tp) return '—';
  const entryAvg = (entryLow + entryHigh) / 2;
  const isLong = signal.direction === 'bullish' || signal.signal_type.toLowerCase().includes('buy');
  try {
    if (isLong) {
      const risk = entryAvg - sl, reward = tp - entryAvg;
      if (risk <= 0 || reward <= 0) return '—';
      return formatNumber(reward / risk);
    } else {
      const risk = sl - entryAvg, reward = entryAvg - tp;
      if (risk <= 0 || reward <= 0) return '—';
      return formatNumber(reward / risk);
    }
  } catch { return '—'; }
}

function stripMd(raw: string): string {
  return raw
    .replace(/^#+\s*/gm, '')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/\*(.+?)\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/—/g, '·')
    .trim();
}

// ─── Sub-components ─────────────────────────────────────────────────────────

type BiasLabelConfig = Record<'bullish' | 'bearish' | 'neutral', { label: string; bg: string; text: string; border: string }>;

// "AL/SAT" reads as a buy/sell call, but this rozet means "this engine
// agrees with the LONG/SHORT direction" — not "act now". LONG/SHORT
// names the actual thing being measured.
const DIRECTIONAL_LABELS: BiasLabelConfig = {
  bullish: { label: 'LONG',  bg: 'bg-bullish/10',   text: 'text-bullish',   border: 'border-bullish/30   hover:border-bullish/60' },
  bearish: { label: 'SHORT', bg: 'bg-bearish/10',   text: 'text-bearish',   border: 'border-bearish/30   hover:border-bearish/60' },
  neutral: { label: 'BEKLE', bg: 'bg-bg-tertiary',  text: 'text-text-muted',border: 'border-border-subtle hover:border-border-medium' },
};

// Risk Yönetimi motoru yön tahmin etmiyor — skoru "bu kurulum ne kadar
// güvenli" ölçüyor (yüksek skor = düşük risk). Backend bunu diğer
// motorlarla aynı AL/SAT/BEKLE şemasından geçiriyor, bu da "SAT" rozetini
// "SHORT'u destekliyorum" gibi okutup kullanıcıyı yanıltıyordu — gerçekte
// "bu işlem riskli, dikkatli ol" diyor. Ayrı bir kelime seti kullanarak bu
// karışıklığı ortadan kaldırıyoruz.
const RISK_SAFETY_LABELS: BiasLabelConfig = {
  bullish: { label: 'GÜVENLİ', bg: 'bg-bullish/10',   text: 'text-bullish',   border: 'border-bullish/30   hover:border-bullish/60' },
  bearish: { label: 'RİSKLİ',  bg: 'bg-bearish/10',   text: 'text-bearish',   border: 'border-bearish/30   hover:border-bearish/60' },
  neutral: { label: 'ORTA',    bg: 'bg-bg-tertiary',  text: 'text-text-muted',border: 'border-border-subtle hover:border-border-medium' },
};

function engineBiasLabels(engineName: string): BiasLabelConfig {
  return engineName === 'risk_management' ? RISK_SAFETY_LABELS : DIRECTIONAL_LABELS;
}

/** Engine card — horizontal compact layout, score + bias, click for full detail */
function EngineCard({ engine, onClick, compact }: {
  engine: EngineRow;
  onClick: () => void;
  compact?: boolean;
}) {
  const biasConfig = (engineBiasLabels(engine.name))[engine.bias];

  return (
    <button
      onClick={onClick}
      title={`${engine.label} — Detayları görmek için tıkla`}
      className={cn(
        'group relative bg-bg-secondary/40 rounded-card',
        'border transition-[background-color,border-color,translate] duration-[var(--dur-state)]',
        'hover:bg-bg-secondary/60 hover:-translate-y-0.5',
        biasConfig.border,
        'text-left w-full',
        compact ? 'p-3' : 'p-4'
      )}
    >
      {/* Info icon top-right (only visible on hover) */}
      {!compact && (
        <div className="absolute top-3 right-3 opacity-0 group-hover:opacity-60 transition-opacity">
          <Info className="w-3.5 h-3.5 text-text-muted" />
        </div>
      )}

      {/* Engine label + bias chip */}
      <div className={cn('flex items-center justify-between gap-1.5', compact ? 'mb-2' : 'mb-3')}>
        <span className={cn(
          'font-display text-text-primary uppercase tracking-wide leading-tight line-clamp-2 flex-1',
          compact ? 'text-micro' : 'text-micro'
        )}>
          {engine.label}
        </span>
        <span className={cn(
          'flex-shrink-0 font-display rounded',
          compact ? 'text-micro px-1.5 py-0.5' : 'text-micro px-2 py-0.5',
          biasConfig.bg, biasConfig.text
        )}>
          {biasConfig.label}
        </span>
      </div>

      {/* Score ring centered */}
      <div className="flex items-center justify-center py-1">
        <ScoreRing score={engine.score} size={compact ? 60 : 70} strokeWidth={compact ? 5 : 6} />
      </div>
    </button>
  );
}

/** Modal showing the engine's key findings */
function EngineDetailModal({ engine, symbol, timeframe, onClose }: {
  engine: EngineRow; symbol: string; timeframe: string; onClose: () => void;
}) {
  const biasColor = engine.bias === 'bullish' ? 'text-bullish'
                  : engine.bias === 'bearish' ? 'text-bearish'
                  : 'text-text-muted';
  const [showFindings, setShowFindings] = useState(false);

  // S1c3 — ad-hoc kabuk (fixed inset-0 + ham z-[60] + elle scrim + onClick/
  // stopPropagation backdrop + glass-panel kutu + window-seviyesi ESC dinleyicisi)
  // kanonik <Modal>'a devredildi: portal, role=dialog + aria-modal + ariaLabel,
  // panel-kapsamlı focus-trap ve odak-iadesi, drag-safe backdrop, gövde
  // scroll-kilidi, E3 materyal (S1a) tek-kaynaktan gelir.
  // z-[60] KALDIRILDI → varsayılan z-modal (50). Kanon: toast (60) > modal (50);
  // eski değer modal'ı toast seviyesine çıkarıp bu sırayı bozuyordu. Mobilde
  // drawer'ın (inline z-50) ÜSTÜNDE kalması portal'ın body'ye sonradan eklenmesi
  // (DOM sırası) ile sağlanır — yeni z-token gerekmez.
  // ESC artık yalnız panel kapsamında (Modal'ın onKeyDown'ı): yığın modallarda
  // yalnız odaklı panel kapanır, drawer açık kalır (global dinleyici bunu bozardı).
  // padded={false}: iki-satırlı başlık (eyebrow + motor adı) ve mevcut ✕ AYNEN
  // korunur; bu modda Modal kendi şeridini/✕'ini render etmez → çift ✕ yok.
  // Not (CP-MODAL-PRESENCE): çağrı yeri koşullu mount ettiği için çıkış animasyonu
  // oynamaz — bilinen ortak borç; bu CP'de çözülmez.
  return (
    <Modal
      open
      onClose={onClose}
      ariaLabel="Motor analizi"
      size="max-w-5xl"
      padded={false}
      className="max-h-[92vh]"
    >
      {/* Başlık şeridi — shrink-0: gövde kayarken motor kimliği sabit kalır */}
      <div className="flex items-start justify-between gap-3 px-6 pt-6 pb-4 shrink-0">
        <div>
          <p className="text-micro text-text-muted uppercase font-medium mb-1">
            Motor Analizi
          </p>
          <h3 className="text-lg font-display text-text-primary">{engine.label}</h3>
        </div>
        <button onClick={onClose} aria-label="Kapat" className="text-text-muted hover:text-text-primary p-1">
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Gövde — kısa viewport'ta iç scroll (min-h-0: flex-col içinde küçülebilsin) */}
      <div className="grow min-h-0 overflow-y-auto px-6 pb-6 space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-bg-secondary/60 rounded-xl p-3 border border-border-subtle text-center">
            <p className="text-micro text-text-muted uppercase font-medium mb-1">Skor</p>
            <p className="text-h2 font-display font-mono text-text-primary">{formatNumber(engine.score, 1)}<span className="text-sm text-text-muted">/100</span></p>
          </div>
          <div className="bg-bg-secondary/60 rounded-xl p-3 border border-border-subtle text-center">
            <p className="text-micro text-text-muted uppercase font-medium mb-1">
              {engine.name === 'risk_management' ? 'Güvenlik' : 'Yön'}
            </p>
            <p className={cn('text-lg font-display uppercase', biasColor)}>
              {engine.name === 'risk_management'
                ? (engine.bias === 'bullish' ? 'GÜVENLİ' : engine.bias === 'bearish' ? 'RİSKLİ' : 'ORTA')
                : (engine.bias === 'bullish' ? 'LONG' : engine.bias === 'bearish' ? 'SHORT' : 'NÖTR')}
            </p>
          </div>
        </div>

        {CHART_ENGINES.has(engine.name) && (
          <div>
            <p className="text-micro text-text-muted uppercase font-medium mb-2">
              Grafik Üzerinde
            </p>
            <EngineMiniChart
              symbol={symbol}
              timeframe={timeframe}
              engineName={engine.name}
              supportingData={engine.supportingData}
            />
          </div>
        )}

        <div>
          <button
            onClick={() => setShowFindings((v) => !v)}
            className="w-full flex items-center justify-between text-micro text-text-muted uppercase font-medium mb-2 hover:text-text-primary transition-colors"
          >
            <span>Bulgular ({engine.findings.length})</span>
            <span className="text-accent-primary normal-case">{showFindings ? 'Gizle ▲' : 'Göster ▼'}</span>
          </button>
          {showFindings && (
            engine.findings.length === 0 ? (
              <p className="text-xs text-text-muted text-center py-4">Detaylı bulgu yok.</p>
            ) : (
              <>
                <p className="text-micro text-text-muted italic mb-2">Motorun ham teknik çıktısı — verbatim, değiştirilmedi.</p>
                <ul className="space-y-2">
                  {engine.findings.map((f, i) => (
                    <li key={i} className="flex gap-2 text-xs text-text-secondary leading-relaxed bg-bg-secondary/40 rounded-lg px-3 py-2 border border-border-subtle">
                      <span className="text-accent-primary flex-shrink-0">•</span>
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>
              </>
            )
          )}
        </div>
      </div>
    </Modal>
  );
}

/** Vertical price ladder — TP3 on top, SL at bottom */
function PriceLadder({ signal }: { signal: ApiSignal }) {
  const isLong = signal.direction === 'bullish' || signal.signal_type.toLowerCase().includes('buy');
  const entry  = signal.entry_zone_low && signal.entry_zone_high
                 ? (signal.entry_zone_low + signal.entry_zone_high) / 2
                 : null;

  // For LONG: TP3 > TP2 > TP1 > ENTRY > SL  (descending visual order)
  // For SHORT: SL > ENTRY > TP1 > TP2 > TP3
  const items: { key: string; label: string; value: number | null; color: string; emphasize?: boolean; hit?: boolean }[] = isLong
    ? [
        { key: 'tp3',   label: 'TP3',   value: signal.tp3 ?? null,        color: 'bullish', hit: !!signal.hit_tp3 },
        { key: 'tp2',   label: 'TP2',   value: signal.tp2 ?? null,        color: 'bullish', hit: !!signal.hit_tp2 },
        { key: 'tp1',   label: 'TP1',   value: signal.tp1 ?? null,        color: 'bullish', hit: !!signal.hit_tp1 },
        { key: 'entry', label: 'GİRİŞ', value: entry,                     color: 'accent', emphasize: true },
        { key: 'sl',    label: 'SL',    value: signal.stop_loss ?? null,  color: 'bearish' },
      ]
    : [
        { key: 'sl',    label: 'SL',    value: signal.stop_loss ?? null,  color: 'bearish' },
        { key: 'entry', label: 'GİRİŞ', value: entry,                     color: 'accent', emphasize: true },
        { key: 'tp1',   label: 'TP1',   value: signal.tp1 ?? null,        color: 'bullish', hit: !!signal.hit_tp1 },
        { key: 'tp2',   label: 'TP2',   value: signal.tp2 ?? null,        color: 'bullish', hit: !!signal.hit_tp2 },
        { key: 'tp3',   label: 'TP3',   value: signal.tp3 ?? null,        color: 'bullish', hit: !!signal.hit_tp3 },
      ];

  return (
    <div className="bg-bg-secondary/30 border border-border-subtle rounded-card p-5">
      <div className="space-y-0">
        {items.map((item, idx) => {
          const colorClass = item.color === 'bullish' ? 'bg-bullish text-black border-bullish'
                            : item.color === 'bearish' ? 'bg-bearish text-white border-bearish'
                            : 'bg-accent-primary text-white border-accent-primary';
          // A TP not yet hit hasn't happened — it gets a plain outline and
          // no motion, full stop. Motion (pulse + traveling highlight) is
          // reserved for the moment hit_tpN actually flips true: that's a
          // real, already-achieved event worth a small celebration, not a
          // "still waiting" progress indicator on something that may never
          // come.
          const outlineClass = 'bg-transparent text-bullish border-bullish';
          const badgeColorClass = item.hit ? colorClass : outlineClass;
          const lineColor  = item.color === 'bullish' ? 'bg-bullish/40'
                            : item.color === 'bearish' ? 'bg-bearish/40'
                            : 'bg-accent-primary/40';
          // R-multiple of each level vs the SL distance (reward ÷ risk). Surfaces
          // that e.g. a TP1 at 0.7R is a small, conservative first target — so a
          // "TP1 reached" tick isn't misread as a big win. Pure presentation;
          // signal geometry is NOT touched.
          const rMult = entry != null && signal.stop_loss != null && item.value != null
                        && entry !== signal.stop_loss && item.key !== 'entry'
            ? Math.abs(item.value - entry) / Math.abs(entry - signal.stop_loss)
            : null;
          const lowTp1 = item.key === 'tp1' && rMult != null && rMult < 0.6;
          return (
            <div key={item.key}>
              <div className="flex items-center gap-4">
                {/* Left label badge */}
                <div className={cn(
                  'w-16 text-center text-micro font-medium py-1.5 rounded-lg border-2 flex items-center justify-center gap-1',
                  badgeColorClass,
                  item.emphasize && 'scale-110',
                  item.hit && 'tp-pulse-badge'
                )}>
                  {item.hit && <Check className="w-3 h-3" />}
                  {item.label}
                </div>
                {/* Dashed connector — a TP that's actually been reached gets
                    a traveling highlight layered on top of the static
                    dashed line underneath, rather than replacing it. */}
                <div className="relative flex-1 border-t-2 border-dashed border-border-subtle/60">
                  {item.hit && (
                    <div className="absolute inset-x-0 -top-[3px] h-[2px] tp-pulse-line" />
                  )}
                </div>
                {/* R-multiple badge + value */}
                <div className="flex items-center justify-end gap-2 min-w-[150px]">
                  {rMult != null && (
                    <span
                      title={item.key === 'sl'
                        ? 'Risk birimi (1R) = giriş ile stop arası mesafe'
                        : lowTp1
                          ? 'TP1 girişe yakın: küçük ama yüksek olasılıklı ilk hedef (R = ödül/risk)'
                          : 'Ödül/risk: hedefin, giriş–stop mesafesine oranı'}
                      className={cn(
                        'text-micro font-mono font-medium px-1.5 py-0.5 rounded border',
                        lowTp1
                          ? 'text-amber bg-amber/10 border-amber/30'
                          : 'text-text-muted bg-bg-tertiary/60 border-border-subtle'
                      )}
                    >
                      {item.key === 'sl' ? '1R risk' : `${formatNumber(rMult, 1)}R`}
                    </span>
                  )}
                  <span className={cn(
                    'text-sm font-display font-mono text-right',
                    item.color === 'bullish' ? 'text-bullish'
                    : item.color === 'bearish' ? 'text-bearish'
                    : 'text-accent-primary',
                    item.emphasize && 'text-base'
                  )}>
                    {formatPrice(item.value)}
                  </span>
                </div>
              </div>
              {/* Vertical bridge to next item */}
              {idx < items.length - 1 && (
                <div className="flex pl-8 my-0.5">
                  <div className={cn('w-0.5 h-3', lineColor)} />
                </div>
              )}
            </div>
          );
        })}
      </div>
      <p className="mt-3 text-micro text-text-muted leading-snug">
        <span className="font-mono font-display">R</span> = ödül/risk (hedefin, giriş–stop mesafesine oranı).
        TP1 çoğu sinyalde 1R altındadır — küçük ama yüksek olasılıklı ilk kâr kademesidir.
      </p>
    </div>
  );
}

/** Compact horizontal risk badge */
function RiskBadge({ level }: { level: string | undefined }) {
  const config = {
    low:        { label: 'DÜŞÜK',       cls: 'bg-bullish/15 text-bullish border-bullish/40' },
    medium:     { label: 'ORTA',        cls: 'bg-amber/15 text-amber border-amber/40' },
    high:       { label: 'YÜKSEK',      cls: 'bg-amber/15 text-amber border-amber/40' },
    very_high:  { label: 'ÇOK YÜKSEK',  cls: 'bg-bearish/15 text-bearish border-bearish/40' },
  }[(level ?? 'medium').toLowerCase()] ?? { label: 'BİLİNMİYOR', cls: 'bg-bg-tertiary text-text-muted border-border-subtle' };

  const isVeryHigh = (level ?? '').toLowerCase() === 'very_high';

  return (
    <div className={cn(
      'flex items-center gap-2 px-3 py-2 rounded-xl border whitespace-nowrap',
      config.cls,
      // Cok-yuksek risk vurgusu STATIK (P6/M07, MO-06 idle-nabiz yasak):
      // dikkat cekme isi config.cls yuksek-kontrast renk+ikon+etikette.
    )}>
      <ShieldAlert className="w-4 h-4 flex-shrink-0" />
      <div className="flex flex-col leading-none">
        <span className="text-micro uppercase font-medium opacity-70">Risk</span>
        <span className="text-xs font-display uppercase tracking-wide mt-0.5">{config.label}</span>
      </div>
    </div>
  );
}

// ─── Tab content extractors ─────────────────────────────────────────────────
// The AI explanation's section headers are plain text lines (no markdown
// "#"), so a section's content has to stop at the next KNOWN header line —
// otherwise (as happened before this fix) "Özet Analiz" never finds a
// boundary and swallows everything to the end of the text, making the
// "Özet" tab identical to "Tam AI Analizi".
const SECTION_BOUNDARIES = [
  /Özet Analiz/i,
  /Destekleyici ve Kısıtlayıcı Unsurlar/i,
  /Piyasa Yapısı ve Hacim Yorumu/i,
  /Smart Money.*CRT.*Analizi/i,
  /Risk Değerlendirmesi(?:\s+ve\s+İşlem Planı)?/i,
].map((r) => r.source).join('|');

function extractSection(text: string, header: RegExp): string {
  const m = text.match(new RegExp(`${header.source}([\\s\\S]+?)(?=\\n(?:${SECTION_BOUNDARIES})|\\n#+\\s|$)`, 'i'));
  return m ? m[1].trim() : '';
}

interface ExplanationTabs {
  summary: string;
  marketStructure: string;
  risk: string;
  tradePlan: string;
  full: string;
}

function buildTabs(raw: string | null | undefined): ExplanationTabs {
  if (!raw) return { summary: '', marketStructure: '', risk: '', tradePlan: '', full: '' };
  const clean = stripMd(raw);
  return {
    summary:         extractSection(clean, /Özet Analiz[:\s]+/i) || clean.split('\n\n')[0]?.slice(0, 400) || '',
    marketStructure: extractSection(clean, /Piyasa Yapısı ve Hacim Yorumu[:\s]+/i)
                  || extractSection(clean, /Smart Money.*CRT.*Analizi[:\s]+/i),
    risk:            extractSection(clean, /Risk Değerlendirmesi(?:\s+ve\s+İşlem Planı)?[:\s]+/i),
    tradePlan:       extractSection(clean, /İşlem Planı[:\s]+/i)
                  || extractSection(clean, /Risk Değerlendirmesi ve İşlem Planı[:\s]+/i),
    full:            clean,
  };
}

// ─── Main Component ─────────────────────────────────────────────────────────

interface SignalDetailSectionProps {
  signal: ApiSignal;
  /** Narrow vertical-sidebar layout (stacked sections, no side-by-side grid)
   * for placement next to a chart, instead of the default wide layout used
   * in the signals-list drawer. */
  compact?: boolean;
}

export const SignalDetailSection: React.FC<SignalDetailSectionProps> = ({ signal, compact = false }) => {
  const [openEngine, setOpenEngine]   = useState<EngineRow | null>(null);
  const [activeTab, setActiveTab]     = useState<keyof ExplanationTabs>('summary');

  const rrRatio  = calculateRR(signal);
  const engines  = parseEngines(signal.engines_data);
  const tabs     = buildTabs(signal.explanation_tr);
  // AT-2 provenance: konsensüs dökümü, Karot'un render ettiği AYNI işaretli-güvenden
  // sayılır (deadzone-tutarlı) → tooltip ile glif birebir uyumlu.
  const karotConfs = signalToKarotConfs(signal.engines_data);
  const consensusBull = karotConfs.filter((c) => c > 0).length;
  const consensusBear = karotConfs.filter((c) => c < 0).length;
  const consensusNeutral = karotConfs.length - consensusBull - consensusBear;

  // Activation event: a user opened a full signal detail (the product's value moment).
  useEffect(() => {
    track(AnalyticsEvent.signal_viewed, {
      signal_id: signal.id,
      symbol: signal.asset.symbol,
      market: signal.asset.market,
      timeframe: signal.timeframe,
    });
  }, [signal.id]);

  const dir = (signal.direction ?? '').toLowerCase();
  const direction = dir === 'bullish' ? { label: 'LONG',  cls: 'text-bullish', icon: TrendingUp }
                  : dir === 'bearish' ? { label: 'SHORT', cls: 'text-bearish', icon: TrendingDown }
                  : { label: 'BEKLE', cls: 'text-text-muted', icon: Activity };

  const DirIcon = direction.icon;

  // Available tabs (skip empty sections). No separate "İşlem Planı" tab —
  // the AI explanation template only ever produces one combined "Risk
  // Değerlendirmesi ve İşlem Planı" section, so a dedicated trade-plan tab
  // would always just duplicate "Risk" verbatim.
  const ALL_TABS: { key: keyof ExplanationTabs; label: string }[] = [
    { key: 'summary',         label: 'Özet' },
    { key: 'marketStructure', label: 'Piyasa Yapısı' },
    { key: 'risk',            label: 'Risk & İşlem Planı' },
    { key: 'full',            label: 'Tam AI Analizi' },
  ];
  const availableTabs = ALL_TABS.filter((t) => tabs[t.key]);

  // Ensure activeTab is valid
  useEffect(() => {
    if (availableTabs.length > 0 && !availableTabs.find((t) => t.key === activeTab)) {
      setActiveTab(availableTabs[0].key);
    }
  }, [signal.id]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className={compact ? 'space-y-4' : 'space-y-6'}>
      {/* ─── 1. Hero — wide: side-by-side; compact: stacked for a narrow sidebar ─── */}
      <GlassCard dense={compact}>
        <div className={cn(
          'flex justify-between gap-6',
          compact ? 'flex-col gap-4' : 'flex-col lg:flex-row lg:items-center'
        )}>
          {/* Left: Symbol + Direction */}
          <div className={cn('flex items-center', compact ? 'gap-3' : 'gap-5')}>
            <div className={cn(
              'rounded-xl bg-bg-tertiary border border-border-subtle flex items-center justify-center font-display font-mono text-accent-primary flex-shrink-0 overflow-hidden',
              compact ? 'w-11 h-11 text-sm' : 'w-16 h-16 text-base'
            )}>
              {signal.asset?.symbol && <CoinIcon symbol={signal.asset.symbol} assetType={signal.asset.asset_type} />}
            </div>
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className={cn('font-display text-text-primary', compact ? 'text-base' : 'text-h2')}>{signal.asset?.symbol}</span>
                <span className="text-micro font-medium text-accent-primary bg-accent-primary/10 border border-accent-primary/30 px-1.5 py-0.5 rounded uppercase">
                  {signal.timeframe}
                </span>
              </div>
              <div className={cn('flex items-center gap-2 font-display tracking-wide', direction.cls, compact ? 'text-lg' : 'text-h1')}>
                <DirIcon className={compact ? 'w-4 h-4' : 'w-7 h-7'} />
                {direction.label}
              </div>
              <p className={cn('text-text-muted mt-1', compact ? 'text-micro' : 'text-micro mt-1.5')}>
                Üretildi: {formatAbsoluteTimeTR(signal.generated_at)} (TR) · {formatRelativeTime(signal.generated_at)}
              </p>
            </div>
          </div>

          {/* Right (wide) / Below (compact): Risk + Scores */}
          <div className={cn('flex items-center flex-wrap', compact ? 'gap-3' : 'gap-4')}>
            <RiskBadge level={signal.risk_level} />
            <div className={cn('flex items-center pl-3 border-l border-border-subtle', compact ? 'gap-3' : 'gap-5 pl-4')}>
              <div className="flex flex-col items-center">
                {/* Same /10 scale as Sinyal Merkezi's "Kalite Skoru" column
                    (Math.round(confidence/10)) — surfacing it here too so
                    a signal's strength reads consistently across pages. */}
                <span className={cn(
                  'font-display font-mono',
                  compact ? 'text-xl' : 'text-h1',
                  signal.confidence_score >= 80 ? 'text-bullish' : signal.confidence_score >= 65 ? 'text-amber' : 'text-text-muted'
                )}>
                  {Math.round(signal.confidence_score / 10)}<span className="text-text-muted text-sm">/10</span>
                </span>
                <span className="text-micro text-text-muted mt-1 font-medium uppercase">Kalite</span>
              </div>
              <div className="flex flex-col items-center">
                <ScoreRing score={signal.confidence_score} size={compact ? 50 : 76} strokeWidth={compact ? 4 : 6} />
                <span className="text-micro text-text-muted mt-1 font-medium uppercase">Güven</span>
              </div>
              <div className="flex flex-col items-center">
                <ScoreRing score={signal.probability_score} size={compact ? 50 : 76} strokeWidth={compact ? 4 : 6} />
                <span className="text-micro text-text-muted mt-1 font-medium uppercase">Olasılık</span>
              </div>
            </div>
          </div>
        </div>
      </GlassCard>

      {/* ─── 1b. Adaptive Intelligence — "is this signal still valid?" ─── */}
      {signal.id && <IntelligencePanel signalId={signal.id} compact={compact} />}

      {/* ─── 2. Trade Plan + Engine Scores — wide: side-by-side; compact: stacked ─── */}
      <div className={compact ? 'flex flex-col gap-4' : 'grid grid-cols-1 xl:grid-cols-[420px_1fr] gap-6'}>
        {/* Trade Plan column */}
        <div>
          <h3 className={cn('font-medium text-text-muted uppercase flex items-center gap-1.5', compact ? 'text-micro mb-2' : 'text-xs mb-3')}>
            <Target className="w-3.5 h-3.5 text-accent-primary" /> İşlem Planı
            {rrRatio !== '—' && (
              <span className="ml-auto flex items-center gap-1.5 text-micro text-text-secondary normal-case font-normal">
                <Scale className="w-3 h-3" />
                R:R
                <span className={cn(
                  'font-mono font-display uppercase',
                  parseFloat(rrRatio) >= 2 ? 'text-bullish' : 'text-text-primary'
                )}>{rrRatio}</span>
              </span>
            )}
          </h3>
          <PriceLadder signal={signal} />
        </div>

        {/* Engine Scores column */}
        {engines.length > 0 && (
          <div>
            <h3 className={cn('font-medium text-text-muted uppercase flex items-center gap-1.5', compact ? 'text-micro mb-2' : 'text-xs mb-3')}>
              <BarChart3 className="w-3.5 h-3.5 text-accent-primary" /> Motor Skorları
              <span className="ml-auto flex items-center gap-2 min-w-0">
                {!compact && (
                  <span
                    className="text-micro text-text-muted normal-case font-normal hidden sm:inline truncate"
                    title="Bu skorlar sinyalin üretildiği tarama anına ait. Yön değişmediği sürece sistem skorları yeniden hesaplamaz — gerçek bir tersine dönüş (reversal) olduğunda otomatik güncellenir."
                  >
                    Skorlar {formatRelativeTime(signal.generated_at)} hesaplandı · Detay için karta tıkla
                  </span>
                )}
              </span>
            </h3>
            {/* S4a (PV-D4 census tek-biçim): konsensüs census serbest metinden kanonik
                ProvenanceReceipt makbuzuna taşındı — Dock census'uyla aynı gramer;
                ayraç/ton/tabular primitive'den. AT-2 bilgisi korunur (4 segment
                koşulsuz — 0-değerler eskisi gibi görünür kalır). Glyph/süs YOK. */}
            <ProvenanceReceipt
              className={cn('flex-wrap normal-case font-normal', compact ? 'mb-2' : 'mb-3')}
              segments={[
                `${karotConfs.length} motor`,
                `${consensusBull} LONG`,
                `${consensusBear} SHORT`,
                `${consensusNeutral} nötr`,
              ]}
            />
            <div className={compact ? 'grid grid-cols-3 gap-2' : 'grid grid-cols-2 sm:grid-cols-3 gap-3'}>
              {engines.map((engine) => (
                <EngineCard
                  key={engine.name}
                  engine={engine}
                  onClick={() => setOpenEngine(engine)}
                  compact={compact}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ─── 3. AI Explanation — wide: full width; compact: stacked, scrollable ─── */}
      {availableTabs.length > 0 && (
        <div className={compact ? 'flex-1 flex flex-col min-h-0' : undefined}>
          <h3 className={cn('font-medium text-text-muted uppercase flex items-center gap-1.5', compact ? 'text-micro mb-2' : 'text-xs mb-3')}>
            <FileText className="w-3.5 h-3.5 text-accent-primary" /> AI Açıklaması
          </h3>

          <div className="flex gap-1 mb-0 overflow-x-auto border-b border-border-subtle">
            {availableTabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={cn(
                  'font-display whitespace-nowrap transition-[background-color,color,border-radius]',
                  compact ? 'px-2.5 py-2 text-micro' : 'px-4 py-2.5 text-xs',
                  activeTab === tab.key
                    ? 'bg-accent-primary text-white rounded-t-lg'
                    : 'text-text-muted hover:text-text-primary hover:bg-bg-secondary/40'
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className={cn(
            'bg-bg-secondary/30 border border-t-0 border-border-subtle rounded-b-xl',
            compact ? 'p-4 overflow-y-auto' : 'p-5 min-h-[140px]'
          )}>
            <div className={cn('text-text-secondary leading-relaxed whitespace-pre-wrap', compact ? 'text-xs' : 'text-sm')}>
              {tabs[activeTab] || 'Bu bölüm için bilgi yok.'}
            </div>
          </div>
        </div>
      )}

      {/* ─── Engine Detail Modal ───────────────────────────────────────── */}
      {openEngine && (
        <EngineDetailModal
          engine={openEngine}
          symbol={signal.asset?.symbol ?? ''}
          timeframe={signal.timeframe}
          onClose={() => setOpenEngine(null)}
        />
      )}

      <InvestmentDisclaimer variant="inline" className="mt-4" />
    </div>
  );
};
