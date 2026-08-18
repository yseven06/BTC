"""SHADOW execution-cost evidence. Observes; never decides.

WHY THIS EXISTS
---------------
CP-D established that this system places no orders. There is no order-placement
code, no fee configuration, and `portfolio_holdings` has never held a row. So for
every historical signal the actual fill price, the actual commission and the
actual slippage are UNAVAILABLE — not missing by accident, but absent because the
trade never happened. No amount of re-analysis can recover them.

What CAN still be captured, going forward, is the market's QUOTED state at the
moment a signal becomes visible. CP-C found a candidate cohort (`sl_dist_pct`
below a frozen threshold) whose out-of-sample expectancy survived an ASSUMED flat
cost; CP-D measured real spreads and found the edge fragile rather than dead. The
missing evidence is spread at decision time, per signal. This module records it.

WHAT THIS IS NOT
----------------
It is not a filter. The predicates below are computed and stored so that a future
analysis can ask "what would this rule have done", and nothing in the application
may branch on them — `test_predicates_are_evaluated_but_never_consulted_by_a_decision`
enforces that across the whole of `app/`.

It also does not compute a net expectancy. Storing one would freeze today's fee
guess into tomorrow's analysis; the raw bid/ask and depth are kept instead, so any
future fee assumption can be applied to the same evidence.

FAILURE IS ALWAYS OPEN
----------------------
A publication must never depend on an exchange being reachable. Every failure
path returns a record whose `market.ok` is False with a reason, and a failed
snapshot is deliberately NOT representable as a zero spread — the two would
otherwise be indistinguishable in the data, and "the book was tight" is a very
different fact from "we could not look".
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

# FROZEN by CP-C, which measured them out of sample across five chronological
# folds. They are recorded here so a later analysis can evaluate the same rules
# it already validated; re-tuning them against shadow data collected afterwards
# would be fitting a threshold to its own test set.
FROZEN_SL_DIST_THRESHOLDS = (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0, 1.2)

# A HARD bound with no retry. This call happens while the publication
# transaction is open, so an unbounded fetch would hold that transaction across
# the network — the precise antipattern `idle_in_transaction_session_timeout`
# exists to catch. One attempt, briefly, then give up and record the failure.
SNAPSHOT_TIMEOUT_SECONDS = 2.0

# Depth is recorded at these distances from mid so a later analysis can model
# market impact for a notional this system does not have. Raw evidence, not a
# slippage estimate: nothing here has been executed against.
DEPTH_BANDS_PCT = (0.05, 0.10, 0.25)

# Where each field comes from. Asserted by tests rather than left to a comment,
# because the whole value of this record is that the reader can tell a
# measurement from an assumption.
PROVENANCE = {
    "bid": "MEASURED",
    "ask": "MEASURED",
    "spread_pct": "MEASURED",
    "depth": "MEASURED",
    "sl_dist_pct": "DERIVED",
    "atr_pct": "DERIVED",
    "entry_geometry": "DERIVED",
    "fee_rate": "ASSUMED",
    "actual_fill_price": "UNAVAILABLE",
    "actual_commission": "UNAVAILABLE",
    "actual_slippage": "UNAVAILABLE",
}


def _f(v) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _sl_dist_pct(signal) -> Optional[float]:
    """Stop distance as a percentage of the assumed entry.

    DERIVED, and derived the same way the rest of the P&L machinery already
    does it: from the entry-zone midpoint. That midpoint is an assumption about
    where a fill would have happened, never an observation of one — which is
    exactly why `actual_fill_price` stays UNAVAILABLE above.
    """
    lo, hi, sl = _f(signal.entry_zone_low), _f(signal.entry_zone_high), _f(signal.stop_loss)
    if lo is None or hi is None or sl is None:
        return None
    mid = (lo + hi) / 2
    if mid <= 0:
        return None
    return abs(mid - sl) / mid * 100


def _failed_market(reason: str) -> Dict[str, Any]:
    """A snapshot that did not happen. `spread_pct` is None rather than 0.0 so a
    failure can never be aggregated as if it were a tight book."""
    return {"ok": False, "failure_reason": reason, "bid": None, "ask": None,
            "spread_abs": None, "spread_pct": None, "depth": None}


async def _snapshot_market(collector, symbol: str) -> Dict[str, Any]:
    try:
        book = await asyncio.wait_for(collector.fetch_orderbook(symbol),
                                      timeout=SNAPSHOT_TIMEOUT_SECONDS)
    except (asyncio.TimeoutError, TimeoutError):
        return _failed_market("timeout")
    except Exception as exc:                                    # noqa: BLE001
        return _failed_market(f"{type(exc).__name__}: {exc}"[:120])

    if not isinstance(book, dict):
        return _failed_market("malformed_response")
    bids, asks = book.get("bids") or [], book.get("asks") or []
    if not bids or not asks:
        return _failed_market("empty_book")
    bid, ask = _f(bids[0][0]), _f(asks[0][0])
    if bid is None or ask is None or bid <= 0 or ask <= 0:
        return _failed_market("non_positive_quote")
    if bid > ask:
        # A crossed book is not a negative spread, it is bad data.
        return _failed_market("crossed_book")

    mid = (bid + ask) / 2
    depth: Dict[str, Dict[str, float]] = {}
    for band in DEPTH_BANDS_PCT:
        bid_notional = ask_notional = 0.0
        for p, q in bids:
            p, q = _f(p), _f(q)
            if p is None or q is None or p < mid * (1 - band / 100):
                break
            bid_notional += p * q
        for p, q in asks:
            p, q = _f(p), _f(q)
            if p is None or q is None or p > mid * (1 + band / 100):
                break
            ask_notional += p * q
        depth[f"within_{band}pct"] = {"bid_notional": bid_notional,
                                      "ask_notional": ask_notional}
    return {"ok": True, "failure_reason": None, "bid": bid, "ask": ask,
            "spread_abs": ask - bid, "spread_pct": 100 * (ask - bid) / mid,
            "depth": depth}


async def build_shadow_exec_cost(*, collector, symbol: str, signal,
                                 atr_pct: Optional[float] = None) -> Dict[str, Any]:
    """Build one shadow record. Pure with respect to the database: this returns
    a dict, and the caller stores it inside the transaction it already owns.

    NEVER RAISES. A publication that failed because a shadow measurement failed
    would be the single worst outcome this module could produce, so every path
    returns a record — including the paths where nothing could be measured.
    """
    try:
        market = await _snapshot_market(collector, symbol)
    except Exception as exc:                                    # noqa: BLE001
        log.warning("shadow exec-cost snapshot failed for %s: %s", symbol, exc)
        market = _failed_market(f"unexpected: {type(exc).__name__}"[:120])

    sd = _sl_dist_pct(signal)
    predicates = {f"sl_dist_lt_{x}": (sd is not None and sd < x)
                  for x in FROZEN_SL_DIST_THRESHOLDS}

    return {
        "schema_version": 1,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "timeframe": getattr(signal, "timeframe", None) and str(signal.timeframe),
        "direction": getattr(signal, "direction", None) and str(signal.direction),
        "derived": {
            "sl_dist_pct": sd,
            "atr_pct": _f(atr_pct),
            "confidence": _f(getattr(signal, "confidence_score", None)),
            "entry_zone_low": _f(signal.entry_zone_low),
            "entry_zone_high": _f(signal.entry_zone_high),
            "stop_loss": _f(signal.stop_loss),
            "tp1": _f(getattr(signal, "tp1", None)),
            "tp2": _f(getattr(signal, "tp2", None)),
            "tp3": _f(getattr(signal, "tp3", None)),
        },
        "market": market,
        # Recorded, never consulted. `would_keep` is the answer to a question a
        # future analysis will ask; it is not an instruction to anything.
        "predicates": predicates,
        "provenance": dict(PROVENANCE),
    }
