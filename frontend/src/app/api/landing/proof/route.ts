import { NextResponse } from 'next/server';

// CP-5a — Landing "Canlı Masa" veri katmanı (Design Constitution v1 §5, K-D/b1).
// ISR: route çıktısı 60 sn cache'lenir (Anayasa çelişki-çözümü #11: anonim poll yok,
// backend'i landing trafiğinden korur). Dev modda Next cache'i devre dışıdır (beklenen).
export const dynamic = 'force-static';
export const revalidate = 60;

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// 7-gün bayatlık kuralı TEK-KAYNAK olarak route'ta uygulanır (K-D kararı):
// son kapanan sinyal bundan eskiyse lastClosed=null döner, panel kartı render etmez.
const STALE_MS = 7 * 24 * 60 * 60 * 1000;

export interface LandingProofPayload {
  lastClosed: {
    symbol: string;
    direction: 'bullish' | 'bearish';
    entryLow: number;
    entryHigh: number;
    returnPct: number;
    outcome: 'win' | 'loss' | 'breakeven';
    closedAt: string;
  } | null;
  teaser: Array<{
    symbol: string;
    direction: 'bullish' | 'bearish';
    liveStatus: string | null;
  }>;
  activeTotal: number;
  generatedAt: string;
}

async function fetchJson(path: string): Promise<any | null> {
  try {
    const res = await fetch(`${BASE}${path}`, { next: { revalidate: 60 } });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    // Fail-open (fake-data yasağı): hata = alan null; asla uydurma değer, asla 500.
    return null;
  }
}

export async function GET() {
  const [historyRes, activeRes] = await Promise.all([
    // Son KAPANAN sinyal — outcome-filtresiz (anti-cherry-pick kuralı; kayıp da döner).
    // Backend sıralaması: coalesce(closed_at, generated_at) DESC → ilk kayıt = son kapanan.
    fetchJson('/api/v1/signals/history?only_resolved=true&page_size=1'),
    fetchJson('/api/v1/signals?only_actionable=true&page_size=3'),
  ]);

  let lastClosed: LandingProofPayload['lastClosed'] = null;
  const item = historyRes?.items?.[0];
  if (
    item &&
    item.closed_at &&
    typeof item.actual_return === 'number' &&
    (item.outcome === 'win' || item.outcome === 'loss' || item.outcome === 'breakeven') &&
    Date.now() - new Date(item.closed_at).getTime() <= STALE_MS
  ) {
    lastClosed = {
      symbol: item.asset?.symbol ?? '',
      direction: item.direction,
      entryLow: item.entry_zone_low,
      entryHigh: item.entry_zone_high,
      returnPct: item.actual_return,
      outcome: item.outcome,
      closedAt: item.closed_at,
    };
    if (!lastClosed.symbol) lastClosed = null;
  }

  const teaser: LandingProofPayload['teaser'] = (activeRes?.items ?? [])
    .slice(0, 3)
    .map((s: any) => ({
      symbol: s.asset?.symbol ?? '',
      direction: s.direction,
      liveStatus: s.live_status ?? null,
    }))
    .filter((t: { symbol: string }) => t.symbol !== '');

  const payload: LandingProofPayload = {
    lastClosed,
    teaser,
    activeTotal: activeRes?.total ?? 0,
    generatedAt: new Date().toISOString(),
  };

  return NextResponse.json(payload);
}
