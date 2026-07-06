'use strict';
/**
 * TradeMinds Design-Lint — Bible v1.3 §08 K4 (Phase 1 · P1-F/g)
 * WARN-MOD: mevcut (henüz göç edilmemiş) ihlaller build'i KIRMAZ; envanter üretir.
 * ERROR yükseltme kapısı: ilgili component fazı grep-DoD=0'a ulaşınca buradaki
 * severity 'warning' → 'error' çekilir (plugin'e dokunulmaz).
 * Kapsam: yalnız CSS (globals.css). TSX ham-hex + gate-4 chart-baseline →
 * scripts/design-gates.mjs (lint:design ikisini birlikte çalıştırır).
 */
module.exports = {
  plugins: ['./stylelint-plugins/trademinds-gates.cjs'],
  rules: {
    'trademinds/no-raw-hex-outside-root': [true, { severity: 'warning' }],
    'trademinds/no-colored-glow': [true, { severity: 'warning' }],
    'trademinds/no-cyan-surface': [true, { severity: 'warning' }],
    'trademinds/duration-token-set': [true, { severity: 'warning' }],
  },
  // İzin-listesi (dosya düzeyi): build çıktıları + bağımlılıklar taranmaz.
  ignoreFiles: ['node_modules/**', '.next/**', 'public/**'],
};
