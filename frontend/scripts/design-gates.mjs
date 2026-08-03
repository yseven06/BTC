#!/usr/bin/env node
/**
 * TradeMinds Design-Gate'leri (CSS-dışı ayak) — Bible v1.3 §08 K4 (P1-F/g)
 * WARN-MOD: her zaman exit 0; envanter raporlar. ERROR yükseltme: `--strict`
 * bayrağı (ilgili faz grep-DoD=0 olunca CI'da --strict'e çekilir).
 *
 *   gate-1/TSX  token-dışı-hex: src TSX/TS içinde ham renk-hex (izin-listesi hariç)
 *   gate-4      kırpılmış-eksen: chart config'lerinde baseline-kırpma desenleri
 *   gate-5/TSX  süre-token: Tailwind duration-* + inline-style transition/animation
 *               literalleri ayrık token setinden ({140,150,180,300,360,520}+50) veya
 *               var(--dur-*) olmalı (MO-01; app 600ms sert-tavan). CSS ayağı gate-5
 *               (stylelint) ERROR; TSX ayağı WARN-envanteri (--strict CI'da error).
 *
 * İZİN-LİSTESİ (ALLOW): CSS var() okuyamayan JS/JSON bağlamları — değer --e0 ile
 * elle-senkron tutulur (bkz. layout.tsx yorumu, P1-F/f):
 *   - src/app/layout.tsx            (viewport.themeColor)
 *   - TradingViewChart.tsx          (3P widget config: toolbar_bg/backgroundColor)
 *   - ShareCardModal.tsx            (canvas export — DOM dışı, computed-style yok)
 * K5: `data-instrument` geçen satırlar muaf (Karot enstrüman-içi; P3'te devreye girer).
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

const STRICT = process.argv.includes('--strict');
const ROOT = join(import.meta.dirname, '..');
const SRC = join(ROOT, 'src');

const ALLOW_FILES = [
  ['src', 'app', 'layout.tsx'].join(sep),
  ['components', 'charts', 'TradingViewChart.tsx'].join(sep),
  // ShareCardModal P9.6'da chartColors'a göç etti → izin-listesinden ÇIKARILDI (ham hex=0).
  ['src', 'lib', 'chartColors.ts'].join(sep), // JS-bağlamı token-kaynağı (P9.5): runtime-resolve + owned fallback
];
const HEX_RE = /#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b(?![0-9a-fA-F])/g;
// gate-4 kırpılmış-eksen desenleri (Lie Factor=1: baseline 0/dataMin'den kırpılamaz):
const CLIP_PATTERNS = [
  [/domain=\{\s*\[\s*['"]auto['"]/, "YAxis domain 'auto' (baseline kayar — 0/dataMin olmalı)"],
  [/domain=\{\s*\[\s*(?!0|\s*['"]dataMin['"])[^\]]+\]/, 'YAxis domain 0/dataMin dışı alt-sınır'],
  [/minValue\s*:\s*(?!0)\d/, 'chart minValue≠0 (kırpılmış baseline)'],
  [/scaleMargins\s*:\s*\{[^}]*bottom\s*:\s*0\.5/, 'aşırı bottom scaleMargin (görsel kırpma)'],
];

// gate-5/TSX süre kümesi (MO-01 ayrık token + 600ms sert-tavan). Named Tailwind
// duration (duration-micro/state/…) ve duration-[var(--dur-*)] serbest; yakalanan:
// numerik/arbitrary literal (duration-200, duration-[0.3s]) + inline-style
// transition/animation literalleri. var(--dur-*) her zaman muaf.
// gate-6/TSX transition-all yasağı (MO-01 property-explicit; S2b migration DoD=0).
// Yeni runtime `transition-all` girişini engeller. YALNIZ tam `transition-all`
// kelimesi yakalanır → property-explicit sınıflar (transition-colors /
// transition-transform / transition-[width,background-color] / transition-[top,left,width,height])
// YANLIŞ-POZİTİF üretmez. Tarama, aşağıdaki yorum-soyulmuş `line` üzerinde koşar →
// //, /* */, {/* */} JSX yorumları ihlal sayılmaz (mevcut stripping yeniden kullanılır).
const TRANSITION_ALL_RE = /\btransition-all\b/;
// (S5d) Landing-CTA grandfather'ı EMEKLİ — iki "Ücretsiz Başla" CTA'sı
// property-explicit'e çevrildi (transition-[background-color,box-shadow]);
// repo-geneli DoD=0, istisna/allowlist kalmadı. (Kaldırma, bu bloğun kendi
// "S5/S6'da CTA property-explicit yapılınca bu blok kaldırılır" talimatıdır.)

