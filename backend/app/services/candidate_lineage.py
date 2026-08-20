"""Opportunity lineage identity for decision candidates — CP-J.

THE PROBLEM. Reset / anti-chase analysis has to tell "this same setup, evaluated
again" apart from "a different setup that happens to share symbol, timeframe and
direction". Matching on that tuple does not: across 121,109 historical pairs,
97.2% had the earlier opportunity ALREADY terminal before the later candidate
existed. Every reset conclusion built on that matching was therefore measuring
new setups, not resets.

THE CONTRACT (ratified before this module was written).

  BEGIN      directional + structurally eligible + no continuable predecessor
             → a fresh opaque UUID.
  CONTINUE   the predecessor for the same asset+timeframe carries a lineage, its
             direction matches, and no authoritative termination intervened
             → reuse its identity.
  TERMINATE  neutral · direction flip · lost structural eligibility · the
             specifically anchored active signal no longer ACTIVE · the safety
             ceiling.

NEUTRAL TERMINATES, AND THAT IS A CHOICE, NOT A MEASUREMENT. Phase 2 looked for a
natural boundary in neutral-gap length and geometry displacement and found none:
the distribution is smooth and unimodal, with 18.3% of strictly contiguous bars
moving the entry zone more than 1 ATR and 38% of gaps beyond 8 bars moving it
less. Since no boundary exists to detect, the rule errs deliberately toward
false-NEW. Fragmentation costs observations; aliasing corrupts conclusions.

WHY IT IS RESTART-SAFE. Identity is resolved entirely from persisted rows. There
is no cache and no module state, so nothing can be lost — or wrongly inherited —
when the process dies mid-opportunity.

WHY IT CANNOT SEE THE FUTURE. `decide_lineage` accepts only what the write path
already knows at that bar. Outcomes, entries and expiries are not parameters, so
they cannot leak in later without changing the signature a test pins.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import select

from app.models.decision_candidate import SignalDecisionCandidate

logger = logging.getLogger(__name__)

_UNSET = object()

LINEAGE_NAMESPACE = "opportunity_lineage_v1"
LINEAGE_SCHEMA_VERSION = 1

STATE_BEGIN = "begin"
STATE_CONTINUED = "continued"
STATE_TERMINATED = "terminated"
STATE_UNRESOLVED = "unresolved"

# A CEILING, never the identity rule. Continuation is decided by direction,
# eligibility and the anchor; this only stops a lineage living forever through a
# long outage or a dormant symbol.
SAFETY_CEILING = timedelta(hours=24)

DIRECTIONAL = ("bullish", "bearish")


def unresolved_payload(reason: str) -> Dict[str, Any]:
    """What is written when identity could not be established.

    Explicitly NOT a fresh UUID: a fabricated identity is indistinguishable from
    a real one and would silently join unrelated rows. Explicitly NOT an absent
    namespace either — historical rows have no namespace at all, and the ban on
    backfilling them is only checkable while those two cases stay distinct.
    """
    return {
        "schema_version": LINEAGE_SCHEMA_VERSION,
        "state": STATE_UNRESOLVED,
        "lineage_id": None,
        "anchor_signal_id": None,
        "failure_reason": reason,
    }


def _payload(state: str, lineage_id: Optional[str],
             anchor: Optional[str] = None) -> Dict[str, Any]:
    return {
        "schema_version": LINEAGE_SCHEMA_VERSION,
        "state": state,
        "lineage_id": lineage_id,
        "anchor_signal_id": anchor,
        "failure_reason": None,
    }


def decide_lineage(*, direction: Any, eligible: bool, bar_time: Any,
                   prev: Optional[Dict[str, Any]],
                   anchor_still_active: bool = True) -> Dict[str, Any]:
    """The whole contract, as a pure function of contemporaneous facts.

    `prev` is the immediately preceding candidate row for this asset+timeframe as
    read back off the table, or None.
    """
    # Not an opportunity at all. Note that neutral rows DO carry a complete
    # entry/stop/TP geometry, so eligibility must never be read as a thesis.
    if direction not in DIRECTIONAL or not eligible:
        return _payload(STATE_TERMINATED, None)

    if not prev:
        return _payload(STATE_BEGIN, str(uuid.uuid4()))

    prev_id = prev.get("lineage_id")
    prev_time = prev.get("evaluated_bar_time")

    # SAME BAR REPLAYED. The row is keyed on the bar, so a re-evaluation writes
    # nothing — but it must not COMPUTE a different identity that ON CONFLICT
    # then hides. Return what is already recorded.
    if prev_id and prev_time is not None and bar_time is not None \
            and prev_time == bar_time:
        return _payload(STATE_CONTINUED, prev_id, prev.get("anchor_signal_id"))

    if not prev_id:
        return _payload(STATE_BEGIN, str(uuid.uuid4()))
    if prev.get("engine_direction") != direction:
        return _payload(STATE_BEGIN, str(uuid.uuid4()))

    # An anchor only terminates a lineage that actually had one. Skipped and
    # dropped candidates carry no signal_id and must not depend on one.
    if prev.get("anchor_signal_id") and not anchor_still_active:
        return _payload(STATE_BEGIN, str(uuid.uuid4()))

    if prev_time is not None and bar_time is not None:
        try:
            if (bar_time - prev_time) > SAFETY_CEILING:
                return _payload(STATE_BEGIN, str(uuid.uuid4()))
        except TypeError:
            return _payload(STATE_BEGIN, str(uuid.uuid4()))

    return _payload(STATE_CONTINUED, prev_id, prev.get("anchor_signal_id"))


async def load_predecessor(db, *, asset_id: Any, timeframe: Any,
                           bar_time: Any) -> Optional[Dict[str, Any]]:
    """The most recent candidate row at or before this bar, for this asset+tf.

    `<=` rather than `<` on purpose: it makes an exact replay of the same bar
    visible, which is what keeps identity stable under ON CONFLICT DO NOTHING.
    Scoped to one asset and one timeframe, so no query can alias across either.
    """
    stmt = (
        select(SignalDecisionCandidate.evaluated_bar_time,
               SignalDecisionCandidate.engine_direction,
               SignalDecisionCandidate.signal_id,
               SignalDecisionCandidate.extra)
        .where(SignalDecisionCandidate.asset_id == asset_id)
        .where(SignalDecisionCandidate.timeframe == timeframe)
        .where(SignalDecisionCandidate.evaluated_bar_time <= bar_time)
        .order_by(SignalDecisionCandidate.evaluated_bar_time.desc())
        .limit(1)
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        return None
    extra = row[3] if len(row) > 3 else None
    ns = extra.get(LINEAGE_NAMESPACE) if isinstance(extra, dict) else None
    ns = ns if isinstance(ns, dict) else {}
    return {
        # The raw extra is surfaced so a sibling namespace can be resolved from
        # the SAME read. Deliberately returned whole rather than parsed here:
        # naming another module's namespace in this file would put it inside a
        # guard that exists to keep evidence out of the decision path.
        "extra": extra if isinstance(extra, dict) else None,
        "evaluated_bar_time": row[0],
        "engine_direction": row[1],
        "lineage_id": ns.get("lineage_id"),
        "anchor_signal_id": ns.get("anchor_signal_id") or row[2],
        "state": ns.get("state"),
    }


async def _anchor_still_active(db, signal_id: Any) -> bool:
    """Is the anchored signal genuinely still open?

    Read through the performance row rather than `signals.live_status`, which is
    demotable and lags. A stale terminal must never masquerade as active.
    """
    from app.models.signal import SignalOutcome, SignalPerformance

    stmt = (select(SignalPerformance.outcome)
            .where(SignalPerformance.signal_id == signal_id)
            .limit(1))
    row = (await db.execute(stmt)).first()
    if row is None:
        return True          # no verdict yet == not yet terminal
    return row[0] == SignalOutcome.ACTIVE


async def resolve_lineage(db, *, asset_id: Any, timeframe: Any, direction: Any,
                          bar_time: Any, eligible: bool,
                          signal_id: Any = None,
                          prefetched_prev: Any = _UNSET) -> Dict[str, Any]:
    """Resolve identity for one candidate. Never raises; never blocks the write.

    Costs ONE indexed SELECT per candidate. The second lookup fires only when the
    predecessor actually carries an anchor, which the overwhelming majority of
    (unpublished) candidates do not.
    """
    try:
        if direction not in DIRECTIONAL or not eligible:
            return _payload(STATE_TERMINATED, None)

        # `prefetched_prev` lets a caller that already performed the one indexed
        # read share it, so resolving a sibling namespace costs no second query.
        prev = (await load_predecessor(db, asset_id=asset_id, timeframe=timeframe,
                                       bar_time=bar_time)
                if prefetched_prev is _UNSET else prefetched_prev)
        anchor_ok = True
        if prev and prev.get("anchor_signal_id") and prev.get("lineage_id"):
            anchor_ok = await _anchor_still_active(db, prev["anchor_signal_id"])

        out = decide_lineage(direction=direction, eligible=eligible,
                             bar_time=bar_time, prev=prev,
                             anchor_still_active=anchor_ok)
        # A newly published signal becomes the anchor for its own lineage.
        if signal_id is not None and out.get("lineage_id") and not out.get("anchor_signal_id"):
            out["anchor_signal_id"] = str(signal_id)
        return out
    except Exception as exc:      # noqa: BLE001 — identity is telemetry, never a gate
        logger.warning("[Lineage] unresolved for %s/%s: %s",
                       asset_id, timeframe, exc)
        return unresolved_payload(type(exc).__name__)
