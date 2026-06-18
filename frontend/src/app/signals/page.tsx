'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { Zap, RefreshCw, TrendingUp, TrendingDown, Eye, LineChart, FileDown } from 'lucide-react';
import { fetchActiveSignals, triggerBatchGeneration, downloadSignalPdf, type ApiSignal } from '@/lib/api';
import { useLivePrices } from '@/hooks/useLivePrices';
import { SignalType } from '@/types';
import { cn } from '@/lib/utils';

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
  if (b.includes('strong_bullish'))  return { color: 'text-bullish',   label: 'Güçlü Alım', ring: 'bg-bullish' };
  if (b.includes('bullish'))         return { color: 'text-bullish',   label: 'Alım',       ring: 'bg-bullish/70' };
  if (b.includes('strong_bearish'))  return { color: 'text-bearish',   label: 'Güçlü Satım',ring: 'bg-bearish' };
  if (b.includes('bearish'))         return { color: 'text-bearish',   label: 'Satım',      ring: 'bg-bearish/70' };
  return { color: 'text-text-muted', label: 'Nötr', ring: 'bg-text-muted/70' };
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
                            <span className="text-text-muted flex-shrink-0">·</span> {f}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {tab === 'explanation' && (() => {
            const parsed = parseExplanation(sig.explanation_tr);
            const hasAny = parsed.summary || parsed.marketStructure.trend || parsed.volumeProfile.exhaustion || parsed.smcCrt.zone || parsed.riskPlan.level;
            if (!hasAny) {
              return (
                <div className="text-xs text-text-muted bg-bg-secondary/40 rounded-xl p-4 border border-border-subtle text-center">
                  AI açıklaması mevcut değil.
                </div>
              );
            }
            return (
              <div className="space-y-3">

                {/* 1. Özet */}
                {parsed.summary && (
                  <div className="bg-accent-primary/5 border border-accent-primary/20 rounded-xl p-3">
                    <p className="text-[10px] text-accent-primary uppercase font-bold tracking-wider mb-1.5">📋 Özet</p>
                    <p className="text-xs text-text-primary leading-relaxed">{parsed.summary}</p>
                  </div>
                )}

                {/* 2. Piyasa Yapısı */}
                {(parsed.marketStructure.trend || parsed.marketStructure.support) && (
                  <div className="bg-bg-secondary/40 border border-border-subtle rounded-xl p-3 space-y-2">
                    <p className="text-[10px] text-text-muted uppercase font-bold tracking-wider">📊 Piyasa Yapısı</p>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      {parsed.marketStructure.trend && (
                        <InfoCell label="Trend" value={parsed.marketStructure.trend}
                          accent={parsed.marketStructure.trend.toLowerCase().includes('düşüş') || parsed.marketStructure.trend.toLowerCase().includes('downtrend') ? 'text-bearish' :
                                  parsed.marketStructure.trend.toLowerCase().includes('yükseliş') || parsed.marketStructure.trend.toLowerCase().includes('uptrend') ? 'text-bullish' : 'text-text-primary'} />
                      )}
                      {parsed.marketStructure.swing && (
                        <InfoCell label="Swing" value={parsed.marketStructure.swing} accent="text-text-primary mono" />
                      )}
                      {parsed.marketStructure.support && (
                        <InfoCell label="Destek" value={parsed.marketStructure.support} accent="text-bullish mono" />
                      )}
                      {parsed.marketStructure.resistance && (
                        <InfoCell label="Direnç" value={parsed.marketStructure.resistance} accent="text-bearish mono" />
                      )}
                    </div>
                  </div>
                )}

                {/* 3. Hacim Profili */}
                {(parsed.volumeProfile.exhaustion || parsed.volumeProfile.poc) && (
                  <div className="bg-bg-secondary/40 border border-border-subtle rounded-xl p-3 space-y-2">
                    <p className="text-[10px] text-text-muted uppercase font-bold tracking-wider">📈 Hacim Profili</p>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      {parsed.volumeProfile.exhaustion && (
                        <InfoCell label="Durum" value={parsed.volumeProfile.exhaustion}
                          accent={parsed.volumeProfile.exhaustion.toLowerCase().includes('bullish') ? 'text-bullish' :
                                  parsed.volumeProfile.exhaustion.toLowerCase().includes('bearish') ? 'text-bearish' : 'text-text-primary'} />
                      )}
                      {parsed.volumeProfile.volumeRatio && (
                        <InfoCell label="Hacim Oranı" value={parsed.volumeProfile.volumeRatio} accent="text-accent-primary mono" />
                      )}
                      {parsed.volumeProfile.poc && (
                        <InfoCell label="POC" value={parsed.volumeProfile.poc} accent="text-text-primary mono" />
                      )}
                      {parsed.volumeProfile.phase && (
                        <InfoCell label="Faz" value={parsed.volumeProfile.phase}
                          accent={parsed.volumeProfile.phase.toLowerCase().includes('accumulation') ? 'text-bullish' : 'text-bearish'} />
                      )}
                    </div>
                  </div>
                )}

                {/* 4. SMC + CRT */}
                {(parsed.smcCrt.zone || parsed.smcCrt.sweeps || parsed.smcCrt.fvg) && (
                  <div className="bg-purple-500/5 border border-purple-500/20 rounded-xl p-3 space-y-2">
                    <p className="text-[10px] text-purple-400 uppercase font-bold tracking-wider">🧠 Smart Money & CRT</p>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      {parsed.smcCrt.zone && (
                        <InfoCell label="Değer Bölgesi" value={parsed.smcCrt.zone}
                          accent={parsed.smcCrt.zone.toLowerCase().includes('discount') || parsed.smcCrt.zone.toLowerCase().includes('iskonto') ? 'text-bullish' : 'text-bearish'} />
                      )}
                      {parsed.smcCrt.sweeps && (
                        <InfoCell label="Likidite Süpürme" value={parsed.smcCrt.sweeps} accent="text-purple-400" />
                      )}
                      {parsed.smcCrt.range && (
                        <InfoCell label="Range Durumu" value={parsed.smcCrt.range} accent="text-text-primary" />
                      )}
                      {parsed.smcCrt.fvg && (
                        <InfoCell label="FVG" value={parsed.smcCrt.fvg}
                          accent={parsed.smcCrt.fvg.toLowerCase().includes('bullish') ? 'text-bullish' : 'text-bearish'} />
                      )}
                    </div>
                  </div>
                )}

                {/* 5. Risk & İşlem Planı */}
                {(parsed.riskPlan.entry || parsed.riskPlan.sl) && (
                  <div className="bg-orange-500/5 border border-orange-500/20 rounded-xl p-3 space-y-2">
                    <p className="text-[10px] text-orange-400 uppercase font-bold tracking-wider">⚠️ Risk & İşlem Planı</p>

                    {/* Risk + position size summary row */}
                    <div className="flex items-center justify-between bg-bg-tertiary/40 rounded-lg p-2">
                      {parsed.riskPlan.level && (
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-text-muted">RİSK</span>
                          <span className={cn('text-xs font-bold',
                            parsed.riskPlan.level === 'VERY_HIGH' ? 'text-bearish' :
                            parsed.riskPlan.level === 'HIGH' ? 'text-orange-400' :
                            parsed.riskPlan.level === 'MEDIUM' ? 'text-yellow-400' :
                            'text-bullish')}>
                            {parsed.riskPlan.level.replace('_', ' ')}
                          </span>
                        </div>
                      )}
                      {parsed.riskPlan.positionSize && (
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-text-muted">POZİSYON</span>
                          <span className="text-xs font-bold font-mono text-accent-primary">{parsed.riskPlan.positionSize}</span>
                          <span className="text-[10px] text-text-muted">portföy</span>
                        </div>
                      )}
                    </div>

                    {/* Trade levels — visual ladder */}
                    <div className="space-y-1.5">
                      {parsed.riskPlan.tp3 && <LevelRow label="TP3" value={parsed.riskPlan.tp3} color="bg-bullish" textColor="text-bullish" />}
                      {parsed.riskPlan.tp2 && <LevelRow label="TP2" value={parsed.riskPlan.tp2} color="bg-bullish/70" textColor="text-bullish" />}
                      {parsed.riskPlan.tp1 && <LevelRow label="TP1" value={parsed.riskPlan.tp1} color="bg-bullish/50" textColor="text-bullish" />}
                      {parsed.riskPlan.entry && <LevelRow label="GİRİŞ" value={parsed.riskPlan.entry} color="bg-accent-primary" textColor="text-accent-primary" bold />}
                      {parsed.riskPlan.sl && <LevelRow label="STOP" value={parsed.riskPlan.sl} color="bg-bearish" textColor="text-bearish" />}
                    </div>
                  </div>
                )}

                {/* 6. Geçersizlik */}
                {parsed.invalidation && (
                  <div className="bg-yellow-500/5 border border-yellow-500/20 rounded-xl p-3">
                    <p className="text-[10px] text-yellow-400 uppercase font-bold tracking-wider mb-1.5">⛔ Geçersizlik Koşulu</p>
                    <p className="text-[11px] text-text-secondary leading-relaxed">{parsed.invalidation}</p>
                  </div>
                )}
              </div>
            );
          })()}
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