const DUR_SET = new Set([140, 150, 180, 300, 360, 520, 50]); // v1.5: +300 (--dur-flash, K-J)
function badDurationsTSX(line) {
  const bad = [];
  let m;
  const push = (label, ms) => {
    if (ms === 0) return;
    if (ms > 600) bad.push(`${label} (>600ms sert-tavan)`);
    else if (!DUR_SET.has(ms)) bad.push(`${label} set-dışı`);
  };
  // Tailwind arbitrary: duration-[..]
  const ARB = /duration-\[([^\]]+)\]/g;
  while ((m = ARB.exec(line))) {
    if (/var\(--dur/.test(m[1])) continue;
    const t = /(\d*\.?\d+)\s*(ms|s)\b/.exec(m[1]);
    if (t) push(`duration-[${m[1]}]`, parseFloat(t[1]) * (t[2] === 's' ? 1000 : 1));
  }
  // Tailwind numerik: duration-200
  const NUM = /\bduration-(\d+)\b/g;
  while ((m = NUM.exec(line))) push(`duration-${m[1]}`, parseInt(m[1], 10));
  // Inline-style: transition/animation(+Duration) literal süreler
  const INLINE = /(transition|animation)(?:Duration)?\s*:\s*(['"`])([^'"`]*)\2/g;
  while ((m = INLINE.exec(line))) {
    if (/var\(--dur/.test(m[3])) continue;
    let t; const T = /(\d*\.?\d+)\s*(ms|s)\b/g;
    while ((t = T.exec(m[3]))) push(`${m[1]}: ${t[1]}${t[2]}`, parseFloat(t[1]) * (t[2] === 's' ? 1000 : 1));
  }
  return bad;
}

const files = [];
(function walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) walk(p);
    else if (/\.(tsx|ts)$/.test(name) && !name.endsWith('.d.ts')) files.push(p);
  }
})(SRC);

