'use strict';
/**
 * TradeMinds Design-Lint Gate'leri — Bible v1.3 §08 K4/K5 (Phase 1 · P1-F/g)
 *
 * 4 CSS gate (WARN-mod; ERROR yükseltmesi component fazları grep-DoD=0'a
 * ulaştıkça .stylelintrc.cjs severity ile yapılır — plugin'e dokunmadan):
 *   gate-1  trademinds/no-raw-hex-outside-root   :root dışı ham hex yasak (token'dan oku)
 *   gate-2  trademinds/no-colored-glow           box/text-shadow'da renkli rgba/hex yasak (nötr siyah + token serbest)
 *   gate-3  trademinds/no-cyan-surface           cyan yüzey/dolgu yasak (yalnız çizgi/iz — COL-07)
 *   gate-5  trademinds/duration-token-set        süre ayrık-küme dışı yasak (MO-01 tek-rejim)
 * (gate-4 kırpılmış-eksen CSS-dışı → scripts/design-gates.mjs)
 *
 * K5 MUAFİYET-KANCASI: selector'ı [data-instrument] içeren kurallar gate-2/3'ten
 * muaftır (Karot enstrüman-içi ışık-underlay / cyan-omurga). Bugün eşleşen selector
 * yok; Karot primitifi (Phase 3) eklenince kanca kendiliğinden devreye girer.
 */
const stylelint = require('stylelint');

