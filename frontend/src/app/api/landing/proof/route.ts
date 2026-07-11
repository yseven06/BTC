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
  // CP-2 — K-B2+ kanıt bandı: HAM DAĞILIM + TP1 (win_rate/ort.getiri landing'e dönmez).
  // closedTotal = W+L+BE (expired/invalidated süreç-iptalleri hariç — Sicil süzgeciyle tutarlı).
  // N-floor (30) TEK-KAYNAK burada: küçük örneklemde yüzde yanıltıcı → tp1Rate=null (yalnız sayım).
  stats: {
    closedTotal: number;
    winCount: number;
    lossCount: number;
    breakevenCount: number;
    tp1Rate: number | null;
  } | null;
  generatedAt: string;
}

const N_FLOOR = 30;

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
  const [historyRes, activeRes, perfRes] = await Promise.all([
    // Son KAPANAN sinyal — outcome-filtresiz (anti-cherry-pick kuralı; kayıp da döner).
    // Backend sıralaması: coalesce(closed_at, generated_at) DESC → ilk kayıt = son kapanan.
    fetchJson('/api/v1/signals/history?only_resolved=true&page_size=1'),
    fetchJson('/api/v1/signals?only_actionable=true&page_size=3'),
    fetchJson('/api/v1/signals/performance'),
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

  let stats: LandingProofPayload['stats'] = null;
  if (
    perfRes &&
    typeof perfRes.win_count === 'number' &&
    typeof perfRes.loss_count === 'number' &&
    typeof perfRes.breakeven_count === 'number'
  ) {
    const closedTotal = perfRes.win_count + perfRes.loss_count + perfRes.breakeven_count;
    stats = {
      closedTotal,
      winCount: perfRes.win_count,
      lossCount: perfRes.loss_count,
      breakevenCount: perfRes.breakeven_count,
      tp1Rate:
        closedTotal >= N_FLOOR && typeof perfRes.tp1_hit_rate === 'number'
          ? perfRes.tp1_hit_rate
          : null,
    };
  }

  const payload: LandingProofPayload = {
    lastClosed,
    teaser,
    activeTotal: activeRes?.total ?? 0,
    stats,
    generatedAt: new Date().toISOString(),
  };

  return NextResponse.json(payload);
}
