"""
Signal lifecycle status.

A signal that hasn't hit TP or SL yet isn't simply "active" — it can be quietly
deteriorating (price drifting back toward the stop, the regime flipping against
it) or building (price pushing toward the first target). The user's real
question is "is this signal still valid right now?", and a binary active/closed
flag can't answer it.

This computes a live status from CHEAP cues only — price position relative to
the trade's own levels, plus the current market regime — so it can run for every
active signal every tracking pass without re-executing the nine-engine suite.

Statuses (terminal states like stopped/reversed are handled by resolution, not
here):
  • approaching_tp — price has travelled most of the way to TP1 in our favour
  • invalidating   — price has retraced most of the way to the stop
  • weakening      — drifting against us, or the regime has turned hostile
  • active         — healthy, thesis intact
"""

from __future__ import annotations

from typing import Optional, Tuple

# Status constants.
ACTIVE = "active"
APPROACHING_TP = "approaching_tp"
WEAKENING = "weakening"
INVALIDATING = "invalidating"

STATUS_TR = {
    ACTIVE: "Aktif",
    APPROACHING_TP: "TP'ye yaklaşıyor",
    WEAKENING: "Zayıflıyor",
    INVALIDATING: "Geçersizleşiyor",
}


def status_tr(status: Optional[str]) -> str:
    if not status:
        return ""
    return STATUS_TR.get(status, status)


# Fraction of the entry→TP1 move that counts as "approaching".
APPROACH_TP_THRESHOLD = 0.6
# Fraction of the entry→SL move that counts as "invalidating".
INVALIDATE_RETRACE_THRESHOLD = 0.6
# Milder retrace that only warrants "weakening".
WEAKEN_RETRACE_THRESHOLD = 0.3


def compute_lifecycle_status(
    *,
    direction: str,
    entry: float,
    stop_loss: float,
    tp1: float,
    current_price: float,
    current_regime: Optional[str] = None,
) -> Tuple[str, str]:
    """Return (status, turkish_reason) for a still-active signal.

    Pure function of the trade's own levels + the latest price and (optional)
    current market regime. Mirrors logic for bullish/bearish.
    """
    is_bull = direction == "bullish"

    dist_to_tp1 = abs(tp1 - entry)
    dist_to_sl = abs(entry - stop_loss)
    if dist_to_tp1 <= 0 or dist_to_sl <= 0 or entry <= 0:
        return ACTIVE, "Seviyeler okunamadı; izlemeye devam."

    # Favourable progress toward TP1 (negative if price went against us).
    if is_bull:
        progress_to_tp = (current_price - entry) / dist_to_tp1
        retrace_to_sl = (entry - current_price) / dist_to_sl
    else:
        progress_to_tp = (entry - current_price) / dist_to_tp1
        retrace_to_sl = (current_price - entry) / dist_to_sl

    regime_hostile = (is_bull and current_regime == "trending_bear") or (
        not is_bull and current_regime == "trending_bull"
    )

    # Order matters: a strong favourable move wins even if regime is noisy.
    if progress_to_tp >= APPROACH_TP_THRESHOLD:
        pct = min(99, int(progress_to_tp * 100))
        return APPROACHING_TP, f"Fiyat TP1 yolunun %{pct}'ini kat etti; hedefe yaklaşıyor."

    if retrace_to_sl >= INVALIDATE_RETRACE_THRESHOLD:
        pct = min(99, int(retrace_to_sl * 100))
        return INVALIDATING, f"Fiyat stop seviyesine doğru %{pct} geri çekildi; tez bozulmak üzere."

    if regime_hostile:
        return WEAKENING, "Piyasa rejimi sinyal yönünün aleyhine döndü."

    if retrace_to_sl >= WEAKEN_RETRACE_THRESHOLD:
        pct = min(99, int(retrace_to_sl * 100))
        return WEAKENING, f"Fiyat girişten stop yönünde %{pct} uzaklaştı; momentum zayıflıyor."

    return ACTIVE, "Tez korunuyor; fiyat giriş bölgesi civarında sağlıklı."