const HEX_RE = /#[0-9a-f]{3,8}\b/gi;
// Nötr (renksiz) gölge serbest: rgba(0,0,0,x) / rgb(0 0 0 / x) — luminans-depth değil glow yasak.
const NEUTRAL_SHADOW_RE = /rgba?\(\s*0\s*[, ]\s*0\s*[, ]\s*0\s*[,/]/;
const COLORED_FN_RE = /rgba?\(\s*(\d{1,3})\s*[, ]\s*(\d{1,3})\s*[, ]\s*(\d{1,3})/g;
// Cyan tespiti: owned #25E0D4 + emekli #22D3EE + rgb eşlenikleri + var(--cyan)/eski alias.
const CYAN_RE = /var\(--cyan\)|var\(--accent-secondary\)|#25E0D4|#22D3EE|rgba?\(\s*37\s*[, ]\s*224\s*[, ]\s*212|rgba?\(\s*34\s*[, ]\s*211\s*[, ]\s*238/i;
const SURFACE_PROPS = new Set(['background', 'background-color', 'background-image', 'fill']);
const SHADOW_PROPS = new Set(['box-shadow', 'text-shadow']);
const DUR_PROPS = new Set(['transition-duration', 'animation-duration', 'transition', 'animation']);
// MO-01 ayrık küme (ms) + stagger; 0 daima serbest; var(--dur-*) token'ları daima serbest.
const ALLOWED_MS = new Set([140, 150, 180, 360, 520, 50]);
const DUR_LITERAL_RE = /(\d*\.?\d+)\s*(ms|s)\b/g;

function isKarotExempt(decl) {
  let node = decl.parent;
  while (node) {
    if (node.selector && node.selector.includes('[data-instrument')) return true;
    node = node.parent;
  }
  return false;
}
// reduced-motion son-kare (0.01ms) MO-03/MO-10 geregi kanonik "hareketi oldur"
// degeridir (0 bazi tarayicida transitionend olayini bastirir) → gate-5'ten muaf.
function inReducedMotion(decl) {
  let node = decl.parent;
  while (node) {
    if (node.type === 'atrule' && node.name === 'media' &&
        /prefers-reduced-motion/i.test(node.params || '')) return true;
    node = node.parent;
  }
  return false;
}
// LANDING glow-drift muafiyeti (VL:255/308) — landing'in TEK animasyonlu ambient
// istisnasi: yavas kayan anahtar-isik (transform-only, yon/opaklik anlamli degil).
// Bu ambient dogasi geregi uzun-sureli (saniyeler) → 600ms app-tavani UYGULANMAZ.
// KAPSAM SIKI + LANDING-ONLY: muafiyet YALNIZ rezerve `[data-landing-ambient]`
// marker-selector'unda gecerlidir (isaretsiz her sure/token hala bloklanir; app
// >600ms kurali DEGISMEDI). isKarotExempt/[data-instrument] ile ayni ancestor-desen.
// Rezerve marker yalniz landing hero atmosfer-katmaninda kullanilir; baska muafiyet yok.
function inLandingAmbient(decl) {
  let node = decl.parent;
  while (node) {
    if (node.selector && node.selector.includes('[data-landing-ambient')) return true;
    node = node.parent;
  }
  return false;
}
function inRoot(decl) {
  let node = decl.parent;
  while (node) {
    if (node.selector && node.selector.split(',').some((s) => s.trim() === ':root')) return true;
    node = node.parent;
  }
  return false;
}
function mkRule(name, message, check) {
  const ruleName = `trademinds/${name}`;
  const messages = stylelint.utils.ruleMessages(ruleName, { rejected: (d) => `${message} → ${d}` });
  const fn = (enabled) => (root, result) => {
    if (!enabled) return;
    root.walkDecls((decl) => {
      const hit = check(decl);
      if (hit) {
        stylelint.utils.report({
          message: messages.rejected(hit),
          node: decl,
          result,
          ruleName,
        });
      }
    });
  };
  fn.ruleName = ruleName;
  fn.messages = messages;
  fn.meta = { url: 'docs/design/DESIGN-BIBLE (§08 K4/K5)' };
  return stylelint.createPlugin(ruleName, fn);
}

const gate1 = mkRule(
  'no-raw-hex-outside-root',
  'gate-1 token-dışı-hex: ham hex yalnız :root token tanımında; component/utility var(--token) okumalı (Bible §01)',
  (decl) => {
    if (inRoot(decl)) return null;
    if (decl.prop.startsWith('--')) return null; // token tanımı (nested custom prop) serbest
    const m = decl.value.match(HEX_RE);
    return m ? `${decl.prop}: …${m.join(', ')}…` : null;
  }
);

const gate2 = mkRule(
  'no-colored-glow',
  'gate-2 renkli-glow: box/text-shadow renkli rgba/hex taşıyamaz (glow yalnız --glow-cta/--shadow-e3 token; COL-12 semantik-glow=0)',
  (decl) => {
    if (!SHADOW_PROPS.has(decl.prop)) return null;
    if (decl.value === 'none' || decl.value.includes('var(--')) return null;
    if (isKarotExempt(decl)) return null; // K5: [data-instrument] enstrüman-içi ışık serbest
    if (HEX_RE.test(decl.value)) { HEX_RE.lastIndex = 0; return decl.value.trim().slice(0, 60); }
    HEX_RE.lastIndex = 0;
    let m; COLORED_FN_RE.lastIndex = 0;
    while ((m = COLORED_FN_RE.exec(decl.value))) {
      if (!(m[1] === '0' && m[2] === '0' && m[3] === '0')) return decl.value.trim().slice(0, 60);
    }
    return null;
  }
);

const gate3 = mkRule(
  'no-cyan-surface',
  'gate-3 cyan-yüzey: cyan yalnız çizgi/nokta/iz (stroke/border/color); background/fill CYAN OLAMAZ (COL-07 AI-izi tekeli)',
  (decl) => {
    if (!SURFACE_PROPS.has(decl.prop)) return null;
    if (isKarotExempt(decl)) return null; // K5: Karot omurga-underlay istisnası
    return CYAN_RE.test(decl.value) ? `${decl.prop}: ${decl.value.trim().slice(0, 60)}` : null;
  }
);

// gate-5 ayrica --dur-*/--stagger TOKEN TANIMLARINI denetler: kullanimda
// var(--dur-x) "daima serbest" gorundugunden, rogue bir token (or. --dur-x: 900ms)
// yalnizca tanim noktasinda yakalanabilir (600ms sert-tavan kaynak-kilidi).
const DUR_TOKEN_RE = /^--(dur|stagger)/;
const gate5 = mkRule(
  'duration-token-set',
  'gate-5 süre-kümesi: süre ayrık token setinden olmalı {140,150,180,360,520}ms+50ms stagger veya var(--dur-*) (MO-01 tek-rejim; app sert-tavan 600ms)',
  (decl) => {
    if (inReducedMotion(decl)) return null; // reduced-motion 0.01ms son-kare muaf
    if (inLandingAmbient(decl)) return null; // landing glow-drift (VL:255 landing-only ambient); app 600ms tavani degismedi
    if (!DUR_PROPS.has(decl.prop) && !DUR_TOKEN_RE.test(decl.prop)) return null;
    let m; DUR_LITERAL_RE.lastIndex = 0;
    const bad = [];
    while ((m = DUR_LITERAL_RE.exec(decl.value))) {
      const ms = parseFloat(m[1]) * (m[2] === 's' ? 1000 : 1);
      if (ms === 0) continue;
      if (ms > 600) bad.push(`${m[1]}${m[2]} (>600ms sert-tavan)`);
      else if (!ALLOWED_MS.has(ms)) bad.push(`${m[1]}${m[2]} set-dışı`);
    }
    return bad.length ? `${decl.prop}: [${bad.join(', ')}]` : null;
  }
);

module.exports = [gate1, gate2, gate3, gate5];
