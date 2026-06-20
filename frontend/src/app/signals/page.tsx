'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { Zap, RefreshCw, TrendingUp, TrendingDown, Eye, LineChart, FileDown } from 'lucide-react';
import { fetchActiveSignals, triggerBatchGeneration, downloadSignalPdf, type ApiSignal } from '@/lib/api';
import { useLivePrices } from '@/hooks/useLivePrices';
import { SignalType } from '@/types';
import { cn, formatAbsoluteTimeTR } from '@/lib/utils';
import { SignalDetailSection } from '@/components/ui/SignalDetailSection';

// ─── Helpers ─────────────────────────────────────────────────────────────────

function qualityScore(confidence: number): number {
  return Math.round(confidence / 10);
}

function qualityColor(score: number): string {
  if (score >= 8) return 'bg-bullish';
  if (score >= 6) return 'bg-yellow-400';
  if (score >= 4) return 'bg-orange-400';
  return 'bg-bearish';
}

function qualityTextColor(score: number): string {
  if (score >= 8) return 'text-bullish';
  if (score >= 6) return 'text-yellow-400';
  if (score >= 4) return 'text-orange-400';
  return 'text-bearish';
}

/** Derive HTF Alignment label from engine_results JSON */
function getHtfAlignment(enginesData: any): { label: string; type: 'ob' | 'fvg' | 'neutral'; bullish: boolean } {
  if (!enginesData) return { label: 'NÖTR', type: 'neutral', bullish: true };

  const smc = enginesData?.smart_money_concepts;
  const smcBias: string = smc?.bias ?? 'NEUTRAL';
  const findings: string[] = smc?.key_findings ?? [];
  const isBullish = smcBias === 'BULLISH';

  const hasOB  = findings.some((f: string) => f.toLowerCase().includes('order block'));
  const hasFVG = findings.some((f: string) => f.toLowerCase().includes('fair value') || f.toLowerCase().includes('fvg'));

  if (hasOB)  return { label: isBullish ? 'BULLISH OB'  : 'BEARISH OB',  type: 'ob',  bullish: isBullish };
  if (hasFVG) return { label: isBullish ? 'BULLISH FVG' : 'BEARISH FVG', type: 'fvg', bullish: isBullish };

  // Fallback to direction bias
  if (smcBias === 'BULLISH') return { label: 'BULLISH', type: 'neutral', bullish: true };
  if (smcBias === 'BEARISH') return { label: 'BEARISH', type: 'neutral', bullish: false };
  return { label: 'NÖTR', type: 'neutral', bullish: true };
}

/** Derive Purge Type from CRT engine */
function getPurgeType(enginesData: any): { label: string; low: boolean } | null {
  if (!enginesData) return null;
  const crt = enginesData?.candle_range_theory;
  if (!crt) return null;

  const dir: string | null = crt?.supporting_data?.latest_signal_direction ?? null;
  const sweeps: number = crt?.supporting_data?.sweeps_count ?? 0;

  if (sweeps === 0) return null;
  if (dir === 'long')  return { label: 'LOW',  low: true };
  if (dir === 'short') return { label: 'HIGH', low: false };

  // fallback: range position zone
  const zone: string = crt?.supporting_data?.range_position?.zone ?? '';
  if (zone === 'discount') return { label: 'LOW',  low: true };
  if (zone === 'premium')  return { label: 'HIGH', low: false };
  return null;
}

type DirState = 'long' | 'short' | 'wait';
function directionLabel(sig: ApiSignal): { label: string; state: DirState } {
  const d = (sig.direction ?? '').toLowerCase();
  const t = (sig.signal_type ?? '').toLowerCase();
  if (d === 'bullish' || t === 'buy' || t === 'strong_buy')
    return { label: 'LONG',  state: 'long' };
  if (d === 'bearish' || t === 'sell' || t === 'strong_sell')
    return { label: 'SHORT', state: 'short' };
  return { label: 'BEKLE', state: 'wait' };
}

interface OnchainInfo {
  fearGreed: number | null;
  fearGreedClass: string | null;
  athDistance: number | null;
  hashRate: number | null;
  fastFee: number | null;
  devScore: number | null;
  rank: number | null;
  findings: string[];
  applicable: boolean;
}

function getOnchainInfo(enginesData: any): OnchainInfo | null {
  if (!enginesData) return null;
  const o = enginesData?.onchain_analysis;
  if (!o) return null;
  const sd = o.supporting_data ?? {};
  return {
    fearGreed:      sd.fear_greed_value ?? null,
    fearGreedClass: sd.fear_greed_classification ?? null,
    athDistance:    sd.ath_distance_pct ?? null,
    hashRate:       sd.btc_hash_rate_ths ?? null,
    fastFee:        sd.btc_fast_fee_sat_vb ?? null,
    devScore:       sd.developer_score ?? null,
    rank:           sd.market_cap_rank ?? null,
    findings:       o.key_findings ?? [],
    applicable:     sd.asset_type !== 'stock',
  };
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function QualityBar({ score }: { score: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-1.5 bg-bg-tertiary rounded-full overflow-hidden">
        <div
          className={cn('h-full rounded-full transition-all', qualityColor(score))}
          style={{ width: `${score * 10}%` }}
        />
      </div>
      <span className={cn('text-xs font-bold font-mono', qualityTextColor(score))}>
        {score}/10
      </span>
    </div>
  );
}

function HtfBadge({ label, bullish }: { label: string; bullish: boolean }) {
  return (
    <span className={cn(
      'inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold tracking-wide',
      bullish
        ? 'bg-bullish/15 text-bullish border border-bullish/30'
        : 'bg-bearish/15 text-bearish border border-bearish/30'
    )}>
      {label}
    </span>
  );
}

function PurgeBadge({ label, low }: { label: string; low: boolean }) {
  return (
    <span className={cn(
      'inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold tracking-wide',
      low
        ? 'bg-bullish/10 text-bullish'
        : 'bg-bearish/10 text-bearish'
    )}>
      {label}
    </span>
  );
}

function OutcomeBadge({ outcome }: { outcome: string }) {
  const config: Record<string, { label: string; cls: string }> = {
    active:    { label: 'AKTİF',     cls: 'bg-accent-primary/15 text-accent-primary border-accent-primary/30' },
    win:       { label: 'KAZANDI ✓', cls: 'bg-bullish/15 text-bullish border-bullish/30' },
    loss:      { label: 'PATLADI ✗', cls: 'bg-bearish/15 text-bearish border-bearish/30' },
    breakeven: { label: 'BERABERE',  cls: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30' },
    expired:   { label: 'GEÇERSİZ',  cls: 'bg-text-muted/15 text-text-muted border-text-muted/30' },
  };
  const c = config[outcome] ?? config.active;
  return (
    <span className={cn(
      'inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold tracking-wide border',
      c.cls
    )}>
      {c.label}
    </span>
  );
}

function DirectionBadge({ label, state }: { label: string; state: DirState }) {
  const config = {
    long:  { cls: 'bg-bullish text-black',     icon: <TrendingUp   className="w-3 h-3" /> },
    short: { cls: 'bg-bearish text-white',     icon: <TrendingDown className="w-3 h-3" /> },
    wait:  { cls: 'bg-text-muted/40 text-text-primary border border-text-muted/40', icon: <span className="w-3 h-3 inline-block">⏸</span> },
  } as const;
  const c = config[state];
  return (
    <span className={cn(
      'inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-[11px] font-bold',
      c.cls
    )}>
      {c.icon}
      {label}
    </span>
  );
}

// ─── Signal Detail Drawer ─────────────────────────────────────────────────────

const ENGINE_LABELS: Record<string, string> = {
  technical_analysis:     'Teknik Analiz',
  market_structure:       'Piyasa Yapısı',
  smart_money_concepts:   'Smart Money (SMC)',
  candle_range_theory:    'CRT (Mum Aralığı)',
  volume_analysis:        'Hacim Analizi',
  risk_management:        'Risk Yönetimi',
  fundamental_analysis:   'Temel Analiz',
  onchain_analysis:       'On-Chain & Sentiment',
  macro_analysis:         'Makro Görünüm',
};

interface EngineRow {
  name: string;
  label: string;
  score: number;
  bias: string;
  findings: string[];
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
      bias:     String(e.bias ?? 'neutral'),
      findings: Array.isArray(e.key_findings) ? e.key_findings : [],
    }));
}

