import React from 'react';
import { clsx } from 'clsx';
import {
  W, H, PAD, SPINE_X, STEP, SPINE_TOP, SPINE_BOTTOM,
  classify, fitiller, clusterFitiller, decisionTip, envelopePath,
  type Fitil,
} from '@/lib/karot-geometry';

/**
 * Karot — konsensüs enstrümanı (statik primitif · Bible §05 v1.4).
 *
 * "K17 görünüm + K02 matematik": dikey cyan omurga + slot'a mıhlı açısal
 * kanıt-fitilleri (slate) + karar-ucu (cyan). Renk KAZANILIR — yön tinti
 * yalnız Uzlaşma'da gövdeye dolar (fill-opacity .14). Cyan yalnız omurga+
 * karar-ucu (kanıt=slate; micro-cyan bütçesi). Radyussuz, tel-malzeme.
 *
 * Saf/deterministik (karot-06 tek render): hook/`use client` yok, SSR-güvenli.
 * Tüm ölçekler tek fonksiyondan (16 silüet=3 küme-fitil · 48 kart · 200 hero).
 * Motion/hover-lümen/glow-blur = serbest katman (karot-15), burada statik.
 */

export interface KarotProps {
  /** 9 motor işaretli-güven dizisi ∈[−1,1] (Teknik→Makro sırası, karot-04). */
  confs: readonly number[];
  /** Piksel yükseklik (en/boy 96:200 korunur). <32 → 3-küme silüet. Default 48. */
  size?: number;
  /** Vurgulanan slot indeksi (+1 lümen) — AI-Thought çapraz-vurgu. */
  highlight?: number;
  /** Boş-Karot skeleton: 9 fitil yatay-nötr (θ=0), tx3 (karot-13). */
  loading?: boolean;
  className?: string;
  /** Erişilebilir başlık (role=img). */
  title?: string;
}

const ZEROS: readonly number[] = Object.freeze(new Array(9).fill(0));

export const Karot: React.FC<KarotProps> = ({
  confs,
  size = 48,
  highlight = -1,
  loading = false,
  className,
  title,
}) => {
  const silhouette = size < 32;
  const showGlow = size >= 40;
  const showGuides = size >= 160;
  const vbPerPx = H / size; // non-scaling stroke için piksel↔viewBox köprüsü
  const dotR = 2 * vbPerPx;

  const data = loading ? ZEROS : confs;
  const cl = classify(data);
  // loading DAİMA kararsız-görünüm (θ=0, tx3); classify hal'i loading'de bastırılır.
  const state = loading ? 'weak' : cl.state;

  const slots: Fitil[] = silhouette ? clusterFitiller(data) : fitiller(data);

  // Renk modeli (karot-05/07 · cyan-bütçe): fitil=slate kanıt, omurga+karar-ucu=cyan.
  const spineColor = state === 'weak' ? 'var(--tx3)' : 'var(--cyan)';
  const fitilBase = state === 'weak' ? 'var(--tx3)' : 'var(--tx2)';
  const strokeW = state === 'weak' ? 1.3 : silhouette ? 1.6 : 1.9;
  const tintColor = cl.dir === 'bull' ? 'var(--bull)' : 'var(--bear)';

  const ns = 'non-scaling-stroke';

  return (
    <svg
      className={clsx('karot', className)}
      data-instrument="karot"
      data-state={loading ? 'loading' : state}
      width={(size * W) / H}
      height={size}
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={title ?? 'Konsensüs enstrümanı'}
      style={{ display: 'block', overflow: 'visible' }}
    >
      {title ? <title>{title}</title> : null}

      {/* slot-kılavuzları (yalnız 200-ölçek) — nötr çentik SPINE_X→+8 */}
      {showGuides && !silhouette
        ? slots.map((s) => (
            <line
              key={`g${s.i}`}
              x1={SPINE_X}
              y1={s.y}
              x2={SPINE_X + 8}
              y2={s.y}
              stroke="var(--hl12)"
              strokeWidth={1}
              vectorEffect={ns}
            />
          ))
        : null}

      {/* tint-zarfı (yalnız Uzlaşma) — omurga→fitil-uçları, karşıt fitil boğumlar */}
      {state === 'consensus' ? (
        <path d={envelopePath(slots)} fill={tintColor} fillOpacity={0.14} stroke="none" />
      ) : null}

      {/* kanıt-fitilleri (slate; highlight → +1 lümen) */}
      {slots.map((s) => {
        const on = s.i === highlight && !silhouette;
        return (
          <line
            key={`f${s.i}`}
            x1={SPINE_X}
            y1={s.y}
            x2={s.x2}
            y2={s.y2}
            stroke={on ? 'var(--tx)' : fitilBase}
            strokeWidth={on ? strokeW + 0.4 : strokeW}
            strokeOpacity={state === 'weak' ? 0.6 : on ? 1 : 0.82}
            strokeLinecap="round"
            vectorEffect={ns}
          />
        );
      })}

      {/* glow-underlay: cyan omurga+karar-ucu'nun AYNI-çizgi ışık-genişletmesi
          (yalnız Uzlaşma & size≥40; blur = serbest Material-katman, burada yok) */}
      {showGlow && state === 'consensus' ? (
        <line
          x1={SPINE_X}
          y1={SPINE_TOP}
          x2={SPINE_X}
          y2={SPINE_BOTTOM}
          stroke="var(--cyan)"
          strokeWidth={3.4}
          strokeOpacity={0.12}
          strokeLinecap="round"
          vectorEffect={ns}
        />
      ) : null}

      {/* omurga — düz dikey; consensus/split cyan, weak tx3 */}
      <line
        x1={SPINE_X}
        y1={SPINE_TOP}
        x2={SPINE_X}
        y2={SPINE_BOTTOM}
        stroke={spineColor}
        strokeWidth={strokeW}
        strokeLinecap="round"
        vectorEffect={ns}
      />

      {/* karar-ucu — yalnız Uzlaşma, en son çizilir (AI en son konuşur) */}
      {state === 'consensus' && !silhouette
        ? (() => {
            const t = decisionTip(cl.mean);
            return (
              <>
                <line
                  x1={t.x1}
                  y1={t.y1}
                  x2={t.x2}
                  y2={t.y2}
                  stroke="var(--cyan)"
                  strokeWidth={2.2}
                  strokeLinecap="round"
                  vectorEffect={ns}
                />
                <circle cx={t.x2} cy={t.y2} r={dotR} fill="var(--cyan)" />
              </>
            );
          })()
        : null}

      {/* bölünmüş imzası — eksen-üstü çift-nokta (cyan), yalnız tam ölçek */}
      {state === 'split' && !silhouette ? (
        <>
          <circle cx={SPINE_X - 4} cy={SPINE_TOP - 2} r={dotR} fill="var(--cyan)" />
          <circle cx={SPINE_X + 4} cy={SPINE_TOP - 2} r={dotR} fill="var(--cyan)" />
        </>
      ) : null}
    </svg>
  );
};

export default Karot;