export default function SignalsPage() {
  const [signals, setSignals]     = useState<ApiSignal[]>([]);
  const [total, setTotal]         = useState(0);
  const [loading, setLoading]     = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [selected, setSelected]   = useState<ApiSignal | null>(null);
  const [tfFilter, setTfFilter]   = useState<TfFilter>('all');
  const [actionableOnly, setActionableOnly] = useState(false);

  const filtered = tfFilter === 'all' ? signals : signals.filter((s) => (s.timeframe ?? '').toLowerCase() === tfFilter);
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
    try {
      await triggerBatchGeneration();
      for (let i = 0; i < 24; i++) {
        await new Promise((r) => setTimeout(r, 5000));
        const res = await fetchActiveSignals({ page_size: 100 });
        if (res.total > 0) { setSignals(res.items); setTotal(res.total); break; }
      }
    } catch { /**/ } finally { setGenerating(false); }
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

      {/* Filters row */}
      <div className="flex items-center gap-3 flex-wrap">

      {/* Timeframe filter */}
      <div className="flex items-center gap-1 p-1 bg-bg-secondary border border-border-subtle rounded-xl w-fit">
        {(['all', '1h', '4h', '1d'] as TfFilter[]).map((tf) => {
          const cnt = tf === 'all' ? signals.length : signals.filter((s) => s.timeframe?.toLowerCase() === tf).length;
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
      </div>

      {/* Table */}
      <div className="glass-panel border border-border-subtle rounded-2xl overflow-hidden">
        {/* Table head */}
        <div className="grid grid-cols-[2fr_1fr_1.2fr_1.5fr_1.3fr_1.5fr_auto] gap-4 px-5 py-3 border-b border-border-subtle bg-bg-secondary/30">
          {['SEMBOL · TF', 'YÖN', 'ANLIK FİYAT', 'KALİTE SKORU', 'DURUM', 'HTF / PURGE', 'ANALİZ'].map((h) => (
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
            const htf    = getHtfAlignment(sig.engines_data);
            const purge  = getPurgeType(sig.engines_data);
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

                {/* HTF + Purge stacked */}
                <div className="flex flex-col gap-1">
                  <HtfBadge {...htf} />
                  {purge && <PurgeBadge {...purge} />}
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
