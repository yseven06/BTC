/**
 * Karot adaptörü — backend `engines_data` → Karot 9-slot işaretli-güven ∈[−1,1].
 *
 * Karot primitifi (karot-geometry.ts) motor-başına işaretli-güven bekler; backend
 * her motoru `{engine_name, score 0-100, confidence 0-100, bias}` olarak verir.
 * Bu modül ikisini köprüler. SAF/deterministik (React/DOM yok).
 *
 * KALİBRASYON (1726 gerçek sinyal analizi · 2026-07-10):
 *  - Ham `((score−50)/50)·(conf/100)` formülü sinyallerin %99.9'unu "kararsız"
 *    gösteriyordu (motorların ~yarısı yapısal-nötr → absMean frozen 0.30 eşiğinin
 *    altında). classify() eşikleri karot-15 ile DONMUŞ → yalnız adaptör ayarlandı.
 *  - `confidence` düşürüldü (tekdüze yüksek → ayrıştırıcı değil, weak'e itiyor).
 *  - **Ölü-bölge (DEADZONE):** |score−50| < 8 → 0. Placeholder/near-neutral
 *    motorları (macro=50, fundamental=57.5, risk=50…) sıfırlar → YAPAY bölünme
 *    (cross) kalkar; yalnız gerçek pozisyon alan motorlar kalır (daha dürüst).
 *  - **Kazanç (GAIN):** 2.5 → yönlü motorlara anlamlı büyüklük.
 *  Sonuç dağılımı (1725 sinyal): consensus %38 · split %33 · weak %29 ·
 *  consensus yön-doğruluğu %99.8. DEADZONE/GAIN ürün-hissine göre ayarlanabilir.
 */

import { ENGINE_COUNT } from './karot-geometry';

/** Backend `engine_name` → Karot slot indeksi (karot-04 sabit sıra Teknik→Makro). */
export const BACKEND_TO_SLOT: Readonly<Record<string, number>> = {
  technical_analysis: 0,
  market_structure: 1,
  smart_money_concepts: 2,
  candle_range_theory: 3,
  volume_analysis: 4,
  risk_management: 5,
  fundamental_analysis: 6,
  onchain_analysis: 7,
  macro_analysis: 8,
};

// Kalibrasyon sabitleri (ayarlanabilir; classify() eşikleri DONMUŞ, bunlar değil).
export const DEADZONE = 8; // |score−50| < 8 → nötr (yapısal-nötr motorları sıfırla)
export const GAIN = 2.5; // yönlü sapmaya kazanç

const clamp = (v: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, v));

/**
 * Tek motor skoru (0-100) → işaretli-güven ∈[−1,1].
 * 50 = nötr; >50 bull (+), <50 bear (−). Ölü-bölge içi → 0. Gain + clamp.
 * Not: DEADZONE·GAIN/50 = 0.40 olduğundan sıfır-olmayan çıktı daima ≥0.40 →
 * classify işaret-bandını (±0.08) hiç bölmez (deterministik hal).
 */
export function scoreToSignedConf(score: number): number {
  if (!Number.isFinite(score)) return 0;
  const dev = score - 50;
  if (Math.abs(dev) < DEADZONE) return 0;
  return clamp((dev / 50) * GAIN, -1, 1);
}

/**
 * Bir sinyalin `engines_data`'sını → 9-slot işaretli-güven dizisine çevirir.
 * Dizi (kanonik) veya obje-map kabul eder; null/eksik/bilinmeyen-motor zarifçe 0.
 * Çıktı daima uzunluk 9, ∈[−1,1]; bileşen ayrıca sanitizeConfs ile korunur.
 */
export function signalToKarotConfs(enginesData: unknown): number[] {
  const confs = new Array<number>(ENGINE_COUNT).fill(0);
  if (!enginesData || typeof enginesData !== 'object') return confs;
  const list: unknown[] = Array.isArray(enginesData)
    ? enginesData
    : Object.values(enginesData as Record<string, unknown>);
  for (const e of list) {
    if (!e || typeof e !== 'object') continue;
    const rec = e as Record<string, unknown>;
    const name = (rec.engine_name ?? rec.name) as string | undefined;
    if (name === undefined) continue;
    const slot = BACKEND_TO_SLOT[name];
    if (slot === undefined) continue;
    confs[slot] = scoreToSignedConf(Number(rec.score));
  }
  return confs;
}
