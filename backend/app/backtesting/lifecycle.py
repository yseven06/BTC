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

import pandas as pd

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


# ════════════════════════════════════════════════════════════════════════════
# Lifecycle v2 — structure/momentum confirmation + hysteresis + min-duration
# ════════════════════════════════════════════════════════════════════════════
#
# v1 (above) is a stateless price-vs-levels classifier. v2 keeps that core but:
#   • adds momentum (short-EMA slope) and market-structure (BOS/CHoCH) as
#     CONFIRMING evidence — never as a sole escalator;
#   • requires, for INVALIDATING, price retrace AND (structure break + momentum)
#     together, so a lone structure print can't flip a healthy signal;
#   • applies hysteresis (stricter thresholds to LEAVE a state than to enter)
#     and a minimum state duration, so the status can't flip-flop between passes
#     — escalation toward danger is always immediate, only recovery is damped.

# Enter thresholds (same spirit as v1).
ENTER_APPROACH = 0.60     # progress to TP1
ENTER_INVALIDATE = 0.60   # retrace to SL (pure price)
ENTER_WEAKEN = 0.30       # retrace to SL (mild)
# Confirmed-cluster invalidation: a shallower retrace counts ONLY when a
# structure break against us AND momentum against us both agree.
ENTER_INVALIDATE_CONFIRMED = 0.45

# Exit thresholds — must be crossed back beyond these (stricter) before a state
# is allowed to de-escalate. The gap between enter/exit is the hysteresis band.
EXIT_APPROACH = 0.50
EXIT_INVALIDATE = 0.45
EXIT_WEAKEN = 0.20

# How long a state must be held before recovery (de-escalation) is allowed.
# Escalation ignores this. Default is conservative; the tracker passes a value
# scaled to the timeframe.
DEFAULT_MIN_STATE_SECONDS = 300

_SEVERITY = {ACTIVE: 0, WEAKENING: 1, INVALIDATING: 2}


def momentum_direction(df: pd.DataFrame, span: int = 9, lookback: int = 3) -> str:
    """Short-term momentum lean from the slope of a fast EMA, normalised by
    price. Cheap (no network); computed from the OHLCV the tracker already has.
    Returns 'bullish' | 'bearish' | 'neutral'."""
    if df is None or len(df) < lookback + 2:
        return "neutral"
    close = df["close"]
    ema = close.ewm(span=span, adjust=False).mean()
    last = float(close.iloc[-1]) or 1.0
    slope_rel = (float(ema.iloc[-1]) - float(ema.iloc[-1 - lookback])) / last
    if slope_rel > 0.0005:
        return "bullish"
    if slope_rel < -0.0005:
        return "bearish"
    return "neutral"


def _structure_against(structure_event: Optional[str], is_bull: bool) -> bool:
    """True when the most-recent BOS/CHoCH points opposite the signal."""
    if not structure_event:
        return False
    ev = structure_event.lower()
    if is_bull:
        return ev in ("bos_bearish", "choch_bearish")
    return ev in ("bos_bullish", "choch_bullish")


def _classify_raw(
    *, is_bull: bool, progress_to_tp: float, retrace_to_sl: float,
    regime_hostile: bool, momentum_against: bool, structure_against: bool,
    structure_event: Optional[str],
) -> Tuple[str, str]:
    """v2 raw candidate (pre-hysteresis). Structure is confirmation only."""
    # Favourable move wins outright.
    if progress_to_tp >= ENTER_APPROACH:
        pct = min(99, int(progress_to_tp * 100))
        return APPROACHING_TP, f"Fiyat TP1 yolunun %{pct}'ini kat etti; hedefe yaklaşıyor."

    # INVALIDATING: deep price retrace, OR a shallower retrace CONFIRMED by both
    # a structure break against us and momentum against us. Structure alone can
    # never reach here.
    if retrace_to_sl >= ENTER_INVALIDATE:
        pct = min(99, int(retrace_to_sl * 100))
        return INVALIDATING, f"Fiyat stop seviyesine doğru %{pct} geri çekildi; tez bozulmak üzere."
    if retrace_to_sl >= ENTER_INVALIDATE_CONFIRMED and structure_against and momentum_against:
        choch = "choch" in (structure_event or "").lower()
        kind = "karakter değişimi (CHoCH)" if choch else "yapı kırılımı (BOS)"
        pct = min(99, int(retrace_to_sl * 100))
        return INVALIDATING, (
            f"Fiyat stop yönünde %{pct} çekildi + aleyhte {kind} + momentum aleyhte "
            f"— tez bozuluyor."
        )

    # WEAKENING: any single soft warning. Structure only enriches the reason.
    if regime_hostile or retrace_to_sl >= ENTER_WEAKEN or momentum_against:
        reasons = []
        if regime_hostile:
            reasons.append("rejim aleyhte döndü")
        if retrace_to_sl >= ENTER_WEAKEN:
            reasons.append(f"fiyat stop yönünde %{min(99, int(retrace_to_sl * 100))} çekildi")
        if momentum_against:
            reasons.append("momentum zayıflıyor")
        if structure_against:  # confirmation only
            reasons.append("aleyhte yapı sinyali")
        return WEAKENING, "Sinyal zayıflıyor: " + ", ".join(reasons) + "."

    return ACTIVE, "Tez korunuyor; fiyat giriş bölgesi civarında sağlıklı."


