"""
Detailed outcome labeling.

A signal's coarse outcome (WIN / LOSS / BREAKEVEN / EXPIRED) hides the lesson.
Two losses can mean opposite things:

  • direction was simply wrong (price went the other way immediately), vs.
  • direction was right but the stop was too tight (price ran most of the way
    to TP1, then a normal pullback clipped the stop).

Only the second is a stop-placement problem. The CoinMemory learning layer
needs that distinction to adjust *how* it trades a coin, not just whether the
engines agreed. These pure functions turn the numbers the tracker already
computes into a single human-meaningful label.
"""

from __future__ import annotations


# Detail labels (stored as plain strings on SignalPerformance.detail_label).
TP3_HIT = "tp3_hit"
TP2_HIT = "tp2_hit"
TP1_HIT = "tp1_hit"
TP1_THEN_BREAKEVEN = "tp1_then_breakeven"
SL_HIT = "sl_hit"
CORRECT_DIR_TIGHT_SL = "correct_dir_tight_sl"
LIVE_SL_HIT = "live_sl_hit"
EXPIRED_PROFIT = "expired_profit"
EXPIRED_LOSS = "expired_loss"
EXPIRED_FLAT = "expired_flat"
INVALIDATED_REVERSAL = "invalidated_reversal"

# Human-readable Turkish labels for the UI / explanations.
LABEL_TR = {
    TP3_HIT: "TP3 geldi",
    TP2_HIT: "TP2 geldi",
    TP1_HIT: "TP1 geldi",
    TP1_THEN_BREAKEVEN: "TP1 sonrası başabaşta kapandı",
    SL_HIT: "Stop oldu",
    CORRECT_DIR_TIGHT_SL: "Yön doğruydu ama stop dardı",
    LIVE_SL_HIT: "Anlık fiyatta stop oldu",
    EXPIRED_PROFIT: "Süre doldu (kârda)",
    EXPIRED_LOSS: "Süre doldu (zararda)",
    EXPIRED_FLAT: "Süre doldu (yatay)",
    INVALIDATED_REVERSAL: "Ters sinyalle geçersiz oldu",
}


def label_tr(detail: str | None) -> str:
    """Turkish display string for a detail label (passthrough if unknown)."""
    if not detail:
        return ""
    return LABEL_TR.get(detail, detail)


# ── Resolution provenance (F1-d) ────────────────────────────────────────────
# Stamped on SignalPerformance.resolution_version by every writer path that
# closes a performance row. ONE monotonic integer for the RESOLUTION semantics
# as a whole: the classifier's branches and thresholds below, the ±0.5%
# WIN/LOSS outcome cut in the tracker, and the booking math (bar-walk ladder,
# live-SL scale-out). BUMP when any of those changes meaning; adding a new
# writer path or a new label is NOT a bump — rows already say which path wrote
# them via resolution_source. NULL on a row = written before stamping existed;
# never backfilled, never guessed. Known pre-stamp sub-eras, documented for
# analysts but NEVER stamped: <06-22 unlabeled, <06-30 pre-KEY1-d scale-out,
# <07-16 pre-F0-1H fresh-flag re-read.
#
# v1 = the post-F0-1H / F0-1A era: KEY1-d ladder honored, live-SL flags re-read
#      from this pass's bars, hit_time/detected_at split recorded.
RESOLUTION_SEMANTICS_VERSION = 1

# Writer-path identities for SignalPerformance.resolution_source — WHICH of
# the seven paths closed the row. Deliberately the same name and value family
# as trade_path.extra["resolution_source"] (bar_walk | live_sl | expiry), but
# stamped on the source of truth: trade-path rows are fail-open and cover only
# the three tracker paths.
RES_SRC_BAR_WALK = "bar_walk"
RES_SRC_LIVE_SL = "live_sl"
RES_SRC_EXPIRY = "expiry"
RES_SRC_HOLD_EXPIRY = "hold_expiry"
RES_SRC_REVERSAL = "reversal"
RES_SRC_ADMIN_INVALIDATE = "admin_invalidate"
RES_SRC_ADMIN_BULK_CLEAN = "admin_bulk_clean"


# Fraction of the entry→TP1 distance price must travel in our favour for a
# stop-out to count as "right direction, stop too tight" rather than a plain
# wrong call. 0.5 = price got at least halfway to the first target first.
TIGHT_SL_MFE_THRESHOLD = 0.5


def classify_resolution(
    *,
    hit_tp1: bool,
    hit_tp2: bool,
    hit_tp3: bool,
    resolved_by_sl: bool,
    is_expired: bool,
    pnl_pct: float,
    mfe_pct: float,
    entry: float,
    tp1: float,
) -> str:
    """Return the detail label for a fully-resolved signal.

    Args:
        hit_tp1/2/3: Which targets were reached.
        resolved_by_sl: True if the trade closed on a stop (incl. breakeven
            stop after a TP1 scale-out).
        is_expired: True if it closed at the 48h expiry instead of TP/SL.
        pnl_pct: Realised return (%).
        mfe_pct: Max favorable excursion (% of entry).
        entry / tp1: Prices, to measure how close MFE got to the first target.
    """
    # Targets take precedence — reaching a TP is the headline regardless of how
    # it later closed.
    if hit_tp3:
        return TP3_HIT
    if hit_tp2:
        return TP2_HIT
    if hit_tp1:
        # TP1 reached: was the rest ridden to profit, or stopped at breakeven?
        return TP1_HIT if pnl_pct > 0.5 else TP1_THEN_BREAKEVEN

    if is_expired:
        if pnl_pct > 0.5:
            return EXPIRED_PROFIT
        if pnl_pct < -0.5:
            return EXPIRED_LOSS
        return EXPIRED_FLAT

    if resolved_by_sl:
        # Did price get most of the way to TP1 before reversing into the stop?
        tp1_distance = abs(tp1 - entry)
        if tp1_distance > 0 and entry > 0:
            mfe_price_move = (mfe_pct / 100.0) * entry
            if mfe_price_move >= TIGHT_SL_MFE_THRESHOLD * tp1_distance:
                return CORRECT_DIR_TIGHT_SL
        return SL_HIT

    # Fallback — shouldn't normally hit, but never return None.
    return SL_HIT if pnl_pct < 0 else EXPIRED_FLAT
