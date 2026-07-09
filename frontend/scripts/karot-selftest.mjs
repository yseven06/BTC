/**
 * Karot geometri self-test — spec doğrulaması (Bible §05 karot-02..09, v1.4).
 *
 * Repo'da unit-test runner YOK (yalnız puppeteer + node scripts). Bu dosya
 * mevcut `scripts/*.mjs` desenini izler; `node scripts/karot-selftest.mjs`.
 *
 * İki katman:
 *  (1) Golden spec asserts — saf formüllerin (classify/fitilEnd) beklenen
 *      deterministik değerleri (rest-state → consensus/bull, eşik sınırları,
 *      θ=c·34° uç-koordinatı, çarpışma yasası).
 *  (2) Kaynak-drift koruması — src/lib/karot-geometry.ts içindeki dondurulmuş
 *      sabitlerin (karot-15 Geometry Freeze) literal olarak yerinde olması.
 *
 * (1)'deki formüller karot-geometry.ts'in AYNASIDIR (node .ts import edemez);
 * bir gün TS-aware runner eklenirse paylaşımlı import'a taşınabilir.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));

// --- Sabitler (karot-02 · ayna) ---
const W = 96, H = 200, PAD = 20, SPINE_X = 24, L = 32, THETA_MAX_DEG = 34;
const THETA_MAX = (THETA_MAX_DEG * Math.PI) / 180;
const STEP = (H - 2 * PAD) / 8; // 20
const SIGN_BAND = 0.08, ABSMEAN_WEAK = 0.30, CROSS_SPLIT = 2;
const REST_STATE = [0.42, 0.55, 0.38, 0.10, 0.48, 0.22, 0.60, 0.35, 0.18];

const ENGINE_COUNT = 9;
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

function sanitizeConfs(confs) {
  const out = [];
  for (let i = 0; i < ENGINE_COUNT; i++) {
    const v = confs[i];
    out.push(Number.isFinite(v) ? clamp(v, -1, 1) : 0);
  }
  return out;
}

function classify(confs) {
  const signs = confs.map((c) => (c > SIGN_BAND ? 1 : c < -SIGN_BAND ? -1 : 0));
  let cross = 0, prev = 0;
  for (const s of signs) {
    if (s !== 0) { if (prev !== 0 && s !== prev) cross++; prev = s; }
  }
  const n = confs.length || 1;
  const absMean = confs.reduce((a, c) => a + Math.abs(c), 0) / n;
  const mean = confs.reduce((a, c) => a + c, 0) / n;
  const state = absMean < ABSMEAN_WEAK ? 'weak' : cross >= CROSS_SPLIT ? 'split' : 'consensus';
  return { state, dir: mean > 0 ? 'bull' : 'bear', mean, absMean, cross };
}

function fitilEnd(c, y) {
  const th = clamp(c, -1, 1) * THETA_MAX;
  return { x2: SPINE_X + L * Math.cos(th), y2: y - L * Math.sin(th) };
}

// --- Test harness ---
let pass = 0, fail = 0;
const fails = [];
const ok = (name, cond) => { if (cond) pass++; else { fail++; fails.push(name); } };
const near = (a, b, eps = 1e-6) => Math.abs(a - b) < eps;

// (1) Golden spec asserts
const rest = classify(REST_STATE);
ok('rest-state → consensus', rest.state === 'consensus');
ok('rest-state → bull', rest.dir === 'bull');
ok('rest-state cross = 0', rest.cross === 0);
ok('rest-state absMean ≈ 0.36444', near(rest.absMean, 3.28 / 9, 1e-5));
ok('rest-state uzunluk 9', REST_STATE.length === 9);

ok('weak: absMean<0.30 → weak',
  classify([0.1, -0.08, 0.12, -0.05, 0.09, 0.06, -0.1, 0.04, 0.07]).state === 'weak');
ok('split: cross≥2 & absMean≥0.30 → split',
  classify([0.5, 0.3, -0.4, 0.2, -0.5, 0.35, -0.3, 0.25, -0.2]).state === 'split');
ok('consensus-bull düz',
  (() => { const c = classify([0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4]); return c.state === 'consensus' && c.dir === 'bull'; })());
ok('consensus-bear düz',
  (() => { const c = classify([-0.4, -0.4, -0.4, -0.4, -0.4, -0.4, -0.4, -0.4, -0.4]); return c.state === 'consensus' && c.dir === 'bear'; })());
// öncelik: weak, cross≥2 olsa bile absMean<0.30 → weak (split değil)
ok('öncelik weak>split (küçük genlik zikzak)',
  classify([0.1, -0.1, 0.1, -0.1, 0.1, -0.1, 0.1, -0.1, 0.1]).state === 'weak');
// işaret bandı: |c|≤0.08 → 0 (geçiş sayılmaz)
ok('işaret bandı ±0.08 nötr',
  classify([0.5, 0.05, 0.5, 0.05, 0.5, 0.05, 0.5, 0.05, 0.5]).cross === 0);

// fitilEnd geometrisi
const e0 = fitilEnd(0, 100);
ok('fitilEnd(0) yatay: x2=SPINE_X+L', near(e0.x2, SPINE_X + L));
ok('fitilEnd(0) yatay: y2=y', near(e0.y2, 100));
const e1 = fitilEnd(1, 100);
ok('fitilEnd(1) θ=34°: x2', near(e1.x2, SPINE_X + L * Math.cos(THETA_MAX)));
ok('fitilEnd(1) θ=34°: y2 (yukarı=bull)', near(e1.y2, 100 - L * Math.sin(THETA_MAX)) && e1.y2 < 100);
const eN = fitilEnd(-1, 100);
ok('fitilEnd(−1) short: y2 aşağı (>y)', eN.y2 > 100);
ok('fitilEnd clamp: c=2 == c=1', near(fitilEnd(2, 50).y2, fitilEnd(1, 50).y2));

// çarpışma yasası (karot-02)
ok('çarpışma yasası L·sin(θmax)<step', L * Math.sin(THETA_MAX) < STEP);
ok('step = 20', STEP === 20);

// sanitizeConfs — davranış-korur sınır-guard'ı
const arrEq = (a, b) => a.length === b.length && a.every((v, i) => Object.is(v, b[i]));
ok('sanitize: geçerli 9-değer kimlik (davranış-korur)', arrEq(sanitizeConfs(REST_STATE), REST_STATE));
ok('sanitize: NaN/Inf/undef → 0', arrEq(sanitizeConfs([NaN, Infinity, undefined, 0.5, -0.5, 0, 0, 0, 0]), [0, 0, 0, 0.5, -0.5, 0, 0, 0, 0]));
ok('sanitize: aralık-dışı → [−1,1] klamp', arrEq(sanitizeConfs([2, -2, 0.5, 0, 0, 0, 0, 0, 0]), [1, -1, 0.5, 0, 0, 0, 0, 0, 0]));
ok('sanitize: uzunluk<9 → 9 (pad 0)', sanitizeConfs([0.1, 0.2, 0.3]).length === 9);
ok('sanitize: uzunluk>9 → 9 (truncate)', sanitizeConfs(new Array(12).fill(0.5)).length === 9);
ok('sanitize: sözleşme-uyumlu classify aynı hal', classify(sanitizeConfs(REST_STATE)).state === 'consensus');

// --- Adaptör (karot-adapter.ts aynası) — backend engines_data → 9-slot işaretli-güven ---
const DEADZONE = 8, GAIN = 2.5;
const BACKEND_TO_SLOT = {
  technical_analysis: 0, market_structure: 1, smart_money_concepts: 2, candle_range_theory: 3,
  volume_analysis: 4, risk_management: 5, fundamental_analysis: 6, onchain_analysis: 7, macro_analysis: 8,
};
function scoreToSignedConf(score) {
  if (!Number.isFinite(score)) return 0;
  const dev = score - 50;
  if (Math.abs(dev) < DEADZONE) return 0;
  return clamp((dev / 50) * GAIN, -1, 1);
}
function signalToKarotConfs(ed) {
  const confs = new Array(9).fill(0);
  if (!ed || typeof ed !== 'object') return confs;
  const list = Array.isArray(ed) ? ed : Object.values(ed);
  for (const e of list) {
    if (!e || typeof e !== 'object') continue;
    const name = e.engine_name ?? e.name;
    if (name === undefined) continue;
    const slot = BACKEND_TO_SLOT[name];
    if (slot === undefined) continue;
    confs[slot] = scoreToSignedConf(Number(e.score));
  }
  return confs;
}
// birim: scoreToSignedConf
ok('adapter: score 50 → 0 (nötr)', scoreToSignedConf(50) === 0);
ok('adapter: score 57 → 0 (ölü-bölge |7|<8)', scoreToSignedConf(57) === 0);
ok('adapter: score 58 → 0.40 (dev 8, sınır)', near(scoreToSignedConf(58), 0.40));
ok('adapter: score 69.5 → 0.975', near(scoreToSignedConf(69.5), 0.975));
ok('adapter: score 72.5 → 1.0 (clamp)', scoreToSignedConf(72.5) === 1);
ok('adapter: score 35 → −0.75', near(scoreToSignedConf(35), -0.75));
ok('adapter: score 20 → −1.0 (clamp)', scoreToSignedConf(20) === -1);
ok('adapter: NaN → 0', scoreToSignedConf(NaN) === 0);
// birim: signalToKarotConfs eşleme + fallback
ok('adapter: null → 9 sıfır', arrEq(signalToKarotConfs(null), [0,0,0,0,0,0,0,0,0]));
ok('adapter: slot eşleme (yalnız market_structure)',
  arrEq(signalToKarotConfs([{ engine_name: 'market_structure', score: 80 }]), [0, 1, 0, 0, 0, 0, 0, 0, 0]));
ok('adapter: bilinmeyen motor atlanır',
  arrEq(signalToKarotConfs([{ engine_name: 'foo_engine', score: 90 }]), [0,0,0,0,0,0,0,0,0]));
ok('adapter: obje-map biçimi de kabul',
  arrEq(signalToKarotConfs({ a: { engine_name: 'technical_analysis', score: 100 } }), [1,0,0,0,0,0,0,0,0]));
// GOLDEN — gerçek DB sinyalleri (2026-07-10) → adapter → classify zinciri
const SIG_BULL_WEAK = [
  { engine_name: 'technical_analysis', score: 69.5 }, { engine_name: 'market_structure', score: 53.2 },
  { engine_name: 'smart_money_concepts', score: 44.2 }, { engine_name: 'candle_range_theory', score: 57.2 },
  { engine_name: 'volume_analysis', score: 72.5 }, { engine_name: 'risk_management', score: 50 },
  { engine_name: 'fundamental_analysis', score: 57.5 }, { engine_name: 'onchain_analysis', score: 55 },
  { engine_name: 'macro_analysis', score: 50 },
];
const SIG_BULL_CONS = [
  { engine_name: 'technical_analysis', score: 71.6 }, { engine_name: 'market_structure', score: 69.6 },
  { engine_name: 'smart_money_concepts', score: 75 }, { engine_name: 'candle_range_theory', score: 78.8 },
  { engine_name: 'volume_analysis', score: 54.4 }, { engine_name: 'risk_management', score: 50 },
  { engine_name: 'fundamental_analysis', score: 57.5 }, { engine_name: 'onchain_analysis', score: 55 },
  { engine_name: 'macro_analysis', score: 50 },
];
const SIG_BEAR_CONS = [
  { engine_name: 'technical_analysis', score: 30.3 }, { engine_name: 'market_structure', score: 6.1 },
  { engine_name: 'smart_money_concepts', score: 48 }, { engine_name: 'candle_range_theory', score: 21.2 },
  { engine_name: 'volume_analysis', score: 46.7 }, { engine_name: 'risk_management', score: 50 },
  { engine_name: 'fundamental_analysis', score: 57.5 }, { engine_name: 'onchain_analysis', score: 65 },
  { engine_name: 'macro_analysis', score: 50 },
];
ok('golden: düşük-genişlik bull sinyal → weak (dürüst)', classify(signalToKarotConfs(SIG_BULL_WEAK)).state === 'weak');
const gc = classify(signalToKarotConfs(SIG_BULL_CONS));
ok('golden: güçlü bull sinyal → consensus/bull', gc.state === 'consensus' && gc.dir === 'bull');
const gb = classify(signalToKarotConfs(SIG_BEAR_CONS));
ok('golden: güçlü bear sinyal → consensus/bear', gb.state === 'consensus' && gb.dir === 'bear');

// (2) Kaynak-drift koruması — dondurulmuş sabitler karot-geometry.ts'te literal
const src = readFileSync(join(__dirname, '..', 'src', 'lib', 'karot-geometry.ts'), 'utf8');
const frozen = [
  ['W = 96', /export const W = 96\b/],
  ['H = 200', /export const H = 200\b/],
  ['PAD = 20', /export const PAD = 20\b/],
  ['SPINE_X = 24', /export const SPINE_X = 24\b/],
  ['L = 32', /export const L = 32\b/],
  ['THETA_MAX_DEG = 34', /export const THETA_MAX_DEG = 34\b/],
  ['ABSMEAN_WEAK = 0.30', /ABSMEAN_WEAK = 0\.30\b/],
  ['CROSS_SPLIT = 2', /CROSS_SPLIT = 2\b/],
  ['SIGN_BAND = 0.08', /SIGN_BAND = 0\.08\b/],
  ['sanitizeConfs guard mevcut', /export function sanitizeConfs/],
];
for (const [name, re] of frozen) ok(`freeze: ${name}`, re.test(src));
ok('ENGINES 9 motor (Teknik…Makro)', /Teknik'[\s\S]*Makro'/.test(src) && (src.match(/'[^']+',/g) || []).length >= 9);

// Adaptör kaynak-drift: kalibrasyon sabitleri + export mevcut (karot-adapter.ts)
const adapterSrc = readFileSync(join(__dirname, '..', 'src', 'lib', 'karot-adapter.ts'), 'utf8');
ok('adapter-freeze: DEADZONE = 8', /DEADZONE = 8\b/.test(adapterSrc));
ok('adapter-freeze: GAIN = 2.5', /GAIN = 2\.5\b/.test(adapterSrc));
ok('adapter-freeze: signalToKarotConfs export', /export function signalToKarotConfs/.test(adapterSrc));
ok('adapter-freeze: 9-slot backend eşleme (technical→macro)', /technical_analysis: 0[\s\S]*macro_analysis: 8/.test(adapterSrc));

// --- Rapor ---
console.log(`\nKarot self-test: ${pass} geçti, ${fail} kaldı (toplam ${pass + fail})`);
if (fail) {
  console.error('BAŞARISIZ:\n  - ' + fails.join('\n  - '));
  process.exit(1);
}
console.log('✓ Tüm spec assert\'leri geçti (karot-02..09 + Geometry Freeze sabitleri).');
