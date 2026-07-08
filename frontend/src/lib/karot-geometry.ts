/**
 * Karot geometri — saf matematik (React/DOM YOK) · tek-kaynak (Bible §05 karot-02..09, v1.4).
 *
 * "K17 görünüm + K02 matematik": dikey omurga + slot'a mıhlı açısal kanıt-fitilleri
 * + karar-ucu. Fitil boyu SABİT (L) → güven yalnız AÇIYA kodlanır (tek-değişkenli
 * dürüst okuma, Lie Factor 1). classify eşikleri karot-03 ile birebir.
 *
 * Bu modül saf ve deterministiktir; `Karot.tsx` (render) ve
 * `scripts/karot-selftest.mjs` (spec doğrulaması) buradan türer.
 * Renk/token YOK — renk kararı karot-05/07'ye göre bileşen katmanında verilir.
 */

// --- Sabitler (karot-02 · TEK KAYNAK · karot-15 Geometry Freeze ile dondurulmuş) ---
export const W = 96;
export const H = 200;
export const PAD = 20;
export const SPINE_X = 24;
export const L = 32; // fitil boyu — SABİT
export const THETA_MAX_DEG = 34;
export const THETA_MAX = (THETA_MAX_DEG * Math.PI) / 180;
export const ENGINE_COUNT = 9;
export const STEP = (H - 2 * PAD) / (ENGINE_COUNT - 1); // = 20
export const TIP_LEN = 18;
export const SPINE_TOP = PAD - 8; // 12
export const SPINE_BOTTOM = H - PAD + 4; // 184

// Çarpışma yasası (karot-02): dönüş süpürmesinde fitiller çarpışmaz.
export const COLLISION_SAFE = L * Math.sin(THETA_MAX) < STEP; // 17.9 < 20 → true

// 9 motor sabit dikey sıra (karot-04). Sıra ASLA değişmez (spatial memory).
export const ENGINES = [
  'Teknik', 'Piyasa Yapısı', 'SMC', 'CRT', 'Hacim', 'Risk', 'Temel', 'On-Chain', 'Makro',
] as const;

// Kanonik rest-state dizisi (karot-09) → Uzlaşma/bull. favicon/loader/logo tek kaynağı.
export const REST_STATE: readonly number[] = [
  0.42, 0.55, 0.38, 0.10, 0.48, 0.22, 0.60, 0.35, 0.18,
];

// classify eşikleri (karot-03) — TEK KAYNAK.
export const SIGN_BAND = 0.08;
export const ABSMEAN_WEAK = 0.30;
export const CROSS_SPLIT = 2;

export type KarotState = 'consensus' | 'split' | 'weak';
export type KarotDir = 'bull' | 'bear';

export interface KarotClassification {
  state: KarotState;
  dir: KarotDir;
  mean: number;
  absMean: number;
  cross: number;
}

const clamp = (v: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, v));

/**
 * Hal-sınıflandırma (karot-03). Öncelik ZORUNLU: weak → split → consensus.
 * Eksen-geçiş sayısı işaret dizisinden hesaplanır — projeksiyondan bağımsız.
 */
export function classify(confs: readonly number[]): KarotClassification {
  const signs = confs.map((c) => (c > SIGN_BAND ? 1 : c < -SIGN_BAND ? -1 : 0));
  let cross = 0;
  let prev = 0;
  for (const s of signs) {
    if (s !== 0) {
      if (prev !== 0 && s !== prev) cross++;
      prev = s;
    }
  }
  const n = confs.length || 1;
  const absMean = confs.reduce((a, c) => a + Math.abs(c), 0) / n;
  const mean = confs.reduce((a, c) => a + c, 0) / n;
  const state: KarotState =
    absMean < ABSMEAN_WEAK ? 'weak' : cross >= CROSS_SPLIT ? 'split' : 'consensus';
  return { state, dir: mean > 0 ? 'bull' : 'bear', mean, absMean, cross };
}

export interface Fitil {
  i: number;
  y: number; // slot taban y (omurga üzerinde)
  c: number; // işaretli güven (clamped)
  x2: number; // uç x
  y2: number; // uç y
}

/** Tek fitil ucu: taban (SPINE_X, y), açı θ=c·θmax, boy L sabit. */
export function fitilEnd(c: number, y: number): { x2: number; y2: number } {
  const th = clamp(c, -1, 1) * THETA_MAX;
  return { x2: SPINE_X + L * Math.cos(th), y2: y - L * Math.sin(th) };
}

/** 9 slot fitili (tam ölçek). */
export function fitiller(confs: readonly number[]): Fitil[] {
  return confs.map((c, i) => {
    const y = PAD + i * STEP;
    const { x2, y2 } = fitilEnd(c, y);
    return { i, y, c: clamp(c, -1, 1), x2, y2 };
  });
}

/**
 * 16px silüet için 3 küme-fitil (karot-08): ardışık üçlü ortalaması.
 * DİKKAT: hal/tint DAİMA 9'lu classify'dan gelir (ölçek-değişmezlik) —
 * bu yalnız GÖRÜNÜR fitil sayısını 3'e indirir.
 */
export function clusterFitiller(confs: readonly number[]): Fitil[] {
  const groups = [confs.slice(0, 3), confs.slice(3, 6), confs.slice(6, 9)];
  const clusterStep = (H - 2 * PAD) / 2; // 3 slot: y = 20, 100, 180
  return groups.map((g, i) => {
    const c = g.length ? g.reduce((a, v) => a + v, 0) / g.length : 0;
    const y = PAD + i * clusterStep;
    const { x2, y2 } = fitilEnd(c, y);
    return { i, y, c: clamp(c, -1, 1), x2, y2 };
  });
}

/** Karar-ucu (yalnız Uzlaşma): taban omurga tepesi, açı=mean, boy TIP_LEN. */
export function decisionTip(mean: number): { x1: number; y1: number; x2: number; y2: number } {
  const th = clamp(mean, -1, 1) * THETA_MAX;
  return {
    x1: SPINE_X,
    y1: SPINE_TOP,
    x2: SPINE_X + TIP_LEN * Math.cos(th),
    y2: SPINE_TOP - TIP_LEN * Math.sin(th),
  };
}

/** Tint-zarfı polygon path (karot-05): omurga → fitil-uçları → omurga, slot sırasında. */
export function envelopePath(slots: Fitil[]): string {
  if (!slots.length) return '';
  const first = slots[0];
  const last = slots[slots.length - 1];
  const pts = slots.map((s) => `L ${s.x2.toFixed(2)} ${s.y2.toFixed(2)}`).join(' ');
  return `M ${SPINE_X} ${first.y} ${pts} L ${SPINE_X} ${last.y} Z`;
}