function biasInfo(bias: string): { color: string; label: string; ring: string } {
  const b = bias.toLowerCase();
  if (b.includes('strong_bullish'))  return { color: 'text-bullish',   label: 'GÜÇLÜ ALIM', ring: 'bg-bullish' };
  if (b.includes('bullish'))         return { color: 'text-bullish',   label: 'ALIM',       ring: 'bg-bullish/70' };
  if (b.includes('strong_bearish'))  return { color: 'text-bearish',   label: 'GÜÇLÜ SATIM',ring: 'bg-bearish' };
  if (b.includes('bearish'))         return { color: 'text-bearish',   label: 'SATIM',      ring: 'bg-bearish/70' };
  return { color: 'text-text-muted', label: 'NÖTR', ring: 'bg-text-muted/70' };
}

function scoreColor(score: number): string {
  if (score >= 70) return 'bg-bullish';
  if (score >= 55) return 'bg-bullish/60';
  if (score >= 45) return 'bg-yellow-500/70';
  if (score >= 30) return 'bg-bearish/60';
  return 'bg-bearish';
}

/** Strip markdown noise (###, **, *, backticks) to plain text. */
function stripMd(raw: string): string {
  return raw
    .replace(/^#+\s*/gm, '')         // ### headings
    .replace(/\*\*(.+?)\*\*/g, '$1') // **bold**
    .replace(/\*(.+?)\*/g, '$1')     // *italic*
    .replace(/`([^`]+)`/g, '$1')     // `code`
    .replace(/—/g, '·')
    .trim();
}

/** Translate English engine findings → Türkçe. Pattern-based for safety. */
type Pat = [RegExp, string | ((m: RegExpMatchArray) => string)];
const FINDING_PATTERNS: Pat[] = [
  // ── Trend / Technical ──
  [/Trend indicators lean bearish \((\d+)\/(\d+) bearish\)/i, (m) => `Trend göstergeleri AYI yönlü (${m[1]}/${m[2]} ayı)`],
  [/Trend indicators lean bullish \((\d+)\/(\d+) bullish\)/i, (m) => `Trend göstergeleri BOĞA yönlü (${m[1]}/${m[2]} boğa)`],
  [/MACD:\s*MACD=(-?[\d.]+)\s+Signal=(-?[\d.]+)\s+Hist=(-?[\d.]+)\s*→?\s*bearish/i,
    (m) => `MACD: MACD=${m[1]} Sinyal=${m[2]} Histogram=${m[3]} → AYI`],
  [/MACD:\s*MACD=(-?[\d.]+)\s+Signal=(-?[\d.]+)\s+Hist=(-?[\d.]+)\s*→?\s*bullish/i,
    (m) => `MACD: MACD=${m[1]} Sinyal=${m[2]} Histogram=${m[3]} → BOĞA`],
  [/RSI:\s*([\d.]+)\s*\(overbought\)/i, (m) => `RSI: ${m[1]} (aşırı alım)`],
  [/RSI:\s*([\d.]+)\s*\(oversold\)/i, (m) => `RSI: ${m[1]} (aşırı satım)`],
  [/RSI:\s*([\d.]+)\s*\(neutral\)/i, (m) => `RSI: ${m[1]} (nötr)`],

  // ── Market Structure ──
  [/Market structure:\s*Downtrend/i, 'Piyasa yapısı: DÜŞÜŞ trendi'],
  [/Market structure:\s*Uptrend/i,   'Piyasa yapısı: YÜKSELİŞ trendi'],
  [/Market structure:\s*Sideways/i,  'Piyasa yapısı: YATAY'],
  [/Swing counts\s*[–-]\s*/i, 'Swing sayıları: '],
  [/HH:(\d+)\s+HL:(\d+)\s+LH:(\d+)\s+LL:(\d+)/i,
    (m) => `Yüksek Tepe:${m[1]} Yüksek Dip:${m[2]} Düşük Tepe:${m[3]} Düşük Dip:${m[4]}`],
  [/EMA crossover bullish/i, 'EMA kesişimi BOĞA yönlü'],
  [/EMA crossover bearish/i, 'EMA kesişimi AYI yönlü'],
  [/Bollinger Bands? squeeze detected/i, 'Bollinger Bantları sıkışması tespit edildi'],
  [/Price above EMA[\s_]?50/i, 'Fiyat EMA50 üstünde'],
  [/Price below EMA[\s_]?50/i, 'Fiyat EMA50 altında'],
  [/Price above EMA[\s_]?200/i, 'Fiyat EMA200 üstünde'],
  [/Price below EMA[\s_]?200/i, 'Fiyat EMA200 altında'],
  [/Doji candle detected/i, 'Doji mum tespit edildi'],
  [/Hammer pattern/i, 'Çekiç formasyonu'],
  [/Shooting star pattern/i, 'Kayan yıldız formasyonu'],
  [/Engulfing\s+bullish/i, 'BOĞA engulfing (yutan mum)'],
  [/Engulfing\s+bearish/i, 'AYI engulfing (yutan mum)'],
  [/Break of Structure \(BOS\) detected/i, 'Yapı Kırılımı (BOS) tespit edildi'],
  [/Change of Character \(CHoCH\) detected/i, 'Karakter Değişimi (CHoCH) tespit edildi'],

  // ── SMC ──
  [/Price is in DISCOUNT zone \(Range position:\s*([\d.]+)%\)/i,
    (m) => `Fiyat İSKONTO (alım) bölgesinde (aralık konumu: %${m[1]})`],
  [/Price is in PREMIUM zone \(Range position:\s*([\d.]+)%\)/i,
    (m) => `Fiyat PRİM (satım) bölgesinde (aralık konumu: %${m[1]})`],
  [/Price is in EQUILIBRIUM \(Range position:\s*([\d.]+)%\)/i,
    (m) => `Fiyat dengede (aralık konumu: %${m[1]})`],
  [/Detected (\d+) unfilled Bearish Fair Value Gap\(?s?\)?/i,
    (m) => `${m[1]} adet doldurulmamış AYI FVG tespit edildi`],
  [/Detected (\d+) unfilled Bullish Fair Value Gap\(?s?\)?/i,
    (m) => `${m[1]} adet doldurulmamış BOĞA FVG tespit edildi`],
  [/Detected (\d+) Bearish Order Block\(?s?\)?/i,
    (m) => `${m[1]} adet AYI Order Block tespit edildi`],
  [/Detected (\d+) Bullish Order Block\(?s?\)?/i,
    (m) => `${m[1]} adet BOĞA Order Block tespit edildi`],

  // ── CRT (Candle Range Theory) ──
  [/Expected range state:\s*Contracting \(Ratio:\s*([\d.]+)\)/i,
    (m) => `Aralık durumu: DARALMAKTA (oran ${m[1]})`],
  [/Expected range state:\s*Expanding \(Ratio:\s*([\d.]+)\)/i,
    (m) => `Aralık durumu: GENİŞLEMEKTE (oran ${m[1]})`],
  [/Expected range state:\s*Normal \(Ratio:\s*([\d.]+)\)/i,
    (m) => `Aralık durumu: NORMAL (oran ${m[1]})`],
  [/Price sits at ([\d.]+)% of HTF range \(Discount\)/i,
    (m) => `Fiyat üst aralığın %${m[1]}'inde (İskonto)`],
  [/Price sits at ([\d.]+)% of HTF range \(Premium\)/i,
    (m) => `Fiyat üst aralığın %${m[1]}'inde (Prim)`],
  [/Price sits at ([\d.]+)% of HTF range \(Upper Mid\)/i,
    (m) => `Fiyat üst aralığın %${m[1]}'inde (Üst orta)`],
  [/Price sits at ([\d.]+)% of HTF range \(Lower Mid\)/i,
    (m) => `Fiyat üst aralığın %${m[1]}'inde (Alt orta)`],
  [/Detected (\d+) recent sweep/i,
    (m) => `${m[1]} adet likidite süpürmesi tespit edildi`],

  // ── Volume ──
  [/Bullish exhaustion:\s*Price falling on declining volume/i,
    'BOĞA tükenmesi: Fiyat azalan hacimle düşüyor'],
  [/Bearish exhaustion:\s*Price rising on declining volume/i,
    'AYI tükenmesi: Fiyat azalan hacimle yükseliyor'],
  [/Smart Money distribution phase \(Distribution score:\s*([\d.]+)\)/i,
    (m) => `Akıllı Para DAĞITIM fazı (skor: ${m[1]})`],
  [/Smart Money accumulation phase \(Accumulation score:\s*([\d.]+)\)/i,
    (m) => `Akıllı Para BİRİKİM fazı (skor: ${m[1]})`],
  [/Climax Volume detected \(([\d.]+)x average volume\)/i,
    (m) => `Doruk hacim (ortalamanın ${m[1]}x'i)`],
  [/Price is trading below Volume POC \(([\d.,]+)\)/i,
    (m) => `Fiyat hacim POC'nin ALTINDA (${m[1]})`],
  [/Price is trading above Volume POC \(([\d.,]+)\)/i,
    (m) => `Fiyat hacim POC'nin ÜSTÜNDE (${m[1]})`],

  // ── Risk ──
  [/Volatility level:\s*LOW \(ATR is ([\d.]+)% of price\)/i,
    (m) => `Volatilite: DÜŞÜK (ATR fiyatın %${m[1]}'i)`],
  [/Volatility level:\s*MEDIUM \(ATR is ([\d.]+)% of price\)/i,
    (m) => `Volatilite: ORTA (ATR fiyatın %${m[1]}'i)`],
  [/Volatility level:\s*HIGH \(ATR is ([\d.]+)% of price\)/i,
    (m) => `Volatilite: YÜKSEK (ATR fiyatın %${m[1]}'i)`],
  [/Recommended Position Size:\s*([\d.]+)% of portfolio \(risking ([\d.]+)% on trade\)/i,
    (m) => `Önerilen pozisyon: portföyün %${m[1]}'i (%${m[2]} risk)`],
  [/Max drawdown:\s*([\d.]+)%/i, (m) => `Maksimum drawdown: %${m[1]}`],

  // ── Fundamental ──
  [/Reasonable supply distribution \(([\d.]+)% circulating\)/i,
    (m) => `Makul arz dağılımı (%${m[1]} dolaşımda)`],
  [/High supply dilution risk/i, 'Yüksek arz seyreltme riski'],
  [/Strong ROE \(([\d.]+)%\)/i, (m) => `Güçlü Özsermaye Karlılığı: %${m[1]}`],
  [/Weak ROE \(([\d.]+)%\)/i,   (m) => `Zayıf Özsermaye Karlılığı: %${m[1]}`],
];

