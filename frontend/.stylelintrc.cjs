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
    // gate-5 ERROR (Premium-motion guardrail, PI-0a): CSS süre-token DoD=0 —
    // reduced-motion 0.01ms muaf (plugin) + scrollbar 0.2s→var(--dur-state).
    // Diğer 3 gate WARN-mod (kendi component fazlarında error'a çekilecek).
    'trademinds/duration-token-set': [true, { severity: 'error' }],
  },
  // İzin-listesi (dosya düzeyi): build çıktıları + bağımlılıklar taranmaz.
  ignoreFiles: ['node_modules/**', '.next/**', 'public/**'],
};
