import { dirname } from 'path';
import { fileURLToPath } from 'url';
import { FlatCompat } from '@eslint/eslintrc';

// Next.js 15 resmi flat-config köprüsü (create-next-app deseni). ESLint 9 artık
// .eslintrc'yi okumadığından lint-staged'in `eslint` görevi bir flat-config
// bekler; bu dosya `next/core-web-vitals` (Core Web Vitals) + `next/typescript`
// (TS desteği) preset'lerini AYNEN köprüler.
//
// Kural sertliği: TEMEL preset kuralları KORUNUR. Tek ayarlama:
//   - `@typescript-eslint/no-explicit-any` → 'warn' (72 pre-existing borç;
//     ayrı typing sprintinde temizlenecek, davranış değişimi riski taşıdığı
//     için toplu error olarak zorlanmıyor).
//   - `.cjs` uzantılı dosyalarda `no-require-imports` doğal olarak KAPALI
//     (CJS'de `require()` doğru yazımdır).
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({
  baseDirectory: __dirname,
});

const eslintConfig = [
  {
    // Üretilen/derlenen çıktı + salt-geliştirici tooling ESLint'e girmez.
    ignores: [
      '.next/**',
      'out/**',
      'build/**',
      'node_modules/**',
      'next-env.d.ts',
      // Repo kökündeki tek-seferlik dev script'i (app runtime'ının parçası değil).
      'take_screenshots.js',
    ],
  },
  ...compat.extends('next/core-web-vitals', 'next/typescript'),
  {
    // CJS dosyalarında `require()` kanonik yazımdır.
    files: ['**/*.cjs'],
    rules: {
      '@typescript-eslint/no-require-imports': 'off',
    },
  },
  {
    // Pre-existing 72 `any` teknik borcu; ayrı typing sprintinde temizlenecek.
    // Yeni kod için lint-staged `--max-warnings=0` bunu yine bloklar.
    rules: {
      '@typescript-eslint/no-explicit-any': 'warn',
    },
  },
];

export default eslintConfig;
