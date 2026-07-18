'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Eye, TrendingUp, TrendingDown } from 'lucide-react';
import { type ApiSignal } from '@/lib/api';
import { type LivePrice } from '@/hooks/useLivePrices';
import { cn, formatAbsoluteTimeTR, formatPrice, formatPercentage } from '@/lib/utils';
import { PriceSkeleton } from '@/components/ui/PriceSkeleton';
import { LiveStatusBadge } from '@/components/ui/LiveStatusBadge';

// ─── Column template ──────────────────────────────────────────────────────────
// Single source for the 7-column grid so the header and every row stay aligned.
// Mounted by Sinyal Merkezi (Signal Center) — the sole consumer since the Dashboard
// moved to the lighter ActiveSignalGlance bridge (CP-DASH-IA-A). No duplication.
// PI-2a: her track `minmax(<taban>, <fr>)` — <taban> kolonun okunakli-alti cokmesini
// engeller. fr davranisi GENIS ekranda AYNEN korunur (taban baglamaz → byte-ozdes);
// taban yalniz dar viewport'ta baglar → govdedeki overflow-x guard yatay-scroll'a
// dusurur (squeeze/taşma yerine). Tabanlar gercek icerik-genisliginden turetildi.
const GRID_TEMPLATE =
  'minmax(180px,2fr) minmax(92px,1fr) minmax(104px,1.2fr) minmax(150px,1.5fr) minmax(116px,1.3fr) minmax(120px,1.5fr) auto';
const COLUMNS = ['SEMBOL · TF', 'YÖN', 'ANLIK FİYAT', 'KALİTE SKORU', 'DURUM', 'ÜRETİLDİ', 'ANALİZ'] as const;

// ─── Density ──────────────────────────────────────────────────────────────────
// User-controlled row density. Drives the per-row vertical padding via the
// inherited `--row-h` custom property. 'comfortable' = 0.875rem = the historical
// py-3.5 (byte-identical default); 'compact' = 0.5rem for more rows per screen.
export type Density = 'comfortable' | 'compact';
const ROW_H: Record<Density, string> = { comfortable: '0.875rem', compact: '0.5rem' };

// ─── Quality helpers ──────────────────────────────────────────────────────────
export function qualityScore(confidence: number): number {
  return Math.round(confidence / 10);
}

export function qualityColor(score: number): string {
  if (score >= 8) return 'bg-bullish';
  if (score >= 6) return 'bg-amber';
  if (score >= 4) return 'bg-amber/70';
  return 'bg-bearish';
}

export function qualityTextColor(score: number): string {
  if (score >= 8) return 'text-bullish';
  if (score >= 6) return 'text-amber';
  if (score >= 4) return 'text-amber/80';
  return 'text-bearish';
}

export type DirState = 'long' | 'short' | 'wait';
export function directionLabel(sig: ApiSignal): { label: string; state: DirState } {
  const d = (sig.direction ?? '').toLowerCase();
  const t = (sig.signal_type ?? '').toLowerCase();
  if (d === 'bullish' || t === 'buy' || t === 'strong_buy')
    return { label: 'LONG',  state: 'long' };
  if (d === 'bearish' || t === 'sell' || t === 'strong_sell')
    return { label: 'SHORT', state: 'short' };
  return { label: 'BEKLE', state: 'wait' };
}

// ─── Cell primitives ──────────────────────────────────────────────────────────

// M-P1 · Tick Photon (VL v1.5 / K-J) — fiyat hücresinin veri-fotonu.
// Tetik = GÖRÜNÜR değişim (formatlanmış fiyat farkı; ham float'ın görünmez
// basamak oynaması flaş üretmez) + coalesce (hücre-başı ≥2s). Yön = tick yönü.
// Rakam ASLA tween'lenmez, konum oynamaz (::after overlay, z-altı — CSS'te).
// Tek-atım/restart = key-remount (timer yok, animationend'e güven yok).
// Per-hücre bağımsız tetik (ortak zamanlayıcı yasağı). invalid (kayıp) satırda
// foton bastırılır — "SL/kayıpta asla alarm" (sakinlik ciddiyettir).
// Reduce'ta global katman fotonu kapatır; bilgi kaybı yok (rakam anlık +
// yön-renkli 24s yüzdesi kalıcı). İki görünüm (tablo/kart) de BU hücreyi
// kullanır; gizli görünüm display:none olduğundan animasyonu hiç koşmaz.
const FLASH_MIN_GAP_MS = 2000;

