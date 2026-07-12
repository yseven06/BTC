#!/usr/bin/env node
/**
 * TradeMinds Motion Self-Test (PI-0b · Premium-motion guardrail hardening)
 *
 * Motion ALTYAPISINI makine-doğrulanabilir kilitler — davranış DEĞİŞTİRMEZ,
 * yalnız mevcut durumun Design Bible v1.4 / Visual Language v1.4'e uyumunu
 * assert eder (karot-selftest.mjs muadili). Drift olursa (token değeri değişir,
 * reduced-motion katmanı düşer, keyframe layout animasyonlar, gate seti token'dan
 * ayrışır) bu test kırar.
 *
 * KAPSAM (yalnız uyumlu-olan-kilitlenir):
 *   1. Süre token seti + --ease-signal = VL §09 kanonik değerler (600ms tavan).
 *   2. gate-5 ALLOWED_MS = token ms kümesi (guardrail↔token tutarlılığı).
 *   3. reduced-motion 3-katman (global 0.01ms + button/link + route-cycle) + scroll auto.
 *   4. @keyframes yalnız transform/opacity (MO-01 layout-anim yasağı) — globals + tailwind.
 *   5. tailwind köprüsü token-bağlı (transitionDuration + timingFunction.signal).
 *
 * KAPSAM-DIŞI (bilinçli): easing conformance (MO-02) — cubic-bezier(.4,0,.2,1) /
 * ease-in-out kullanımları AYRI micro-CP'de ele alınacak; bu test onları assert ETMEZ.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const ROOT = join(import.meta.dirname, '..');
const css = readFileSync(join(ROOT, 'src/app/globals.css'), 'utf8');
const tw = readFileSync(join(ROOT, 'tailwind.config.ts'), 'utf8');
const gates = readFileSync(join(ROOT, 'stylelint-plugins/trademinds-gates.cjs'), 'utf8');
const cssN = css.replace(/\s+/g, ' '); // yapısal kontroller için whitespace-normalize

let pass = 0, fail = 0;
const fails = [];
function ok(cond, label) {
  if (cond) { pass++; } else { fail++; fails.push(label); }
}

// ── 1 · Süre token seti (VL §09 kanonik) + 600ms sert-tavan ──────────────────
const EXPECT_DUR = {
  '--dur-micro': 140, '--dur-state': 180, '--dur-photon': 150, '--dur-warm': 140,
  '--dur-settle': 520, '--dur-route': 180, '--dur-overlay': 360, '--stagger': 50,
  '--dur-flash': 300, // v1.5 (K-J): veri-foton bg-tint
};
for (const [tok, ms] of Object.entries(EXPECT_DUR)) {
  const m = css.match(new RegExp(`${tok}\\s*:\\s*(\\d+)ms`));
  ok(m && Number(m[1]) === ms, `token ${tok} = ${ms}ms`);
  ok(m && Number(m[1]) <= 600, `token ${tok} ≤ 600ms sert-tavan`);
}
ok(/--ease-signal\s*:\s*cubic-bezier\(\s*0\.2\s*,\s*0\.8\s*,\s*0\.2\s*,\s*1\s*\)/.test(css),
  '--ease-signal = cubic-bezier(0.2, 0.8, 0.2, 1)');

// ── 2 · gate-5 ALLOWED_MS = token ms kümesi (guardrail↔token drift kilidi) ────
const gm = gates.match(/ALLOWED_MS = new Set\(\[([^\]]+)\]\)/);
ok(!!gm, 'gate-5 ALLOWED_MS bulundu');
if (gm) {
  const gateSet = new Set(gm[1].split(',').map((s) => Number(s.trim())));
  const tokenSet = new Set(Object.values(EXPECT_DUR));
  const eq = gateSet.size === tokenSet.size && [...tokenSet].every((v) => gateSet.has(v));
  ok(eq, `gate-5 seti {${[...gateSet].sort((a,b)=>a-b)}} = token ms kümesi {${[...tokenSet].sort((a,b)=>a-b)}}`);
}

// ── 3 · reduced-motion 3-katman + scroll auto (VL §08/§09) ───────────────────
const rmCount = (cssN.match(/@media \(prefers-reduced-motion: reduce\)/g) || []).length;
ok(rmCount >= 2, `reduced-motion @media blok sayısı ≥ 2 (bulunan: ${rmCount})`);
ok(/animation-duration:\s*0\.01ms\s*!important/.test(css), 'katman-1: animation-duration 0.01ms !important');
ok(/transition-duration:\s*0\.01ms\s*!important/.test(css), 'katman-1: transition-duration 0.01ms !important');
ok(/animation-iteration-count:\s*1\s*!important/.test(css), 'katman-1: animation-iteration-count 1 !important');
ok(cssN.includes('scroll-behavior: auto'), 'katman-1: scroll-behavior auto (reduced-motion)');
ok(/button:not\(:disabled\), a \{ transition: none/.test(cssN), 'katman-2: button/link transition none');
ok(/a:active \{ transform: none/.test(cssN), 'katman-2: a:active transform none');
ok(/\.route-cycle \{ animation: none/.test(cssN), 'katman-3: .route-cycle animation none');

// ── 4 · @keyframes yalnız transform/opacity (MO-01 layout-anim yasağı) ───────
const ANIM_ALLOWED = new Set(['transform', 'opacity']);
function checkKeyframeProps(source, blockBody, name) {
  const props = [...blockBody.matchAll(/([a-z][a-z-]*)\s*:/g)].map((m) => m[1]);
  const bad = props.filter((p) => !ANIM_ALLOWED.has(p));
  ok(bad.length === 0, `keyframe ${name} yalnız transform/opacity${bad.length ? ` (ihlal: ${bad.join(',')})` : ''}`);
}
// Tam gövde (bir-seviye iç-içe {}): keyframe'in HER bloğu taranır (ilk % ile sınırlı değil).
for (const m of css.matchAll(/@keyframes\s+([\w-]+)\s*\{((?:[^{}]|\{[^{}]*\})*)\}/g)) {
  checkKeyframeProps(css, m[2], `css:${m[1]}`);
}
// globals.css beklenen keyframe'ler mevcut mu
for (const kf of ['route-cycle-in', 'tp-win-photon', 'landing-rise', 'price-flash']) {
  ok(new RegExp(`@keyframes\\s+${kf}\\b`).test(css), `keyframe ${kf} mevcut`);
}
// tailwind.config keyframes objesi (slideUp/slideDown/fadeIn/scaleIn)
const twKf = tw.match(/keyframes:\s*\{([\s\S]*?)\n\s{6}\}/);
ok(!!twKf, 'tailwind keyframes bloğu bulundu');
if (twKf) {
  const twProps = [...twKf[1].matchAll(/([a-z]+):\s*'/g)].map((m) => m[1]);
  const bad = twProps.filter((p) => !ANIM_ALLOWED.has(p));
  ok(bad.length === 0, `tailwind keyframes yalnız transform/opacity${bad.length ? ` (ihlal: ${bad.join(',')})` : ''}`);
}

// ── 5 · tailwind köprüsü token-bağlı ─────────────────────────────────────────
const TW_DUR = { micro: '--dur-micro', state: '--dur-state', photon: '--dur-photon', warm: '--dur-warm',
  settle: '--dur-settle', route: '--dur-route', overlay: '--dur-overlay', stagger: '--stagger',
  flash: '--dur-flash' };
for (const [key, tok] of Object.entries(TW_DUR)) {
  ok(new RegExp(`${key}:\\s*'var\\(${tok}\\)'`).test(tw), `tailwind transitionDuration.${key} → var(${tok})`);
}
ok(/signal:\s*'var\(--ease-signal\)'/.test(tw), 'tailwind transitionTimingFunction.signal → var(--ease-signal)');

// ── 6 · gate-5 landing carve-out (PI-3b · VL:255 landing-only glow-drift) ─────
// Landing ambient muafiyeti YALNIZ [data-landing-ambient] marker'inda; app 600ms
// sert-tavani + set-disi kurali DEGISMEDI. Davranissal kanit: gate5-carveout.test.mjs.
ok(/function inLandingAmbient\(decl\)/.test(gates), 'carve-out: inLandingAmbient helper mevcut');
ok(/\[data-landing-ambient/.test(gates), 'carve-out: rezerve marker [data-landing-ambient]');
ok(/if \(inLandingAmbient\(decl\)\) return null;/.test(gates), 'carve-out: gate-5 inLandingAmbient ile muaf tutuyor');
ok(/ms > 600/.test(gates), 'global 600ms sert-tavan kurali DEGISMEDI (app icin korunur)');
ok(/if \(inReducedMotion\(decl\)\) return null;/.test(gates), 'reduced-motion muafiyeti korundu (ikinci muafiyet degil, mevcut)');
// Yalniz bu iki muafiyet (reduced-motion + landing-ambient) — baska "return null" muafiyeti eklenmedi.
const gate5Body = (gates.match(/'duration-token-set'[\s\S]*?\n\);/) || [''])[0];
const exemptionReturns = (gate5Body.match(/return null;/g) || []).length;
ok(exemptionReturns === 3, `gate-5 muafiyet-cikisi = 3 (reduced-motion + landing-ambient + prop-disi filtre); bulunan ${exemptionReturns}`);

// ── 7 · M-L1 T3 landing-reveal kilitleri (VL v1.5 / K-J) ─────────────────────
// (a) Scope-sızıntı yasağı: her .rv-* selector'ü [data-landing-reveal] altında
//     yaşar — app yüzeyine sızamaz (Doctrine: T3 YALNIZ landing).
const cssNoComments = css.replace(/\/\*[\s\S]*?\*\//g, '');
const rvSelectorLines = cssNoComments.split('\n')
  .map((l) => l.trim())
  .filter((l) => /\.rv-/.test(l) && /[,{]\s*$/.test(l));
ok(rvSelectorLines.length >= 8, `M-L1: .rv-* selector satırları mevcut (bulunan: ${rvSelectorLines.length})`);
ok(rvSelectorLines.every((l) => l.startsWith('[data-landing-reveal]')),
  'M-L1: tüm .rv-* selector\'leri [data-landing-reveal] scope-içi (app-sızıntısı yok)');
// (b) Reduce emniyet katmanı: reveal reduce'ta tamamen atlanır (animation none +
//     opacity 1) — .rv-section reduce-listesinin son selector'ü, blok gövdesine bitişik.
ok(/\[data-landing-reveal\] \.rv-section \{ animation: none; opacity: 1; \}/.test(cssN),
  'M-L1: reduce emniyet bloğu (animation:none + opacity:1) mevcut');
// (c) T3 sekans-bütçe kilidi: max stagger-çarpanı × --stagger + --dur-settle ≤ 1200ms
//     (VL v1.5 carve-out: sekans toplamı ≤1.2s; öğe süreleri zaten set-içi).
const staggerMults = [...css.matchAll(/calc\(var\(--stagger\) \* (\d+)\)/g)].map((m) => Number(m[1]));
ok(staggerMults.length >= 4, `M-L1: stagger-çarpanlı delay katmanları mevcut (bulunan: ${staggerMults.length})`);
if (staggerMults.length) {
  const worstMs = Math.max(...staggerMults) * EXPECT_DUR['--stagger'] + EXPECT_DUR['--dur-settle'];
  ok(worstMs <= 1200, `M-L1: T3 sekans en-geç-bitiş ${worstMs}ms ≤ 1200ms (carve-out bütçesi)`);
}

// ── 8 · M-P1 Tick Photon kilitleri (VL v1.5 / K-J) ───────────────────────────
// Foton = token-süre + kanonik easing + TEK-ATIM (iteration 1; loop'a dönüşemez).
ok(/animation: price-flash var\(--dur-flash\) var\(--ease-signal\) 1;/.test(css),
  'M-P1: foton animasyonu --dur-flash + --ease-signal + iteration 1');
// Tint yalnız owned bull/bear %12 color-mix (hex yok; /10–/15 bandı, COL-11 kapalı).
ok(/\.price-flash-up::after\s*\{ background: color-mix\(in oklab, var\(--bull\) 12%, transparent\); \}/.test(css) &&
   /\.price-flash-down::after\s*\{ background: color-mix\(in oklab, var\(--bear\) 12%, transparent\); \}/.test(css),
  'M-P1: tint = color-mix var(--bull/--bear) %12 (hex yok)');
// Overlay metnin ALTINDA (z:-1) + isolation — flash-anı kontrast güvencesinin CSS ayağı.
ok(/\.price-flash-up,\s*\.price-flash-down \{\s*position: relative;\s*isolation: isolate;/.test(css),
  'M-P1: flash host relative + isolate');
ok(/\.price-flash-up::after,\s*\.price-flash-down::after \{[^}]*z-index: -1;/.test(css),
  'M-P1: foton overlay z-index -1 (metnin altında)');

// ── Sonuç ────────────────────────────────────────────────────────────────────
const total = pass + fail;
if (fail) {
  console.error(`Motion self-test: ${pass} geçti, ${fail} KALDI (toplam ${total})`);
  fails.forEach((f) => console.error(`  ✗ ${f}`));
  process.exit(1);
}
console.log(`Motion self-test: ${pass} geçti, 0 kaldı (toplam ${total})`);
console.log('✓ Token seti + reduced-motion 3-katman + keyframe MO-01 + gate↔token + tailwind köprüsü kilitli.');
