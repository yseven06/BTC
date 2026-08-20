"""Publication-time observation evidence — CP-SIGNAL-SHADOW-OBSERVABILITY-V1.

WHAT THIS ADDS, AND WHY IT IS SO SMALL. Almost everything an analyst needs is
already persisted. `signal_decision_candidates` holds one scored row per asset
per timeframe per closed bar — published, dropped AND skipped — carrying the
demotion reason, the engine score vector, the weights, the regime and the full
geometry. `signal_trade_path` already resolves MAE, MFE, first touches and the
bar indices for both. `exec_cost` already measures the book at publication. None
of that is copied here; copying is how a second source of truth is born.

Exactly one thing was missing and could not be reconstructed faithfully later:
HOW FAR PRICE HAD ALREADY RUN when the signal was published. It is *partially*
recoverable by joining neighbouring candidate rows, but only from `last_close` —
close granularity, no intrabar extreme, and only while those rows survive. The
frame the engines were scored on is in memory at publication and carries the
true highs and lows, so freezing the statistic here is both cheaper and strictly
more accurate than any later reconstruction.

WHAT MAKES IT SAFE. This builder is PURE and SYNCHRONOUS. It performs no I/O, so
it cannot delay a publication, cannot hold the transaction open, cannot leak a
client and needs no timeout — there is nothing to time out. It never raises: a
malformed frame produces a record that says so. And it never states as measured
anything this product does not measure. The system places no orders, so fills,
commissions and slippage are UNAVAILABLE here and always will be.

READING THE RECORD LATER. `link` carries the key back to the candidate row, so
"which gate was blocking this an hour earlier" is a join, not a guess.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

OBSERVATION_SCHEMA_VERSION = 1

# Bounded on purpose. An unbounded lookback would mean a different statistic on
# every timeframe and every frame length; 96 bars is one day of 15m bars and the
# analysis frame holds 100, so the answer is stable rather than incidental.
LOOKBACK_BARS = 96

_TAXONOMY: Dict[str, str] = {
    # The bars themselves come off the exchange.
    "lookback_high": "MEASURED",
    "lookback_low": "MEASURED",
    "last_close": "MEASURED",
    # Everything computed from them is derived, and says so.
    "extension_from_low_pct": "DERIVED",
    "extension_from_high_pct": "DERIVED",
    "extension_from_low_atr": "DERIVED",
    "extension_from_high_atr": "DERIVED",
    "range_position_pct": "DERIVED",
    "high_low_span_pct": "DERIVED",
    "bars_since_low": "DERIVED",
    "bars_since_high": "DERIVED",
    # This product publishes advice and places no orders. These are not gaps to
    # be filled in later; they are structurally absent.
    "actual_fill_price": "UNAVAILABLE",
    "actual_commission": "UNAVAILABLE",
    "actual_slippage": "UNAVAILABLE",
}

_EMPTY_LOOKBACK: Dict[str, Any] = {
    "ok": False,
    "failure_reason": None,
    "bars_used": 0,
    "first_bar_time": None,
    "last_bar_time": None,
    "last_close": None,
    "high": None,
    "low": None,
    "high_bar_time": None,
    "low_bar_time": None,
    "bars_since_high": None,
    "bars_since_low": None,
    "extension_from_low_pct": None,
    "extension_from_high_pct": None,
    "extension_from_low_atr": None,
    "extension_from_high_atr": None,
    "range_position_pct": None,
    "high_low_span_pct": None,
}


def _f(value: Any) -> Optional[float]:
    """A float, or None. Never a NaN and never a numpy scalar: this record goes
    into a JSON column, where `float('nan')` serialises to invalid JSON."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and out not in (float("inf"), float("-inf")) else None


def _failed(reason: str) -> Dict[str, Any]:
    out = dict(_EMPTY_LOOKBACK)
    out["failure_reason"] = reason
    return out