export function LivePriceCell({
  live,
  invalid,
  layout,
}: {
  live?: LivePrice;
  invalid: boolean;
  layout: 'stack' | 'inline';
}) {
  const prevRef = useRef<{ display: string; price: number; ts: number } | null>(null);
  const [flash, setFlash] = useState<{ dir: 'up' | 'down'; seq: number }>({ dir: 'up', seq: 0 });

  const price = live?.price;
  useEffect(() => {
    if (price == null) return;
    const display = formatPrice(price);
    const prev = prevRef.current;
    if (prev === null) { prevRef.current = { display, price, ts: 0 }; return; } // ilk değer: olay değil
    if (prev.display === display) return; // görünmez basamak oynaması: foton yok, kayıt değişmez
    const now = Date.now();
    const fire = !invalid && price !== prev.price && now - prev.ts >= FLASH_MIN_GAP_MS;
    const dir: 'up' | 'down' = price > prev.price ? 'up' : 'down';
    prevRef.current = { display, price, ts: fire ? now : prev.ts };
    if (fire) setFlash((f) => ({ dir, seq: f.seq + 1 }));
  }, [price, invalid]);

  if (!live) return <PriceSkeleton />;

  const up = (live.changePct24h ?? 0) >= 0;
  const priceCls = cn('text-sm num font-num-520', invalid ? 'text-text-muted line-through' : 'text-text-primary');
  const pctCls = cn('text-micro font-mono font-medium', up ? 'text-bullish' : 'text-bearish');
  const flashCls = flash.seq > 0 ? (flash.dir === 'up' ? 'price-flash-up' : 'price-flash-down') : '';

  return layout === 'stack' ? (
    <div key={flash.seq} className={flashCls || undefined}>
      <p className={priceCls}>{formatPrice(live.price)}</p>
      <p className={pctCls}>{formatPercentage(live.changePct24h ?? 0)}</p>
    </div>
  ) : (
    // twMerge özel price-flash-* sınıfına dokunmaz; yine de emsal gereği düz birleştirme.
    <div key={flash.seq} className={'flex items-baseline gap-2' + (flashCls ? ' ' + flashCls : '')}>
      <span className={priceCls}>{formatPrice(live.price)}</span>
      <span className={pctCls}>{formatPercentage(live.changePct24h ?? 0)}</span>
    </div>
  );
}

export function QualityBar({ score }: { score: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-1.5 bg-bg-tertiary rounded-full overflow-hidden">
        <div
          className={cn('h-full rounded-full transition-all', qualityColor(score))}
          style={{ width: `${score * 10}%` }}
        />
      </div>
      <span className={cn('text-xs num font-num-520', qualityTextColor(score))}>
        {score}/10
      </span>
    </div>
  );
}

export function OutcomeBadge({ outcome }: { outcome: string }) {
  const config: Record<string, { label: string; cls: string }> = {
    active:    { label: 'AKTİF',     cls: 'bg-accent-primary/15 text-accent-primary border-accent-primary/30' },
    win:       { label: 'KAZANDI ✓', cls: 'bg-bullish/15 text-bullish border-bullish/30' },
    loss:      { label: 'PATLADI ✗', cls: 'bg-bearish/15 text-bearish border-bearish/30' },
    breakeven: { label: 'BERABERE',  cls: 'bg-amber/15 text-amber border-amber/30' },
    expired:   { label: 'GEÇERSİZ',  cls: 'bg-text-muted/15 text-text-muted border-text-muted/30' },
    invalidated: { label: 'İPTAL EDİLDİ', cls: 'bg-accent-ui/15 text-accent-ui border-accent-ui/30' },
  };
  const c = config[outcome] ?? config.active;
  return (
    <span className={cn(
      'inline-flex items-center px-2 py-0.5 rounded text-micro font-medium border',
      c.cls
    )}>
      {c.label}
    </span>
  );
}