def evaluate_lifecycle(
    *,
    direction: str,
    entry: float,
    stop_loss: float,
    tp1: float,
    current_price: float,
    current_regime: Optional[str] = None,
    structure_event: Optional[str] = None,
    momentum_dir: str = "neutral",
    prev_status: Optional[str] = None,
    seconds_in_state: Optional[float] = None,
    min_state_seconds: float = DEFAULT_MIN_STATE_SECONDS,
) -> Tuple[str, str]:
    """v2 lifecycle: raw classify + hysteresis + min-duration.

    Returns (status, turkish_reason). Pure function — the tracker supplies
    prev_status and seconds_in_state (from live_status_since) and persists the
    result. Escalation toward danger is immediate; recovery is gated.
    """
    is_bull = direction == "bullish"
    dist_to_tp1 = abs(tp1 - entry)
    dist_to_sl = abs(entry - stop_loss)
    if dist_to_tp1 <= 0 or dist_to_sl <= 0 or entry <= 0:
        return ACTIVE, "Seviyeler okunamadı; izlemeye devam."

    if is_bull:
        progress_to_tp = (current_price - entry) / dist_to_tp1
        retrace_to_sl = (entry - current_price) / dist_to_sl
    else:
        progress_to_tp = (entry - current_price) / dist_to_tp1
        retrace_to_sl = (current_price - entry) / dist_to_sl

    regime_hostile = (is_bull and current_regime == "trending_bear") or (
        not is_bull and current_regime == "trending_bull"
    )
    momentum_against = (is_bull and momentum_dir == "bearish") or (
        not is_bull and momentum_dir == "bullish"
    )
    structure_against = _structure_against(structure_event, is_bull)

    candidate, reason = _classify_raw(
        is_bull=is_bull, progress_to_tp=progress_to_tp, retrace_to_sl=retrace_to_sl,
        regime_hostile=regime_hostile, momentum_against=momentum_against,
        structure_against=structure_against, structure_event=structure_event,
    )

    # First evaluation or unchanged → take candidate as-is.
    if prev_status is None or prev_status == candidate:
        return candidate, reason

    # APPROACHING_TP is unambiguous good news — enter immediately.
    if candidate == APPROACHING_TP:
        return candidate, reason

    # Leaving APPROACHING_TP: hold until min-duration AND progress falls back
    # below the exit band.
    if prev_status == APPROACHING_TP:
        held_long_enough = seconds_in_state is None or seconds_in_state >= min_state_seconds
        if not held_long_enough or progress_to_tp >= EXIT_APPROACH:
            pct = min(99, int(max(progress_to_tp, 0) * 100))
            return APPROACHING_TP, f"Fiyat TP1 yolunun %{pct}'inde; hedefe yakınlığını koruyor."
        return candidate, reason

    # Both prev and candidate on the {active,weakening,invalidating} axis.
    prev_sev = _SEVERITY.get(prev_status, 0)
    cand_sev = _SEVERITY.get(candidate, 0)

    # Escalation toward danger — apply immediately (safety first).
    if cand_sev > prev_sev:
        return candidate, reason

    # De-escalation (recovery) — gated by min-duration + hysteresis exit bands.
    if seconds_in_state is not None and seconds_in_state < min_state_seconds:
        return prev_status, _hold_reason(prev_status)

    if prev_status == INVALIDATING and retrace_to_sl >= EXIT_INVALIDATE:
        return prev_status, _hold_reason(prev_status)

    if prev_status == WEAKENING:
        recovered = (
            retrace_to_sl < EXIT_WEAKEN
            and not regime_hostile
            and not momentum_against
        )
        if not recovered:
            return prev_status, _hold_reason(prev_status)

    return candidate, reason


def _hold_reason(status: str) -> str:
    if status == INVALIDATING:
        return "Tez hâlâ riskli; toparlanma teyidi bekleniyor."
    if status == WEAKENING:
        return "Zayıflık sürüyor; net toparlanma teyidi bekleniyor."
    return "İzlemeye devam."
