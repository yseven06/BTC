"""Canonical entry level and entry activation — CP-ENTRY-ACTIVATION-GATE.

TWO components, deliberately separate. Conflating them was the one clause of the
requested architecture the code refused: three of the twelve midpoint sites have
no bars to consult (``tracker.py:1132`` derives the level inside the function
that RETURNS the DataFrame; ``tracker.py:675`` runs before ``df_after`` exists;
``tracker.py:1110`` is on the ticker path, where a bar frame does not exist by
construction). A single helper would have to be callable with no evidence, which
is exactly the shape that turns an absence of data into a False verdict.

  1. :func:`entry_level` — pure arithmetic, callable anywhere, no evidence needed.
  2. :func:`entry_activation` — the gate, callable only where evidence exists.

VALUE IDENTITY (the reason :func:`entry_level` is unflagged). The repo carries
TWO spellings of the midpoint and they are not interchangeable in general:

    Form A   float(hi + lo) / 2.0        operands are Decimal — one rounding
    Form B   (float(lo) + float(hi))/2.0 operands are float  — two roundings

``Decimal('0.1') + Decimal('0.2')`` is exactly ``Decimal('0.3')``; the float sum
of the same two values is ``0.30000000000000004``. So the forms can differ in the
last ulp. ``float(high + low) / 2.0`` reproduces BOTH exactly, provided each call
site keeps passing the operand types it passes today:

  * Decimal operands → ``high + low`` stays exact, ``float()`` rounds once  → Form A
  * float operands   → ``high + low`` is the float sum, ``float()`` is a no-op,
    and IEEE-754 addition is commutative                                    → Form B

That property is the whole justification for centralising without a flag, so it
is pinned by test rather than asserted here.

THE GATE returns one of three closed statuses and never invents a fourth. The
vocabulary is deliberately identical to ``app/services/entry_validity.py`` — one
dictionary for the write side and the read side, not two that drift.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Tuple

ENTRY_ACTIVATION_VERSION = "entry_activation_v1"

# --- statuses (must match app/services/entry_validity.py verbatim) -----------
STATUS_REACHED = "reached"
STATUS_NOT_REACHED = "not_reached"
STATUS_UNKNOWN = "unknown"
CANONICAL_STATUSES = (STATUS_REACHED, STATUS_NOT_REACHED, STATUS_UNKNOWN)

# --- how the fill was proved -------------------------------------------------
PROOF_BAR = "bar"              # a post-birth bar's low/high reached the level
PROOF_OPEN_GAP = "open_gap"    # the bar OPENED beyond the level (gap through)
PROOF_LIVE_STOP = "live_stop"  # ticker path: the stop broke, so the entry was crossed first
PROOF_NONE = "none"            # not proved

# --- why the gate could not decide ------------------------------------------
UNKNOWN_NO_BARS = "no_post_birth_bars"
UNKNOWN_WINDOW_INCOMPLETE = "observation_window_incomplete"


def entry_level(entry_zone_low: Any, entry_zone_high: Any) -> float:
    """The canonical assumed entry: the entry-zone midpoint ("Reading A").

    Pass the operands in the types the call site already uses — see the module
    docstring. Doing the addition BEFORE the float() conversion is load-bearing,
    not stylistic.
    """
    return float(entry_zone_high + entry_zone_low) / 2.0


def _touched(is_bull: bool, level: float, high: float, low: float) -> bool:
    """Did this bar reach the entry level? INCLUSIVE — touching exactly counts.

    Mirrors ``entry_telemetry.py:88`` (``lows <= entry_level`` for a long) so the
    gate and the passive detector can never disagree about the same bar.
    """
    return (low <= level) if is_bull else (high >= level)


def _gapped(is_bull: bool, level: float, open_: Optional[float]) -> Optional[bool]:
    """Did the bar OPEN already beyond the level (a gap straight through)?

    Detection is unaffected — a gapping bar's low/high still crosses the level —
    so this is recorded, not acted on. The fill price stays the level (locked
    decision 3), matching how stops and targets are already priced.
    """
    if open_ is None:
        return None
    return (open_ < level) if is_bull else (open_ > level)


def entry_activation(
    *,
    is_bull: bool,
    level: float,
    highs: Optional[Sequence[float]] = None,
    lows: Optional[Sequence[float]] = None,
    opens: Optional[Sequence[float]] = None,
    window_complete: bool = False,
    live_stop_breached: bool = False,
) -> Dict[str, Any]:
    """Decide whether price provably reached ``level``, over the bars given.

    ``highs``/``lows`` are the POST-BIRTH frame — bars strictly after
    ``generated_at`` with the still-forming birth candle collapsed to
    ``high=low=close`` (``tracker.py:283`` and ``:308-311``). The frame is the
    caller's; this function does not build one.

    ``live_stop_breached`` is the ticker channel. It is a PROOF of entry, not a
    bypass: the stop sits beyond the entry (the generator forces
    ``stop_loss < entry_zone_low`` for a long, ``signal_generator.py:390-391``),
    so price reaching the stop must have crossed the entry level on the way. The
    same argument does NOT hold for a target, which is why only the stop counts.

    ``window_complete=False`` means the observation window does not reach back to
    the signal's birth. A "never reached" verdict is a claim about bars we do not
    have, so an incomplete window yields ``unknown`` — never ``not_reached``.
    """
    out: Dict[str, Any] = {
        "version": ENTRY_ACTIVATION_VERSION,
        "status": STATUS_UNKNOWN,
        "proof": PROOF_NONE,
        "entry_pos": None,
        "bars_to_entry": None,
        "gapped_entry": None,
        "window_complete": bool(window_complete),
        "unknown_reason": None,
    }

    # The ticker channel needs no bars, so it is answered first.
    if live_stop_breached:
        out["status"] = STATUS_REACHED
        out["proof"] = PROOF_LIVE_STOP
        return out

    if not highs or not lows or len(highs) != len(lows):
        out["unknown_reason"] = UNKNOWN_NO_BARS
        return out

    for i in range(len(lows)):
        if not _touched(is_bull, level, float(highs[i]), float(lows[i])):
            continue
        open_ = float(opens[i]) if (opens is not None and i < len(opens)) else None
        gapped = _gapped(is_bull, level, open_)
        out["status"] = STATUS_REACHED
        out["proof"] = PROOF_OPEN_GAP if gapped else PROOF_BAR
        out["entry_pos"] = i
        out["bars_to_entry"] = i + 1     # 1-based, matching entry_telemetry.py:95
        out["gapped_entry"] = bool(gapped) if gapped is not None else None
        return out

    if window_complete:
        out["status"] = STATUS_NOT_REACHED
        out["gapped_entry"] = False
        return out

    out["unknown_reason"] = UNKNOWN_WINDOW_INCOMPLETE
    return out


def walk_start(
    entry_bar: Optional[Sequence[float]],
    entry_pos: int,
    entry_mid: float,
    sl: float,
    is_bull: bool,
) -> Tuple[int, bool, bool]:
    """Where the TP/SL walk may begin, and whether the entry bar was provable.

    PROMOTED VERBATIM from ``shadow_eval._walk_start`` so the live path and the
    shadow evaluator consume one implementation instead of two copies. Returns
    ``(start_index, entry_bar_walked, tp_withheld)``.

    THE PROBLEM. The fill instant on the entry bar is defined by that bar's LOW
    for a long and its HIGH for a short. The take profits are then tested against
    the SAME bar's high/low. OHLC carries no intra-bar ordering, so a bar that
    both reaches the entry and reaches a TP cannot say which came first — and
    crediting the TP would book profit on movement that may have happened before
    anyone was in the trade. The bias is one-sided, so it inflates return, R,
    TP-reach, expectancy and PF rather than adding symmetric noise.

    TWO EXCEPTIONS, BOTH PROVED RATHER THAN ASSUMED.

    1. THE FILL IS CERTAIN AT THE OPEN. Long: ``open <= entry_mid`` means price
       was already at or through the entry at the bar's first tick, so the fill
       is the open and every subsequent tick in that bar is post-fill.

    2. THE STOP IS CERTAIN EVEN WHEN THE FILL TIME IS NOT. Long: the stop sits
       BELOW the entry. If the bar's low reaches the stop then price was, at that
       instant, below the entry too; by continuity it must have crossed the entry
       on the way down, and the fill fires the first time price touches it. So
       the fill necessarily precedes the stop. The same argument does NOT hold
       for a take profit, because a TP sits on the far side of the entry from the
       stop: reaching it does not require having crossed the entry first. That
       asymmetry is the whole reason this function exists.

    Otherwise the entry bar is skipped and the walk starts on the next one.
    Skipping loses that bar's MFE/MAE, which is the conservative direction:
    unattributable extrema are dropped rather than credited.

    Pure and total: no I/O, no clock, and every branch returns.
    """
    if entry_bar is None:
        return entry_pos, False, False

    o, h, l = entry_bar[0], entry_bar[1], entry_bar[2]

    # Exception 1 — fill certain at the open.
    if (o <= entry_mid) if is_bull else (o >= entry_mid):
        return entry_pos, True, False

    # Exception 2 — stop causally certain on the entry bar.
    if (l <= sl) if is_bull else (h >= sl):
        return entry_pos, True, False

    # Neither holds: any TP on this bar is unprovable, so the bar is not walked.
    return entry_pos + 1, False, True