export function DirectionBadge({ label, state }: { label: string; state: DirState }) {
  const config = {
    long:  { cls: 'bg-bullish text-black',     icon: <TrendingUp   className="w-3 h-3" /> },
    short: { cls: 'bg-bearish text-white',     icon: <TrendingDown className="w-3 h-3" /> },
    wait:  { cls: 'bg-text-muted/40 text-text-primary border border-text-muted/40', icon: <span className="w-3 h-3 inline-block">⏸</span> },
  } as const;
  const c = config[state];
  return (
    <span className={cn(
      'inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-micro font-medium',
      c.cls
    )}>
      {c.icon}
      {label}
    </span>
  );
}

// ─── Density toggle ───────────────────────────────────────────────────────────
const DENSITY_OPTS: { id: Density; label: string }[] = [
  { id: 'comfortable', label: 'Rahat' },
  { id: 'compact', label: 'Sıkışık' },
];

/**
 * Segmented Rahat/Sıkışık control. Purely a user preference — flips row density
 * instantly (no fetch, no motion). Used by Signal Center's filter bar.
 */
export function DensityToggle({ value, onChange }: { value: Density; onChange: (d: Density) => void }) {
  return (
    <div className="inline-flex items-center gap-0.5 p-0.5 bg-bg-secondary border border-border-subtle rounded-xl">
      {DENSITY_OPTS.map((o) => (
        <button
          key={o.id}
          onClick={() => onChange(o.id)}
          aria-pressed={value === o.id}
          title={o.id === 'compact' ? 'Sıkışık satırlar — ekranda daha çok sinyal' : 'Rahat satırlar'}
          className={cn(
            'px-2.5 py-1 text-micro font-medium rounded-lg transition-colors',
            value === o.id
              ? 'bg-accent-primary text-white'
              : 'text-text-muted hover:text-text-primary'
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// ─── Row ──────────────────────────────────────────────────────────────────────
export function SignalTableRow({
  sig,
  live,
  onSelect,
  selected = false,
}: {
  sig: ApiSignal;
  live?: LivePrice;
  onSelect: (sig: ApiSignal) => void;
  selected?: boolean;
}) {
  const sym     = sig.asset?.symbol ?? '';
  const qScore  = qualityScore(sig.confidence_score);
  const dir     = directionLabel(sig);
  const outcome = sig.outcome ?? 'active';
  const invalid = outcome === 'loss';

  return (
    <div
      className={cn(
        'grid gap-4 items-center px-5 transition-colors',
        invalid ? 'bg-bearish/[0.04] opacity-70'
          : selected ? 'bg-accent-primary/[0.06]'
          : 'hover:bg-e-2'
      )}
      // Kolon sablonu inline (minmax fr-floor, GRID_TEMPLATE tek-kaynak) + dikey padding
      // yogunluk-tabanli (miras --row-h; default py-3.5 ile ozdes).
      style={{ gridTemplateColumns: GRID_TEMPLATE, paddingTop: 'var(--row-h, 0.875rem)', paddingBottom: 'var(--row-h, 0.875rem)' }}
    >
      {/* Symbol + Timeframe */}
      <div className="flex items-center gap-3 min-w-0">
        <div className="w-8 h-8 rounded-lg bg-bg-tertiary border border-border-subtle flex items-center justify-center num font-num-520 text-xs text-accent-primary flex-shrink-0">
          {sym.slice(0, 2)}
        </div>
        <div className="min-w-0">
          <p className="text-sm font-display text-text-primary truncate flex items-center gap-1.5">
            {sym}
            <span className="text-micro font-medium text-accent-primary bg-accent-primary/10 border border-accent-primary/30 px-1.5 py-0.5 rounded uppercase">
              {sig.timeframe}
            </span>
          </p>
          <p className="text-micro text-text-muted truncate">{sig.asset?.name}</p>
        </div>
      </div>

      {/* Direction */}
      <div className={invalid ? 'line-through opacity-60' : ''}>
        <DirectionBadge {...dir} />
      </div>

      {/* Live Price — M-P1: veri-foton hücresi (tek-kaynak LivePriceCell) */}
      <div>
        <LivePriceCell live={live} invalid={invalid} layout="stack" />
      </div>

      {/* Kalite Skoru (CP-KAROT-UI1: satır-içi Karot kaldırıldı — sade bar + sayı) */}
      <div className="flex items-center">
        <QualityBar score={qScore} />
      </div>

      {/* Durum — aktif sinyalde canli yasam-dongusu fazi; kapananlarda sonuc rozeti korunur */}
      <div>
        {outcome === 'active' && sig.live_status ? (
          <LiveStatusBadge
            status={sig.live_status}
            since={sig.live_status_since}
            reason={sig.status_reason}
          />
        ) : (
          <OutcomeBadge outcome={outcome} />
        )}
      </div>

      {/* Generation time (TR saati) */}
      <div className="text-micro font-mono text-text-muted">
        {formatAbsoluteTimeTR(sig.generated_at)}
      </div>

      {/* Action */}
      <div>
        <button
          onClick={() => onSelect(sig)}
          className="flex items-center gap-1 text-micro font-medium text-text-muted hover:text-accent-primary border border-border-subtle hover:border-accent-primary/40 px-2.5 py-1 rounded-lg transition-all"
        >
          <Eye className="w-3 h-3" /> Analiz
        </button>
      </div>
    </div>
  );
}

// ─── Mobile card row (PI-2a) ────────────────────────────────────────────────
// md-alti (Bible §03 "md alti → kart"): AYNI veri + AYNI hucre-primitifleri, yeni
// veri YOK. Gecis CSS-only (md:hidden), animasyonsuz (MO-01 layout-anim yasak).
// Desktop SignalTableRow'a DOKUNULMADI → masaustu byte-ozdes. Analiz butonu touch
// 44px (Bible mobil). Yeni davranis yok: secim yalniz butonda (satir-genelinde tap
// eklenmedi), hover/selected/invalid halleri satir ile birebir ayni.
export function SignalCardRow({
  sig,
  live,
  onSelect,
  selected = false,
}: {
  sig: ApiSignal;
  live?: LivePrice;
  onSelect: (sig: ApiSignal) => void;
  selected?: boolean;
}) {
  const sym     = sig.asset?.symbol ?? '';
  const qScore  = qualityScore(sig.confidence_score);
  const dir     = directionLabel(sig);
  const outcome = sig.outcome ?? 'active';
  const invalid = outcome === 'loss';

  return (
    <div
      className={cn(
        'flex flex-col gap-3 p-4 transition-colors',
        invalid ? 'bg-bearish/[0.04] opacity-70'
          : selected ? 'bg-accent-primary/[0.06]'
          : ''
      )}
    >
      {/* Ust: sembol·TF + yon */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-9 h-9 rounded-lg bg-bg-tertiary border border-border-subtle flex items-center justify-center num font-num-520 text-xs text-accent-primary flex-shrink-0">
            {sym.slice(0, 2)}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-display text-text-primary truncate flex items-center gap-1.5">
              {sym}
              <span className="text-micro font-medium text-accent-primary bg-accent-primary/10 border border-accent-primary/30 px-1.5 py-0.5 rounded uppercase">
                {sig.timeframe}
              </span>
            </p>
            <p className="text-micro text-text-muted truncate">{sig.asset?.name}</p>
          </div>
        </div>
        <div className={cn('flex-shrink-0', invalid && 'line-through opacity-60')}>
          <DirectionBadge {...dir} />
        </div>
      </div>

      {/* Orta: anlik fiyat + konsensus/kalite — M-P1: veri-foton hücresi (tek-kaynak) */}
      <div className="flex items-center justify-between gap-3">
        <div>
          <LivePriceCell live={live} invalid={invalid} layout="inline" />
        </div>
        <div className="flex items-center flex-shrink-0">
          <QualityBar score={qScore} />
        </div>
      </div>

      {/* Alt: durum + uretildi + analiz (touch 44px) */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          {outcome === 'active' && sig.live_status ? (
            <LiveStatusBadge
              status={sig.live_status}
              since={sig.live_status_since}
              reason={sig.status_reason}
            />
          ) : (
            <OutcomeBadge outcome={outcome} />
          )}
          <span className="text-micro font-mono text-text-muted truncate">
            {formatAbsoluteTimeTR(sig.generated_at)}
          </span>
        </div>
        <button
          onClick={() => onSelect(sig)}
          className="flex items-center justify-center gap-1 min-h-[44px] px-3 text-micro font-medium text-text-muted hover:text-accent-primary border border-border-subtle hover:border-accent-primary/40 rounded-lg transition-all flex-shrink-0"
        >
          <Eye className="w-3 h-3" /> Analiz
        </button>
      </div>
    </div>
  );
}

// ─── Table ────────────────────────────────────────────────────────────────────
interface SignalTableProps {
  /** Rows to render (already filtered/sorted by the caller). */
  rows: ApiSignal[];
  /** Live price map keyed by symbol (from useLivePrices). */
  livePrices: Record<string, LivePrice>;
  /** Opens the analysis view for a signal (Signal Center: drawer on mobile, Dock on lg+). */
  onSelect: (sig: ApiSignal) => void;
  /** Show the loading spinner instead of rows. */
  loading?: boolean;
  /** Render `emptyState` (when not loading) — caller decides the empty condition. */
  showEmpty?: boolean;
  /** Page-specific empty state node. */
  emptyState?: React.ReactNode;
  /** Row density; default 'comfortable' renders byte-identically to the legacy table. */
  density?: Density;
  /** Highlight the row whose signal id matches (Signal Center master-detail Dock). */
  selectedId?: string;
}

/**
 * Dense signal table — Signal Center's table (the Dashboard moved to the lighter
 * ActiveSignalGlance bridge in CP-DASH-IA-A). Header + rows share a single column template
 * so they always stay aligned. Presentational only (no motion/glow — Premium).
 */
export function SignalTable({
  rows,
  livePrices,
  onSelect,
  loading = false,
  showEmpty = false,
  emptyState,
  density = 'comfortable',
  selectedId,
}: SignalTableProps) {
  return (
    <div
      className="glass-panel border border-border-subtle rounded-2xl overflow-hidden"
      // --row-h cascades to every row's vertical padding (see SignalTableRow).
      style={{ ['--row-h' as string]: ROW_H[density] } as React.CSSProperties}
    >
      {/* Masaustu (md+): grid tablo + overflow-x guard — dar viewport'ta kolonlar
          minmax-tabana carpinca squeeze/taşma yerine yatay-scroll (kart-sinirinda). */}
      <div className="hidden md:block overflow-x-auto">
        {/* Table head */}
        <div
          className="grid gap-4 px-5 py-3 border-b border-border-subtle bg-bg-secondary/30"
          style={{ gridTemplateColumns: GRID_TEMPLATE }}
        >
          {COLUMNS.map((h) => (
            <span key={h} className="text-micro font-medium text-text-muted uppercase">{h}</span>
          ))}
        </div>

        {!loading && !showEmpty && (
          <div className="divide-y divide-border-subtle">
            {rows.map((sig) => (
              <SignalTableRow
                key={sig.id}
                sig={sig}
                live={livePrices[sig.asset?.symbol ?? '']}
                onSelect={onSelect}
                selected={selectedId ? sig.id === selectedId : false}
              />
            ))}
          </div>
        )}
      </div>

      {loading && (
        // Liste-fetch loading (CP-KAROT-UI1: boş-Karot kaldırıldı). Nötr sade
        // dark-terminal loading dili — glyph/spinner/süs YOK; sabit metin
        // (idle-sessiz, MO-06 uyumlu; layout kaymaz). Her iki viewport.
        <div className="py-16 text-center text-sm text-text-muted">
          Sinyaller yükleniyor…
        </div>
      )}

      {!loading && showEmpty && emptyState}

      {/* Mobil (md-alti): kart-liste — ayni veri/primitifler, CSS-only, animasyonsuz. */}
      {!loading && !showEmpty && (
        <div className="md:hidden divide-y divide-border-subtle">
          {rows.map((sig) => (
            <SignalCardRow
              key={sig.id}
              sig={sig}
              live={livePrices[sig.asset?.symbol ?? '']}
              onSelect={onSelect}
              selected={selectedId ? sig.id === selectedId : false}
            />
          ))}
        </div>
      )}
    </div>
  );
}
