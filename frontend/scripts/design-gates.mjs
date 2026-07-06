#!/usr/bin/env node
/**
 * TradeMinds Design-Gate'leri (CSS-dışı ayak) — Bible v1.3 §08 K4 (P1-F/g)
 * WARN-MOD: her zaman exit 0; envanter raporlar. ERROR yükseltme: `--strict`
 * bayrağı (ilgili faz grep-DoD=0 olunca CI'da --strict'e çekilir).
 *
 *   gate-1/TSX  token-dışı-hex: src TSX/TS içinde ham renk-hex (izin-listesi hariç)
 *   gate-4      kırpılmış-eksen: chart config'lerinde baseline-kırpma desenleri
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
  ['components', 'ui', 'ShareCardModal.tsx'].join(sep),
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

const files = [];
(function walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) walk(p);
    else if (/\.(tsx|ts)$/.test(name) && !name.endsWith('.d.ts')) files.push(p);
  }
})(SRC);

let warnHex = 0, warnClip = 0, allowedHex = 0;
const report = [];
for (const f of files) {
  const rel = relative(ROOT, f);
  const isAllowed = ALLOW_FILES.some((a) => rel.endsWith(a));
  const lines = readFileSync(f, 'utf8').split('\n');
  lines.forEach((line, i) => {
    if (line.includes('data-instrument')) return; // K5 muafiyet-kancası
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
  });
}

console.log('— TradeMinds design-gates (CSS-dışı) —');
console.log(`taranan: ${files.length} dosya · izin-listesi hex: ${allowedHex} (senkron-envanteri, WARN değil)`);
if (report.length) {
  console.log(`WARN ${warnHex} ham-hex (gate-1/TSX) · ${warnClip} kırpılmış-eksen (gate-4):`);
  // İlk 40 satır; tam envanter component fazlarında (P9 Color) grep-DoD=0'a çekilecek.
  report.slice(0, 40).forEach((r) => console.log(r));
  if (report.length > 40) console.log(`  … +${report.length - 40} satır daha (WARN-mod envanteri)`);
} else {
  console.log('WARN 0 — temiz.');
}
process.exit(STRICT && report.length ? 1 : 0);