function translateFinding(s: string): string {
  if (!s) return s;
  let out = s;
  // Apply each pattern as a *replace* (not full-match) so partial phrases
  // like "Swing counts" only swap the prefix and keep "HH:2 HL:2 LH:2 LL:0".
  for (const [pat, rep] of FINDING_PATTERNS) {
    if (typeof rep === 'function') {
      out = out.replace(pat, (...args) => {
        // args = [full, ...groups, offset, fullString]
        const match = args.slice(0, args.length - 2) as unknown as RegExpMatchArray;
        return rep(match);
      });
    } else {
      out = out.replace(pat, rep);
    }
  }
  // Final word-level cleanup for any leftover English bias words
  return out
    .replace(/\bDowntrend\b/g, 'Düşüş trendi')
    .replace(/\bUptrend\b/g,   'Yükseliş trendi')
    .replace(/\bSideways\b/g,  'Yatay')
    .replace(/\bDiscount\b/g,  'İskonto')
    .replace(/\bPremium\b/g,   'Prim')
    .replace(/\bbullish\b/gi,  'boğa')
    .replace(/\bbearish\b/gi,  'ayı')
    .replace(/\bneutral\b/gi,  'nötr');
}

/** Extract just the first "Özet" section as a clean summary. */
function summaryFrom(text: string | null | undefined): string {
  if (!text) return '';
  const cleaned = stripMd(text);
  const summaryMatch = cleaned.match(/Özet Analiz[:\s]+([\s\S]+?)(?=\n[A-ZĞÜŞİÖÇ][a-zğüşıöç]+\s|$)/);
  if (summaryMatch) return summaryMatch[1].trim().slice(0, 350);
  // fallback: first paragraph
  const firstPara = cleaned.split(/\n\s*\n/)[0];
  return firstPara.slice(0, 350);
}

