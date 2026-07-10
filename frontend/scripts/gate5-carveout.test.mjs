// gate-5 landing carve-out — DAVRANISSAL test (stylelint'i fixture'larda kosar).
// PI-3b: landing glow-drift (VL:255 landing'in TEK animasyonlu ambient'i) icin
// [data-landing-ambient] marker'inda >600ms muaf; ama app >600ms/set-disi kurali
// isaretsiz her yerde DEGISMEDEN bloklanir. Bu test tam da bunu kanitlar.
//
// Kosum: node scripts/gate5-carveout.test.mjs   (frontend/ kokunden)
import stylelint from 'stylelint';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..'); // frontend/
const RULE = 'trademinds/duration-token-set';

let pass = 0;
let fail = 0;

async function gate5Warnings(code) {
  const res = await stylelint.lint({
    code,
    configBasedir: ROOT,
    config: {
      plugins: ['./stylelint-plugins/trademinds-gates.cjs'],
      rules: { [RULE]: [true, { severity: 'error' }] },
    },
  });
  return res.results[0].warnings.filter((w) => w.rule === RULE);
}

async function expectCase(label, code, wantBlocked) {
  const w = await gate5Warnings(code);
  const blocked = w.length > 0;
  if (blocked === wantBlocked) {
    pass++;
    console.log(`  ✓ ${label} → ${blocked ? 'BLOKLANDI' : 'muaf/temiz'}`);
  } else {
    fail++;
    console.log(
      `  ✗ ${label} → beklenen ${wantBlocked ? 'BLOK' : 'muaf'}, gelen ${blocked ? 'BLOK' : 'muaf'}` +
      (w.length ? ` [${w.map((x) => x.text).join('; ')}]` : '')
    );
  }
}

console.log('gate-5 landing carve-out davranissal test:');

// ── MUAF (landing-ambient marker) ────────────────────────────────────────────
await expectCase('marker + 24s glow-drift muaf', '[data-landing-ambient] { animation: glowDrift 24s linear infinite; }', false);
await expectCase('marker + 40s animation-duration muaf', '[data-landing-ambient] { animation-duration: 40s; }', false);
await expectCase('marker altindaki torun (ancestor-walk) muaf', '[data-landing-ambient] .layer { animation: glowDrift 30s linear infinite; }', false);
await expectCase('marker + kombine class muaf', '.glow-drift[data-landing-ambient] { animation: glowDrift 22s ease-in-out infinite; }', false);

// ── REGRESYON: marker YOK → app kurali degismeden bloklu ─────────────────────
await expectCase('REGRESYON marker YOK + 24s bloklu', '.hero-bg { animation: glowDrift 24s linear infinite; }', true);
await expectCase('REGRESYON app transition 900ms bloklu', '.foo { transition-duration: 900ms; }', true);
await expectCase('REGRESYON :root token-def 900ms bloklu', ':root { --dur-x: 900ms; }', true);
await expectCase('REGRESYON set-disi 300ms bloklu', '.foo { transition-duration: 300ms; }', true);
await expectCase('REGRESYON set-disi 12ms bloklu', '.foo { animation-duration: 12ms; }', true);
await expectCase('REGRESYON benzer-ama-farkli marker (data-landing) bloklu', '[data-landing] { animation: x 24s linear infinite; }', true);

// ── KONTROL: mevcut davranis korunur ─────────────────────────────────────────
await expectCase('KONTROL set-ici 180ms temiz', '.foo { transition-duration: 180ms; }', false);
await expectCase('KONTROL var(--dur-*) serbest', '.foo { transition-duration: var(--dur-state); }', false);
await expectCase('KONTROL reduced-motion 0.01ms hala muaf', '@media (prefers-reduced-motion: reduce) { * { animation-duration: 0.01ms; } }', false);

console.log(
  fail === 0
    ? `\ngate-5 carve-out: ${pass} geçti, 0 kaldı (toplam ${pass})\n✓ Landing-ambient marker muaf + isaretsiz/non-landing >600ms DEGISMEDEN bloklu.`
    : `\nBASARISIZ: ${fail} test kaldi (${pass} gecti).`
);
process.exit(fail === 0 ? 0 : 1);