def _lookback(bars: Any, atr_pct: Optional[float],
              atr_fallback_used: bool) -> Dict[str, Any]:
    """The one genuinely new statistic: where publication sat inside the move
    that preceded it."""
    for attr in ("empty", "columns", "index"):
        if not hasattr(bars, attr):
            return _failed("bars_not_a_frame")
    try:
        if bars.empty:
            return _failed("empty_frame")
        needed = ("high", "low", "close")
        if any(c not in bars.columns for c in needed):
            return _failed("missing_price_columns")

        # Only the tail is consulted, and only up to the final row. Nothing in
        # this function can reach past the bar it was handed, which is what
        # makes the record reproducible from a truncated frame.
        tail = bars.iloc[-LOOKBACK_BARS:]
        n = len(tail)
        if n < 2:
            return _failed("insufficient_bars")

        highs = [_f(v) for v in tail["high"].tolist()]
        lows = [_f(v) for v in tail["low"].tolist()]
        last_close = _f(tail["close"].iloc[-1])
        if last_close is None or any(v is None for v in highs) or any(v is None for v in lows):
            return _failed("non_numeric_prices")

        hi = max(highs)
        lo = min(lows)
        hi_i = max(range(n), key=lambda i: highs[i])
        lo_i = min(range(n), key=lambda i: lows[i])

        span = hi - lo
        ext_low = ((last_close - lo) / lo * 100.0) if lo > 0 else None
        ext_high = ((hi - last_close) / hi * 100.0) if hi > 0 else None

        # An ATR-normalised number divided by a SUBSTITUTED ATR looks measured
        # and is not — the risk engine falls back to a flat 2% when ATR is NaN.
        # The percentage stays honest either way, so only the normalisation is
        # withheld.
        atr = _f(atr_pct)
        usable_atr = atr if (atr and atr > 0 and not atr_fallback_used) else None

        return {
            "ok": True,
            "failure_reason": None,
            "bars_used": n,
            "first_bar_time": str(tail.index[0]),
            "last_bar_time": str(tail.index[-1]),
            "last_close": last_close,
            "high": hi,
            "low": lo,
            "high_bar_time": str(tail.index[hi_i]),
            "low_bar_time": str(tail.index[lo_i]),
            "bars_since_high": n - 1 - hi_i,
            "bars_since_low": n - 1 - lo_i,
            "extension_from_low_pct": ext_low,
            "extension_from_high_pct": ext_high,
            "extension_from_low_atr": (ext_low / usable_atr)
            if (usable_atr and ext_low is not None) else None,
            "extension_from_high_atr": (ext_high / usable_atr)
            if (usable_atr and ext_high is not None) else None,
            "range_position_pct": ((last_close - lo) / span * 100.0) if span > 0 else None,
            "high_low_span_pct": (span / lo * 100.0) if lo > 0 else None,
        }
    except Exception as exc:                      # noqa: BLE001 — evidence never raises
        return _failed(f"{type(exc).__name__}")


def build_shadow_observation(*, symbol: Any, timeframe: Any, signal: Any, bars: Any,
                             atr_pct: Any = None, atr_fallback_used: bool = False,
                             evaluated_bar_time: Any = None) -> Dict[str, Any]:
    """Freeze the publication-time context that cannot be recovered later.

    `signal` is accepted so the record can be built at the publication site
    without reordering anything, and deliberately not read: its geometry is
    already a column on the row itself and on the candidate row.
    """
    lookback = _lookback(bars, atr_pct, bool(atr_fallback_used))
    provenance = dict(_TAXONOMY)
    if lookback["extension_from_low_atr"] is None:
        provenance["extension_from_low_atr"] = "UNAVAILABLE"
        provenance["extension_from_high_atr"] = "UNAVAILABLE"
    return {
        "schema_version": OBSERVATION_SCHEMA_VERSION,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "link": {
            "symbol": symbol if isinstance(symbol, str) else None,
            "timeframe": timeframe if isinstance(timeframe, str) else None,
            # The join key defaults to the frame's last CLOSED bar, because that
            # is precisely what candidate_log stamps as `evaluated_bar_time`
            # (it is handed the same closed frame and takes its final index).
            # Leaving this null would make `link` decorative: a join key that is
            # absent on every row cannot be joined on.
            "evaluated_bar_time": evaluated_bar_time
            if isinstance(evaluated_bar_time, str) else lookback["last_bar_time"],
            # Named so the join is discoverable from the record alone.
            "candidate_table": "signal_decision_candidates",
        },
        "lookback": lookback,
        "provenance": provenance,
    }


def extension_atr(bars: Any, atr_pct: Any, direction: Any, *,
                  atr_fallback_used: bool = False) -> Optional[float]:
    """How far price has run from the lookback extreme, in ATR, for `direction`.

    Exposed so the reset-lifecycle telemetry can reuse THIS computation instead
    of growing a second one. A second implementation of the same statistic is how
    two numbers that should agree quietly stop agreeing; it is also why the
    guarded field names stay inside this module rather than spreading.

    None when the frame cannot support the statistic, or when ATR was the risk
    engine's substituted constant — dividing by that produces a value that looks
    measured and is not.
    """
    lb = _lookback(bars, atr_pct, bool(atr_fallback_used))
    if not lb.get("ok"):
        return None
    bullish = str(direction).lower() in ("bullish", "buy", "long")
    return lb["extension_from_low_atr"] if bullish else lb["extension_from_high_atr"]