interface ParsedExplanation {
  summary: string;
  marketStructure: { trend?: string; swing?: string; support?: string; resistance?: string };
  volumeProfile: { exhaustion?: string; volumeRatio?: string; poc?: string; phase?: string };
  smcCrt: { zone?: string; sweeps?: string; range?: string; fvg?: string };
  riskPlan: { level?: string; positionSize?: string; entry?: string; sl?: string; tp1?: string; tp2?: string; tp3?: string };
  invalidation: string;
}

/** Parse the long explanation_tr markdown blob into structured sections. */
function parseExplanation(raw: string | null | undefined): ParsedExplanation {
  const out: ParsedExplanation = {
    summary: '', marketStructure: {}, volumeProfile: {},
    smcCrt: {}, riskPlan: {}, invalidation: '',
  };
  if (!raw) return out;
  const text = stripMd(raw);

  // ── Özet ──
  const summary = text.match(/Özet Analiz[:\s]+([\s\S]+?)(?=\n###|\nDestekleyici|$)/i);
  if (summary) out.summary = summary[1].trim();

  // ── Piyasa Yapısı ve Hacim ──
  const trendM   = text.match(/Trend Yapısı[:*\s]+([^\n.·]+?)(?=[.·\n])/i);
  if (trendM) out.marketStructure.trend = trendM[1].trim();
  const swingM   = text.match(/Swing counts[:\s]*[–-]?\s*([HL\d:\s]+?)(?=[.·\n*])/i);
  if (swingM) out.marketStructure.swing = swingM[1].trim();
  const supM     = text.match(/destek seviyesi\s*`?([\d.,]+)/i);
  if (supM) out.marketStructure.support = supM[1];
  const resM     = text.match(/direnç seviyesi(?:\s*ise)?\s*`?([\d.,]+)/i);
  if (resM) out.marketStructure.resistance = resM[1];

  // ── Hacim Profili ──
  const exhM     = text.match(/(Bullish exhaustion|Bearish exhaustion|Climax Volume[^,.\n]*)/i);
  if (exhM) out.volumeProfile.exhaustion = exhM[1].trim();
  const ratioM   = text.match(/ortalamanın\s*`?([\d.]+x?)/i);
  if (ratioM) out.volumeProfile.volumeRatio = ratioM[1].trim();
  const pocM     = text.match(/Point of Control\)\s*`?([\d.,]+)/i);
  if (pocM) out.volumeProfile.poc = pocM[1];
  const phaseM   = text.match(/(distribution phase|accumulation phase|Smart Money distribution|Smart Money accumulation)/i);
  if (phaseM) out.volumeProfile.phase = phaseM[1].trim();

  // ── SMC + CRT ──
  const zoneM    = text.match(/Değer Bölgesi[:*\s]+[^`]*`?([^`\n.]+)/i);
  if (zoneM) out.smcCrt.zone = zoneM[1].trim();
  const sweepM   = text.match(/Son barlarda\s*`?(\d+)`?\s*adet likidite süpürme/i);
  if (sweepM) out.smcCrt.sweeps = `${sweepM[1]} adet süpürme`;
  const rangeM   = text.match(/range\s*state[:\s]+([A-Za-z]+).*?Ratio:\s*([\d.]+)/i);
  if (rangeM) out.smcCrt.range = `${rangeM[1]} (oran ${rangeM[2]})`;
  const fvgM     = text.match(/Detected\s+(\d+)\s+unfilled\s+(Bullish|Bearish)\s+Fair Value Gap/i);
  if (fvgM) out.smcCrt.fvg = `${fvgM[1]} adet ${fvgM[2] === 'Bullish' ? 'bullish' : 'bearish'} FVG`;

  // ── Risk + Plan ──
  const lvlM     = text.match(/Risk Seviyesi[:*\s]+`?([A-Z_]+)/i);
  if (lvlM) out.riskPlan.level = lvlM[1];
  const psM      = text.match(/(?:Önerilen Pozisyon Büyüklüğü|Position Size)[^:]*:\s*[^%\d]*%?\s*([\d.]+)/i);
  if (psM) out.riskPlan.positionSize = `%${psM[1]}`;
  const entryM   = text.match(/Giriş Bölgesi[:*\s]+`?([\d.,]+\s*[-–]\s*[\d.,]+)/i);
  if (entryM) out.riskPlan.entry = entryM[1].trim();
  const slM      = text.match(/Zarar Kes[^:]*:\s*`?([\d.,]+)/i);
  if (slM) out.riskPlan.sl = slM[1];
  const tp1M     = text.match(/Hedef 1[:*\s]*`?([\d.,]+)/i);
  if (tp1M) out.riskPlan.tp1 = tp1M[1];
  const tp2M     = text.match(/Hedef 2[:*\s]*`?([\d.,]+)/i);
  if (tp2M) out.riskPlan.tp2 = tp2M[1];
  const tp3M     = text.match(/Hedef 3[:*\s]*`?([\d.,]+)/i);
  if (tp3M) out.riskPlan.tp3 = tp3M[1];

  // ── Geçersizlik ──
  const invM     = text.match(/Geçersizlik Şartları[:*\s]+([\s\S]+?)$/i)
                 ?? text.match(/Close (?:above|below)\s+stop loss[\s\S]+?(?=\n\n|$)/i);
  if (invM) out.invalidation = (invM[1] ?? invM[0]).trim().slice(0, 240);

  return out;
}

type DrawerTab = 'overview' | 'engines' | 'explanation';

function SignalDrawer({ sig, onClose }: { sig: ApiSignal; onClose: () => void }) {
  const [tab, setTab] = useState<DrawerTab>('overview');

  const htf     = getHtfAlignment(sig.engines_data);
  const purge   = getPurgeType(sig.engines_data);
  const dir     = directionLabel(sig);
  const qScore  = qualityScore(sig.confidence_score);
  const onchain = getOnchainInfo(sig.engines_data);
  const engines = parseEngines(sig.engines_data);
  const summary = summaryFrom(sig.explanation_tr);

  const longestBullish = engines.filter((e) => e.score > 55).sort((a, b) => b.score - a.score).slice(0, 2);
  const longestBearish = engines.filter((e) => e.score < 45).sort((a, b) => a.score - b.score).slice(0, 2);

  return (
    <div
      className="fixed inset-0 z-50 flex items-end md:items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl glass-panel border border-border-medium rounded-2xl flex flex-col max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ── Sticky Header ── */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border-subtle">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-xl bg-bg-tertiary border border-border-subtle flex items-center justify-center font-bold font-mono text-sm text-accent-primary flex-shrink-0">
              {sig.asset?.symbol.slice(0, 2)}
            </div>
            <div className="min-w-0">
              <h3 className="font-bold text-text-primary flex items-center gap-2 truncate">
                {sig.asset?.symbol}
                <span className="text-[9px] font-bold text-accent-primary bg-accent-primary/10 border border-accent-primary/30 px-1.5 py-0.5 rounded uppercase">
                  {sig.timeframe}
                </span>
              </h3>
              <p className="text-xs text-text-secondary truncate">{sig.asset?.name}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-text-muted hover:text-text-primary text-xl leading-none flex-shrink-0">✕</button>
        </div>

        {/* ── Badges + Levels (fixed) ── */}
        <div className="px-5 py-4 space-y-4 border-b border-border-subtle">
          <div className="flex flex-wrap gap-2">
            <DirectionBadge {...dir} />
            <HtfBadge {...htf} />
            {purge && <PurgeBadge {...purge} />}
            <OutcomeBadge outcome={sig.outcome ?? 'active'} />
          </div>

          {/* Levels grid: compact */}
          <div className="grid grid-cols-4 gap-2 text-center">
            <LevelCard label="Giriş ↓" value={sig.entry_zone_low}    color="text-text-primary" />
            <LevelCard label="Stop SL" value={sig.stop_loss}          color="text-bearish" />
            <LevelCard label="Hedef TP1" value={sig.tp1}              color="text-bullish" />
            <LevelCard label="Hedef TP2" value={sig.tp2}              color="text-bullish" />
          </div>

          {dir.state === 'wait' && (
            <div className="text-[11px] text-yellow-400/90 bg-yellow-500/10 border border-yellow-500/30 rounded-lg px-3 py-2 flex items-start gap-2">
              <span className="text-yellow-400">ⓘ</span>
              <span>
                Bu sinyalde net AL/SAT konsensüsü yok (motorlar uzlaşmadı).
                Yukarıdaki seviyeler <b>bilgi amaçlıdır</b> — pozisyon almadan önce daha güçlü onay bekleyin.
              </span>
            </div>
          )}

          {/* Scores row */}
          <div className="flex items-center justify-between gap-3">
            <div className="flex-1">
              <p className="text-[10px] text-text-muted uppercase font-semibold mb-1">Kalite</p>
              <QualityBar score={qScore} />
            </div>
            <div className="text-center">
              <p className="text-[10px] text-text-muted uppercase font-semibold">Olasılık</p>
              <p className="text-sm font-bold font-mono text-accent-primary">{Number(sig.probability_score ?? 0).toFixed(0)}%</p>
            </div>
            <div className="text-center">
              <p className="text-[10px] text-text-muted uppercase font-semibold">Risk</p>
              <p className="text-sm font-bold font-mono text-text-primary uppercase">{sig.risk_level}</p>
            </div>
          </div>
        </div>

        {/* ── Tabs ── */}
        <div className="flex items-center gap-1 px-5 py-2 border-b border-border-subtle bg-bg-secondary/30">
          {([
            { id: 'overview',    label: 'Genel Bakış' },
            { id: 'engines',     label: `Motorlar (${engines.length})` },
            { id: 'explanation', label: 'AI Açıklaması' },
          ] as const).map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                'px-3 py-1.5 text-xs font-bold rounded-lg transition-all',
                tab === t.id
                  ? 'bg-accent-primary text-white'
                  : 'text-text-muted hover:text-text-primary'
              )}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* ── Scrollable Content ── */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {tab === 'overview' && (
            <>
              {summary && (
                <div className="bg-bg-secondary/40 rounded-xl p-3 border border-border-subtle">
                  <p className="text-[10px] text-text-muted uppercase font-semibold mb-1.5">Özet</p>
                  <p className="text-xs text-text-secondary leading-relaxed">{summary}</p>
                </div>
              )}

              {/* Top bullish / bearish engines */}
              {(longestBullish.length > 0 || longestBearish.length > 0) && (
                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-bullish/5 border border-bullish/20 rounded-xl p-3">
                    <p className="text-[10px] text-bullish uppercase font-semibold mb-2 flex items-center gap-1.5">
                      <TrendingUp className="w-3 h-3" /> Alım Lehine
                    </p>
                    {longestBullish.length > 0 ? (
                      <ul className="space-y-1">
                        {longestBullish.map((e) => (
                          <li key={e.name} className="text-[11px] text-text-primary flex justify-between gap-2">
                            <span className="truncate">{e.label}</span>
                            <span className="font-mono font-bold text-bullish flex-shrink-0">{e.score.toFixed(0)}</span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-[10px] text-text-muted">Lehine motor yok</p>
                    )}
                  </div>
                  <div className="bg-bearish/5 border border-bearish/20 rounded-xl p-3">
                    <p className="text-[10px] text-bearish uppercase font-semibold mb-2 flex items-center gap-1.5">
                      <TrendingDown className="w-3 h-3" /> Satım Lehine
                    </p>
                    {longestBearish.length > 0 ? (
                      <ul className="space-y-1">
                        {longestBearish.map((e) => (
                          <li key={e.name} className="text-[11px] text-text-primary flex justify-between gap-2">
                            <span className="truncate">{e.label}</span>
                            <span className="font-mono font-bold text-bearish flex-shrink-0">{e.score.toFixed(0)}</span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-[10px] text-text-muted">Aleyhine motor yok</p>
                    )}
                  </div>
                </div>
              )}

              {/* On-Chain quick view */}
              {onchain && onchain.applicable && (onchain.fearGreed != null || onchain.athDistance != null) && (
                <div className="bg-bg-secondary/40 rounded-xl p-3 border border-border-subtle">
                  <p className="text-[10px] text-text-muted uppercase font-semibold mb-2">On-Chain Hızlı Bakış</p>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    {onchain.fearGreed != null && (
                      <div className="bg-bg-tertiary/60 rounded-lg p-2">
                        <p className="text-[10px] text-text-muted">Fear &amp; Greed</p>
                        <p className={cn('font-bold font-mono',
                          onchain.fearGreed <= 25 ? 'text-bearish' :
                          onchain.fearGreed >= 75 ? 'text-bullish' : 'text-yellow-400')}>
                          {onchain.fearGreed} <span className="text-[9px] text-text-muted font-normal">{onchain.fearGreedClass ?? ''}</span>
                        </p>
                      </div>
                    )}
                    {onchain.athDistance != null && (
                      <div className="bg-bg-tertiary/60 rounded-lg p-2">
                        <p className="text-[10px] text-text-muted">ATH Mesafesi</p>
                        <p className={cn('font-bold font-mono', onchain.athDistance < -30 ? 'text-bullish' : onchain.athDistance > -10 ? 'text-bearish' : 'text-text-primary')}>
                          {onchain.athDistance.toFixed(1)}%
                        </p>
                      </div>
                    )}
                    {onchain.rank != null && (
                      <div className="bg-bg-tertiary/60 rounded-lg p-2">
                        <p className="text-[10px] text-text-muted">Piyasa Sırası</p>
                        <p className="font-bold font-mono text-text-primary">#{onchain.rank}</p>
                      </div>
                    )}
                    {onchain.fastFee != null && (
                      <div className="bg-bg-tertiary/60 rounded-lg p-2">
                        <p className="text-[10px] text-text-muted">BTC Ücret</p>
                        <p className="font-bold font-mono text-text-primary">{onchain.fastFee} sat/vB</p>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </>
          )}

          {tab === 'engines' && (
            <div className="space-y-2">
              {engines.length === 0 && <p className="text-xs text-text-muted text-center py-6">Motor verisi yok.</p>}
              {engines.map((e) => {
                const bi = biasInfo(e.bias);
                return (
                  <div key={e.name} className="bg-bg-secondary/40 border border-border-subtle rounded-xl p-3">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className={cn('w-1.5 h-1.5 rounded-full flex-shrink-0', bi.ring)} />
                        <span className="text-xs font-bold text-text-primary truncate">{e.label}</span>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <span className={cn('text-[10px] font-bold uppercase', bi.color)}>{bi.label}</span>
                        <span className="text-sm font-bold font-mono text-text-primary tabular-nums">
                          {e.score.toFixed(0)}<span className="text-[10px] text-text-muted">/100</span>
                        </span>
                      </div>
                    </div>
                    {/* Score bar */}
                    <div className="h-1.5 bg-bg-tertiary rounded-full overflow-hidden mb-2">
                      <div className={cn('h-full transition-all', scoreColor(e.score))} style={{ width: `${e.score}%` }} />
                    </div>
                    {e.findings.length > 0 && (
                      <ul className="space-y-0.5">
                        {e.findings.slice(0, 2).map((f, i) => (
                          <li key={i} className="text-[10.5px] text-text-secondary leading-relaxed flex gap-1.5">
                            <span className="text-text-muted flex-shrink-0">·</span> {translateFinding(f)}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {tab === 'explanation' && (
            <SignalDetailSection signal={sig} />
          )}
        </div>

        {/* ── Sticky Action Bar ── */}
        <div className="px-5 py-3 border-t border-border-subtle bg-bg-secondary/30 grid grid-cols-2 gap-2">
          <button
            onClick={() => downloadSignalPdf(sig.id, sig.asset?.symbol ?? 'signal').catch(() =>
              alert('PDF indirilemedi. Pro/Premium aboneliği gerekir.'))}
            className="flex items-center justify-center gap-2 py-2.5 rounded-xl bg-bg-tertiary border border-border-medium hover:border-accent-primary/40 text-text-primary text-sm font-semibold transition-colors"
          >
            <FileDown className="w-4 h-4" /> PDF İndir
          </button>
          <Link
            href={`/markets/${encodeURIComponent(sig.asset?.symbol ?? '')}`}
            className="flex items-center justify-center gap-2 py-2.5 rounded-xl bg-accent-primary hover:bg-accent-secondary text-white text-sm font-semibold transition-colors"
          >
            <LineChart className="w-4 h-4" /> Grafiği Aç
          </Link>
        </div>
      </div>
    </div>
  );
}

function InfoCell({ label, value, accent }: { label: string; value: string; accent: string }) {
  const isMono = accent.includes('mono');
  const cleanAccent = accent.replace(' mono', '');
  return (
    <div className="bg-bg-tertiary/40 rounded-lg p-2">
      <p className="text-[9px] text-text-muted uppercase font-semibold mb-0.5">{label}</p>
      <p className={cn('text-[11px] font-bold', cleanAccent, isMono && 'font-mono')}>{value}</p>
    </div>
  );
}

function LevelRow({ label, value, color, textColor, bold }: {
  label: string; value: string; color: string; textColor: string; bold?: boolean;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className={cn(
        'w-12 text-center text-[9px] font-bold uppercase py-0.5 rounded text-white',
        color
      )}>
        {label}
      </span>
      <div className="flex-1 h-px bg-border-subtle/40" />
      <span className={cn('text-xs font-mono', textColor, bold && 'font-bold')}>{value}</span>
    </div>
  );
}

function LevelCard({ label, value, color }: { label: string; value: number | null | undefined; color: string }) {
  return (
    <div className="bg-bg-secondary/60 rounded-lg p-2 border border-border-subtle">
      <p className="text-[9px] text-text-muted uppercase font-semibold mb-0.5">{label}</p>
      <p className={cn('text-xs font-bold font-mono truncate', color)}>
        {value != null ? value.toLocaleString('tr-TR', { maximumFractionDigits: 4 }) : '—'}
      </p>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

type TfFilter = 'all' | '1h' | '4h' | '1d';
type DirFilter = 'all' | 'long' | 'short';

export default function SignalsPage() {
  const [signals, setSignals]     = useState<ApiSignal[]>([]);
  const [total, setTotal]         = useState(0);
  const [loading, setLoading]     = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [genMsg, setGenMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [selected, setSelected]   = useState<ApiSignal | null>(null);
  const [tfFilter, setTfFilter]   = useState<TfFilter>('all');
  const [dirFilter, setDirFilter] = useState<DirFilter>('all');
  const [actionableOnly, setActionableOnly] = useState(true);
  const [minQuality, setMinQuality] = useState(5);
  // Aynı sembol için en kaliteli timeframe'i göster, diğerlerini gizle.
  // Kullanıcı her timeframe'i ayrı görmek istiyorsa bunu kapatabilir.
  const [dedupBySymbol, setDedupBySymbol] = useState(true);

  // Timeframe önceliği (büyük TF daha güvenilir): 1d > 4h > 1h > 15m
  const TF_PRIORITY: Record<string, number> = { '1d': 4, '4h': 3, '1h': 2, '15m': 1 };

  // Apply filters → dedup → sort
  const filtered = (() => {
    // 1) TF + minQuality filtreleri
    let arr = signals
      .filter((s) => tfFilter === 'all' || (s.timeframe ?? '').toLowerCase() === tfFilter)
      .filter((s) => qualityScore(s.confidence_score) >= minQuality)
      .filter((s) => dirFilter === 'all' || (dirFilter === 'long' ? s.direction === 'bullish' : s.direction === 'bearish'));

    // 2) Dedup: aynı sembol için en kaliteli (eşitse en büyük TF) tek sinyal
    if (dedupBySymbol) {
      const bestPerSymbol = new Map<string, ApiSignal>();
      for (const s of arr) {
        const sym = (s.asset?.symbol ?? '').toUpperCase();
        if (!sym) continue;
        const existing = bestPerSymbol.get(sym);
        if (!existing) {
          bestPerSymbol.set(sym, s);
          continue;
        }
        // Önce kalite skoruna bak, eşitse timeframe önceliğine
        const a = s.confidence_score, b = existing.confidence_score;
        if (a > b) bestPerSymbol.set(sym, s);
        else if (a === b) {
          const pa = TF_PRIORITY[(s.timeframe ?? '').toLowerCase()] ?? 0;
          const pb = TF_PRIORITY[(existing.timeframe ?? '').toLowerCase()] ?? 0;
          if (pa > pb) bestPerSymbol.set(sym, s);
        }
      }
      arr = Array.from(bestPerSymbol.values());
    }

    // 3) Sıralama: kalite skoru DESC → TF önceliği DESC → sembol ASC
    arr.sort((a, b) => {
      if (b.confidence_score !== a.confidence_score) return b.confidence_score - a.confidence_score;
      const pa = TF_PRIORITY[(a.timeframe ?? '').toLowerCase()] ?? 0;
      const pb = TF_PRIORITY[(b.timeframe ?? '').toLowerCase()] ?? 0;
      if (pb !== pa) return pb - pa;
      return (a.asset?.symbol ?? '').localeCompare(b.asset?.symbol ?? '');
    });

    return arr;
  })();

  // Same-symbol siblings (other TFs) — for showing "+2 TF" hint
  const tfSiblingsBySym = (() => {
    const map = new Map<string, string[]>();
    if (!dedupBySymbol) return map;
    for (const s of signals.filter((x) => qualityScore(x.confidence_score) >= minQuality)) {
      const sym = (s.asset?.symbol ?? '').toUpperCase();
      const tf = (s.timeframe ?? '').toLowerCase();
      if (!sym || !tf) continue;
      const list = map.get(sym) ?? [];
      if (!list.includes(tf)) list.push(tf);
      map.set(sym, list);
    }
    return map;
  })();

  const symbols  = filtered.map((s) => s.asset?.symbol ?? '').filter(Boolean);
  const livePrices = useLivePrices(symbols);

  const load = async (showRefresh = false) => {
    if (showRefresh) setRefreshing(true); else setLoading(true);
    try {
      const res = await fetchActiveSignals({ page_size: 100, only_actionable: actionableOnly });
      setSignals(res.items);
      setTotal(res.total);
    } catch { /**/ } finally {
      setLoading(false); setRefreshing(false);
    }
  };

  const generateAll = async () => {
    setGenerating(true);
    setGenMsg(null);
    try {
      await triggerBatchGeneration();
      setGenMsg({ ok: true, text: 'Tarama başlatıldı. ~5-10 dakika sürer, sonuçlar otomatik düşecek...' });
      const startCount = signals.length;
      for (let i = 0; i < 60; i++) { // up to 5 min polling
        await new Promise((r) => setTimeout(r, 5000));
        const res = await fetchActiveSignals({ page_size: 100, only_actionable: actionableOnly });
        if (res.total > startCount || res.total > 0) {
          setSignals(res.items);
          setTotal(res.total);
          setGenMsg({ ok: true, text: `Tarama devam ediyor — şimdiye kadar ${res.total} sinyal üretildi.` });
        }
      }
      setGenMsg({ ok: true, text: 'Tarama tamamlandı.' });
    } catch (e: any) {
      const msg = e?.message ?? '';
      if (msg.includes('Backend') || msg.includes('Failed to fetch') || msg.includes('NetworkError')) {
        setGenMsg({ ok: false, text: 'Backend çalışmıyor. BAŞLAT.bat dosyasını çift tıklayarak backend\'i aç.' });
      } else if (msg.includes('402') || msg.includes('upgrade_required')) {
        setGenMsg({ ok: false, text: 'Pro veya üzeri abonelik gerekiyor.' });
      } else {
        setGenMsg({ ok: false, text: 'Tarama başlatılamadı: ' + msg });
      }
    } finally {
      setGenerating(false);
      setTimeout(() => setGenMsg(null), 8000);
    }
  };

  useEffect(() => { load(); }, [actionableOnly]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-extrabold text-text-primary flex items-center gap-2">
            <Zap className="w-6 h-6 text-accent-primary" /> Sinyal Merkezi
          </h1>
          <p className="text-sm text-text-secondary mt-1">
            Canlı setup önceliklendiricisi · kurumsal kalite skoru · fiyatlar anlık
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm font-mono text-text-muted">{total} sinyal</span>
          <button
            onClick={generateAll}
            disabled={generating || refreshing}
            className="flex items-center gap-1.5 text-xs font-semibold text-accent-primary hover:text-accent-secondary border border-accent-primary/30 hover:border-accent-primary/60 px-3 py-1.5 rounded-lg transition-all disabled:opacity-50"
          >
            <Zap className={cn('w-3.5 h-3.5', generating && 'animate-pulse')} />
            {generating ? 'Üretiliyor...' : 'Sinyal Üret'}
          </button>
          <button
            onClick={() => load(true)}
            disabled={refreshing || generating}
            className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-primary transition-colors disabled:opacity-50 px-2 py-1.5"
          >
            <RefreshCw className={cn('w-3.5 h-3.5', refreshing && 'animate-spin')} />
          </button>
        </div>
      </div>

      {/* Generation status banner */}
      {genMsg && (
        <div className={cn(
          'flex items-start gap-2 px-4 py-3 rounded-xl border text-sm',
          genMsg.ok
            ? 'bg-bullish/5 border-bullish/30 text-bullish'
            : 'bg-bearish/10 border-bearish/30 text-bearish'
        )}>
          <span className="text-base flex-shrink-0">{genMsg.ok ? '✓' : '✗'}</span>
          <span className="flex-1">{genMsg.text}</span>
        </div>
      )}

      {/* Filters row */}
      <div className="flex items-center gap-3 flex-wrap">

      {/* Timeframe filter */}
      <div className="flex items-center gap-1 p-1 bg-bg-secondary border border-border-subtle rounded-xl w-fit">
        {(['all', '1h', '4h', '1d'] as TfFilter[]).map((tf) => {
          // Count respects the minQuality filter so the badge matches what user sees
          const qualified = signals.filter((s) => qualityScore(s.confidence_score) >= minQuality);
          const cnt = tf === 'all' ? qualified.length : qualified.filter((s) => s.timeframe?.toLowerCase() === tf).length;
          return (
            <button
              key={tf}
              onClick={() => setTfFilter(tf)}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold rounded-lg transition-all',
                tfFilter === tf
                  ? 'bg-accent-primary text-white shadow-glow-sm'
                  : 'text-text-muted hover:text-text-primary'
              )}
            >
              {tf === 'all' ? 'TÜMÜ' : tf.toUpperCase()}
              <span className={cn(
                'text-[10px] font-mono px-1.5 py-0.5 rounded',
                tfFilter === tf ? 'bg-white/20' : 'bg-bg-tertiary/60'
              )}>
                {cnt}
              </span>
            </button>
          );
        })}
      </div>

      {/* Direction filter: AL / SAT */}
      <div className="flex items-center gap-1 p-1 bg-bg-secondary border border-border-subtle rounded-xl w-fit">
        {([
          { id: 'all',   label: 'TÜMÜ' },
          { id: 'long',  label: 'AL' },
          { id: 'short', label: 'SAT' },
        ] as { id: DirFilter; label: string }[]).map((d) => {
          const qualified = signals.filter((s) => qualityScore(s.confidence_score) >= minQuality);
          const cnt = d.id === 'all'
            ? qualified.length
            : qualified.filter((s) => (d.id === 'long' ? s.direction === 'bullish' : s.direction === 'bearish')).length;
          return (
            <button
              key={d.id}
              onClick={() => setDirFilter(d.id)}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold rounded-lg transition-all',
                dirFilter === d.id
                  ? d.id === 'long'
                    ? 'bg-bullish text-white shadow-glow-sm'
                    : d.id === 'short'
                      ? 'bg-bearish text-white shadow-glow-sm'
                      : 'bg-accent-primary text-white shadow-glow-sm'
                  : 'text-text-muted hover:text-text-primary'
              )}
            >
              {d.label}
              <span className={cn(
                'text-[10px] font-mono px-1.5 py-0.5 rounded',
                dirFilter === d.id ? 'bg-white/20' : 'bg-bg-tertiary/60'
              )}>
                {cnt}
              </span>
            </button>
          );
        })}
      </div>

      {/* Actionable-only toggle */}
      <button
        onClick={() => setActionableOnly(!actionableOnly)}
        className={cn(
          'flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-xl border transition-all',
          actionableOnly
            ? 'bg-bullish/15 text-bullish border-bullish/30'
            : 'bg-bg-secondary text-text-muted border-border-subtle hover:text-text-primary'
        )}
        title="Sadece AL/SAT göster (BEKLE sinyallerini gizle)"
      >
        {actionableOnly ? '✓ SADECE AL/SAT' : 'TÜMÜ (BEKLE DAHİL)'}
      </button>

      {/* Min quality slider */}
      <div className="flex items-center gap-2 px-3 py-2 bg-bg-secondary border border-border-subtle rounded-xl">
        <span className="text-[10px] text-text-muted font-bold uppercase">MİN. KALİTE</span>
        <input
          type="range" min={0} max={10} step={1}
          value={minQuality}
          onChange={(e) => setMinQuality(Number(e.target.value))}
          className="w-24 accent-accent-primary cursor-pointer"
        />
        <span className={cn(
          'text-xs font-bold font-mono min-w-[40px] text-center',
          minQuality >= 7 ? 'text-bullish' :
          minQuality >= 5 ? 'text-yellow-400' :
          minQuality >= 3 ? 'text-orange-400' : 'text-text-muted'
        )}>
          {minQuality}/10
        </span>
      </div>
      </div>

      {/* Table */}
      <div className="glass-panel border border-border-subtle rounded-2xl overflow-hidden">
        {/* Table head */}
        <div className="grid grid-cols-[2fr_1fr_1.2fr_1.5fr_1.3fr_1.5fr_auto] gap-4 px-5 py-3 border-b border-border-subtle bg-bg-secondary/30">
          {['SEMBOL · TF', 'YÖN', 'ANLIK FİYAT', 'KALİTE SKORU', 'DURUM', 'ÜRETİLDİ', 'ANALİZ'].map((h) => (
            <span key={h} className="text-[10px] font-bold text-text-muted uppercase tracking-wider">{h}</span>
          ))}
        </div>

        {loading && (
          <div className="flex justify-center py-16">
            <div className="w-7 h-7 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {!loading && signals.length === 0 && (
          <div className="py-16 text-center text-text-muted text-sm">
            Aktif sinyal bulunamadı. &nbsp;
            <button onClick={generateAll} disabled={generating} className="text-accent-primary hover:underline font-semibold">
              {generating ? 'Üretiliyor...' : 'Şimdi üret →'}
            </button>
          </div>
        )}

        <div className="divide-y divide-border-subtle">
          {filtered.map((sig) => {
            const sym    = sig.asset?.symbol ?? '';
            const live   = livePrices[sym];
            const qScore = qualityScore(sig.confidence_score);
            const dir    = directionLabel(sig);
            const up     = (live?.changePct24h ?? 0) >= 0;
            const outcome = sig.outcome ?? 'active';
            const invalid = outcome === 'loss';

            return (
              <div
                key={sig.id}
                className={cn(
                  "grid grid-cols-[2fr_1fr_1.2fr_1.5fr_1.3fr_1.5fr_auto] gap-4 items-center px-5 py-3.5 transition-colors",
                  invalid ? 'bg-bearish/[0.04] opacity-70' : 'hover:bg-white/[0.02]'
                )}
              >
                {/* Symbol + Timeframe */}
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-8 h-8 rounded-lg bg-bg-tertiary border border-border-subtle flex items-center justify-center font-bold font-mono text-xs text-accent-primary flex-shrink-0">
                    {sym.slice(0, 2)}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-bold text-text-primary truncate flex items-center gap-1.5">
                      {sym}
                      <span className="text-[9px] font-bold text-accent-primary bg-accent-primary/10 border border-accent-primary/30 px-1.5 py-0.5 rounded uppercase">
                        {sig.timeframe}
                      </span>
                    </p>
                    <p className="text-[10px] text-text-muted truncate">{sig.asset?.name}</p>
                  </div>
                </div>

                {/* Direction */}
                <div className={invalid ? 'line-through opacity-60' : ''}>
                  <DirectionBadge {...dir} />
                </div>

                {/* Live Price */}
                <div>
                  {live ? (
                    <div>
                      <p className={cn('text-sm font-bold font-mono', invalid ? 'text-text-muted line-through' : 'text-text-primary')}>
                        {live.price.toLocaleString('tr-TR', { maximumFractionDigits: 4 })}
                      </p>
                      <p className={cn('text-[10px] font-mono font-semibold', up ? 'text-bullish' : 'text-bearish')}>
                        {up ? '+' : ''}{live.changePct24h?.toFixed(2)}%
                      </p>
                    </div>
                  ) : (
                    <span className="text-xs text-text-muted animate-pulse">—</span>
                  )}
                </div>

                {/* Quality Score */}
                <div><QualityBar score={qScore} /></div>

                {/* Outcome status */}
                <div>
                  <OutcomeBadge outcome={outcome} />
                </div>

                {/* Generation time (TR saati) */}
                <div className="text-[11px] font-mono text-text-muted">
                  {formatAbsoluteTimeTR(sig.generated_at)}
                </div>

                {/* Action */}
                <div>
                  <button
                    onClick={() => setSelected(sig)}
                    className="flex items-center gap-1 text-[11px] font-semibold text-text-muted hover:text-accent-primary border border-border-subtle hover:border-accent-primary/40 px-2.5 py-1 rounded-lg transition-all"
                  >
                    <Eye className="w-3 h-3" /> Analiz
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Detail Drawer */}
      {selected && <SignalDrawer sig={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
