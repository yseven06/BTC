/**
 * Chart renkleri — JS/canvas bağlamı için tek-kaynak köprüsü (P9.5 / D9-07).
 *
 * lightweight-charts ve canvas-2D string hex/rgba ister; CSS var() DOĞRUDAN
 * geçmez. Bu modül token'ı RUNTIME'da globals.css :root'tan çözer
 * (getComputedStyle) → gerçek tek-kaynak: :root değişirse chart'lar da değişir.
 * SSR/ilk-frame için owned-hex FALLBACK sabitleri (Bible §01 KİLİTLİ değerler;
 * elle-senkron kuralı — bkz. layout.tsx themeColor deseni, P1-F/f).
 * design-gates izin-listesindedir (JS-bağlamı token-kaynağı).
 */

const FALLBACK = {
  e0: '#070B14',
  e1: '#0C1220',
  e2: '#111A2B',
  e3: '#17233A',
  tx: '#E8EDF5',
  tx2: '#9AA6B8',
  tx3: '#5C6980',
  bull: '#2FBE9A',
  bear: '#E14640',
  accent: '#3B57D4',
  accentUi: '#4E6BE3',
  accentHover: '#3450C6',
  cyan: '#25E0D4',
  amber: '#F5A524',
  hl10: 'rgba(148, 163, 184, 0.10)',
  hl12: 'rgba(148, 163, 184, 0.12)',
  hl16: 'rgba(148, 163, 184, 0.16)',
  hl22: 'rgba(148, 163, 184, 0.22)',
} as const;

export type ChartColorToken = keyof typeof FALLBACK;

const CSS_VAR: Record<ChartColorToken, string> = {
  e0: '--e0', e1: '--e1', e2: '--e2', e3: '--e3',
  tx: '--tx', tx2: '--tx2', tx3: '--tx3',
  bull: '--bull', bear: '--bear',
  accent: '--accent', accentUi: '--accent-ui', accentHover: '--accent-hover',
  cyan: '--cyan', amber: '--amber',
  hl10: '--hl10', hl12: '--hl12', hl16: '--hl16', hl22: '--hl22',
};

/** Token'ı runtime'da :root'tan çöz; SSR/erken-frame'de owned fallback. */
export function chartColor(token: ChartColorToken): string {
  if (typeof window === 'undefined') return FALLBACK[token];
  const v = getComputedStyle(document.documentElement)
    .getPropertyValue(CSS_VAR[token])
    .trim();
  return v || FALLBACK[token];
}

/** Hex (#RRGGBB) → rgba(r,g,b,a). Hex değilse (rgba token'ı) olduğu gibi döner. */
export function withAlpha(color: string, alpha: number): string {
  const m = /^#([0-9a-fA-F]{6})$/.exec(color.trim());
  if (!m) return color;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}