let warnHex = 0, warnClip = 0, warnDur = 0, allowedHex = 0;
const report = [];      // gate-1 + gate-4: DoD=0 → --strict'te commit-BLOKLAR.
const durReport = [];   // gate-5/TSX: 3 mevcut borç → WARN-envanteri, BLOKLAMAZ (aşağı).
const gate6Report = []; // gate-6/TSX: yeni transition-all ihlalleri (DoD=0) → --strict'te BLOKLAR.
for (const f of files) {
  const rel = relative(ROOT, f);
  const isAllowed = ALLOW_FILES.some((a) => rel.endsWith(a));
  const lines = readFileSync(f, 'utf8').split(/\r?\n/) /* CRLF: satir-sonu \r yorum-stripping $ desenlerini bozuyordu (P9-FINAL) */;
  lines.forEach((raw, i) => {
    if (raw.includes('data-instrument')) return; // K5 muafiyet-kancası
    // Yorum-stripping (P9-FINAL): dokümantasyon hex'leri (EMEKLİ/migration-notları)
    // ihlal değildir — satır-içi //, /* */, JSDoc-devamı (* ile başlar) ve HTML
    // entity (&#039;) taramadan SOYULUR; URL'deki :// korunur ([^:] guard).
    const line = raw
      .replace(/\/\*[\s\S]*?(\*\/|$)/g, '')
      .replace(/^\s*\*.*/, '')
      .replace(/(^|[^:])\/\/.*$/, '$1')
      .replace(/&#x?[0-9a-fA-F]+;/g, '');
    const hexes = line.match(HEX_RE);
    if (hexes) {
      if (isAllowed) { allowedHex += hexes.length; return; }
      warnHex += hexes.length;
      report.push(`  [gate-1/TSX] ${rel}:${i + 1}  ${hexes.join(' ')}`);
    }
    if (/chart/i.test(rel) || /recharts|lightweight/i.test(line)) {
      for (const [re, why] of CLIP_PATTERNS) {
        if (re.test(line)) { warnClip++; report.push(`  [gate-4] ${rel}:${i + 1}  ${why}`); }
      }
    }
    for (const d of badDurationsTSX(line)) {
      warnDur++;
      durReport.push(`  [gate-5/TSX] ${rel}:${i + 1}  ${d}`);
    }
    // gate-6/TSX: transition-all yasağı (yorum-soyulmuş `line` → yorum muaf).
    if (TRANSITION_ALL_RE.test(line)) {
      gate6Report.push(
        `  [gate-6/TSX] ${rel}:${i + 1}  runtime "transition-all" (property-belirsiz)`
        + `\n      bağlam: ${raw.trim().slice(0, 96)}`
        + `\n      → yalnız gerçekten değişen property'leri belirt: transition-colors ·`
        + ` transition-[width,background-color] · transition-[top,left,width,height]`
      );
    }
  });
}

// ─── gate-7: canlı yaşam-döngüsü sözlüğü sözleşmesi (DoD=0 · --strict BLOKLAR) ──
// Backend `waiting_entry` durumunu üretmeye başladığında hiçbir şey hata vermedi:
// haritada anahtar yoktu, her yüzey sessizce `active`'e düştü ve dolmamış sinyal
// kullanıcıya yeşil "Aktif" göründü. Bu kapı bunun TEKRARINI imkânsız kılar —
// eksik eşleme veya `active`'e düşen bir fallback CI'ı kırar.
const gate7Report = [];
const g7 = (cond, msg) => { if (!cond) gate7Report.push(`  [gate-7] ${msg}`); };
const stripComments = (s) => s
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .split(/\r?\n/).map((l) => l.replace(/(^|[^:])\/\/.*$/, '$1')).join('\n');

const BADGE_REL = ['src', 'components', 'ui', 'LiveStatusBadge.tsx'].join(sep);
const badgeFile = files.find((f) => relative(ROOT, f).endsWith(BADGE_REL));
if (!badgeFile) {
  gate7Report.push('  [gate-7] LiveStatusBadge.tsx bulunamadı — durum sözlüğünün tek kaynağı');
} else {
  const b = stripComments(readFileSync(badgeFile, 'utf8'));
  g7(/\bwaiting_entry\s*:\s*\{/.test(b),
     "LIVE_STATUS_META'da `waiting_entry` yok — backend bu durumu üretiyor");
  g7(/label:\s*['"]Giriş Bekleniyor['"]/.test(b),
     "`waiting_entry` etiketi kanonik değil (beklenen: 'Giriş Bekleniyor')");
  g7(/export const UNKNOWN_STATUS_META/.test(b),
     'UNKNOWN_STATUS_META yok — bilinmeyen durumun gidecek güvenli yeri kalmaz');
  g7(/export function statusMeta/.test(b),
     'statusMeta() yok — tek güvenli çözümleme yolu');
  const wRow = b.split(/\r?\n/).find((l) => /\bwaiting_entry\s*:\s*\{/.test(l)) || '';
  g7(!/bullish/.test(wRow),
     '`waiting_entry` bullish/yeşil token kullanıyor — açılmamış pozisyonu açık gösterir');
}

for (const f of files) {
  const rel = relative(ROOT, f);
  const s = stripComments(readFileSync(f, 'utf8'));
  if (/LIVE_STATUS_META\s*\.\s*active/.test(s)) {
    gate7Report.push(`  [gate-7] ${rel}  bilinmeyen durum \`active\`'e düşürülüyor → statusMeta() kullan`);
  }
  if (/LIVE_STATUS_META\s*\[[^\]]*\]\s*\??\.\s*(label|cls|bg|Icon)/.test(s)) {
    gate7Report.push(`  [gate-7] ${rel}  ham LIVE_STATUS_META[...] okuması (bilinmeyen değerde undefined) → statusMeta()`);
  }
  if (/\|\|\s*['"]Aktif['"]/.test(s)) {
    gate7Report.push(`  [gate-7] ${rel}  metin fallback'i 'Aktif' — bilinmeyen durumu aktif ilan ediyor`);
  }
  if (/\?\?\s*(s|status)\s*[;,)]/.test(s)) {
    gate7Report.push(`  [gate-7] ${rel}  ham durum dizesi kullanıcıya sızıyor (\`?? s\`) → statusMeta()`);
  }
}

const journalFile = files.find((f) => relative(ROOT, f).endsWith(['LifecycleJourney.tsx'].join(sep)));
if (journalFile) {
  const j = stripComments(readFileSync(journalFile, 'utf8'));
  g7(/PHASE_DOT[\s\S]{0,240}?waiting_entry\s*:/.test(j),
     "LifecycleJourney PHASE_DOT'ta `waiting_entry` yok — zaman çizelgesinde renksiz kalır");
}
const bandFile = files.find((f) => relative(ROOT, f).endsWith(['DurumBandi.tsx'].join(sep)));
if (bandFile) {
  const d = stripComments(readFileSync(bandFile, 'utf8'));
  g7(/const census\s*=\s*\(\[[^\]]*['"]waiting_entry['"]/.test(d),
     "DurumBandı sayımı `waiting_entry` içermiyor — dolmamış sinyaller sayımdan düşer");
}

console.log('— TradeMinds design-gates (CSS-dışı) —');
console.log(`taranan: ${files.length} dosya · izin-listesi hex: ${allowedHex} (senkron-envanteri, WARN değil)`);
// gate-1/gate-4 (DoD=0) — --strict'te commit-BLOKLAR.
if (report.length) {
  console.log(`WARN ${warnHex} ham-hex (gate-1/TSX) · ${warnClip} kırpılmış-eksen (gate-4):`);
  // İlk 40 satır; tam envanter component fazlarında (P9 Color) grep-DoD=0'a çekilecek.
  report.slice(0, 40).forEach((r) => console.log(r));
  if (report.length > 40) console.log(`  … +${report.length - 40} satır daha (WARN-mod envanteri)`);
} else {
  console.log('WARN 0 — temiz (gate-1/gate-4).');
}
// gate-5/TSX (PI-0a) — CSS ayağı stylelint'te ERROR; TSX ayağı henüz DoD>0
// (3 mevcut borç) olduğundan yalnız WARN-envanteri, --strict'te BLOKLAMAZ.
// Borçlar component checkpoint'lerinde temizlenince exit koşuluna (report) alınır.
if (durReport.length) {
  console.log(`WARN ${warnDur} süre-token (gate-5/TSX · non-blocking envanter; CSS ayağı ERROR):`);
  durReport.slice(0, 40).forEach((r) => console.log(r));
}
// gate-6/TSX transition-all yasağı — S5d ile grandfather EMEKLİ: repo-geneli
// DoD=0; HER occurrence ihlaldir ve --strict'te BLOKLAR.
const gate6Fail = gate6Report.length > 0;
console.log(`gate-6/TSX transition-all — violations: ${gate6Report.length} (DoD=0 · grandfather emekli/S5d)`);
gate6Report.forEach((r) => console.log(r));
if (gate6Fail) console.log('  transition-all is forbidden (MO-01). Declare only the properties that actually change, e.g. transition-colors or transition-[width,background-color].');

// gate-7 — DoD=0, her ihlal bloklar.
const gate7Fail = gate7Report.length > 0;
console.log(`gate-7 canlı-durum sözlüğü — violations: ${gate7Report.length} (DoD=0)`);
gate7Report.forEach((r) => console.log(r));
if (gate7Fail) console.log('  Every live_status must resolve through statusMeta(); an unknown status may never render as "Aktif" and the raw token may never reach the user.');

process.exit(STRICT && (report.length || gate6Fail || gate7Fail) ? 1 : 0);
