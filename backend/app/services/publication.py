"""Publication boundary — which LIVE signals may reach the public Signal Center.

This module answers exactly one question: *may this signal be shown to a user
right now?* It does not decide whether a trade opened, when it opened, or what
it is worth. Those are lifecycle/entry-activation questions and they are settled
elsewhere; nothing here may influence them.

WHY A BOUNDARY IS NEEDED AT ALL
-------------------------------
`waiting_entry` is a PRE-publication state: the signal has been generated and its
levels stamped, but price has not yet been observed at the entry zone, so no
position exists. `list_signals` filtered only on `Signal.is_active`, so those
rows were served to the public feed alongside genuinely open trades. A user
looking at a `waiting_entry` row sees entry/TP/SL levels for a trade that the
system itself does not consider open — and if price later reaches those levels
without the signal ever activating, the row reads as a call that "worked" when
the product never took it.

ALLOW-LIST, NOT A DENY-LIST
---------------------------
The rule is membership in a closed set of post-activation live states, not
`!= waiting_entry`. A deny-list fails OPEN: any state added later — or a row
whose `live_status` is NULL because it predates the lifecycle column — would be
published by default, which is the wrong direction for a publication gate. The
allow-list fails CLOSED: an unknown state is not published until someone decides
it should be.

WHY NOT "REQUIRES A waiting_entry -> active HISTORY ROW"
-------------------------------------------------------
That was considered and measured against production, and it is WORSE on both
sides:

  * FALSE POSITIVES. `live_status` can be demoted back to `waiting_entry`
    (tracker.py:1034-1052). Production currently holds 18 such rows, 3 of which
    have a genuine `waiting_entry -> active` history row from earlier in their
    life. A history-based rule would publish those 3 even though the system now
    says the entry is not held.
  * FALSE NEGATIVES. Before the entry gate was enabled, signals were born
    directly `active` (scheduler.py:638-641) and therefore have NO activation
    transition at all. Production holds 827 `active`, 948 `approaching_tp`, 710
    `weakening` and 1395 `invalidating` rows in exactly that shape. A
    history-based rule would refuse to publish every one of them.

On the CURRENT live cohort the two rules agree exactly — all 11 `active`, 9
`approaching_tp`, 5 `weakening` and 1 `invalidating` rows do have the transition,
and all 10 `waiting_entry` rows do not — but that agreement is a coincidence of
this cohort being young (oldest 2026-08-06, entirely post-gate). The status rule
is the one that stays correct when it stops being a coincidence.

SCOPE
-----
LIVE surfaces only. The history surface (`is_active = False`) is a separate
contract and is deliberately untouched: a closed signal remains fully visible,
including one that closed without ever filling.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, Optional
from uuid import UUID

from sqlalchemy import func, select

from app.backtesting import lifecycle
from app.models.intelligence import SignalStatusHistory

# The post-activation live states. `waiting_entry` is absent BY DESIGN — it is
# the one state that means "no position exists yet".
PUBLIC_LIVE_STATUSES: tuple[str, ...] = (
    lifecycle.ACTIVE,
    lifecycle.APPROACHING_TP,
    lifecycle.WEAKENING,
    lifecycle.INVALIDATING,
)


def is_public_live_status(live_status: Optional[str]) -> bool:
    """True when a LIVE signal in this state may be shown publicly."""
    return live_status in PUBLIC_LIVE_STATUSES


def is_publishable(*, is_active: bool, live_status: Optional[str]) -> bool:
    """May this signal be served on a public surface?

    A closed signal (`is_active` False) belongs to the history contract and is
    always serveable — hiding it would erase the record of trades that never
    filled, which is exactly the data the no-fill research depends on being
    visible. A live signal is serveable only from a post-activation state.
    """
    if not is_active:
        return True
    return is_public_live_status(live_status)


# ── PUBLIC AGE ───────────────────────────────────────────────────────────────
# Since only post-activation signals are published, the age a user reads must be
# measured from ACTIVATION, not from candidate birth. Measured on production the
# two disagree by up to an order of magnitude on individual rows — COMPUSDT read
# 18.5h old while the trade had been open 1.8h; XRPUSDT read 39.6h against 23.1h.
#
# WHY NOT `signals.live_status_since`. It is re-stamped on EVERY phase change
# (lifecycle_log.apply_live_status:123-126 assigns it unconditionally once the
# phase differs), so it measures how long the CURRENT phase has lasted, not how
# long the signal has been live. Same production rows: ETHUSDT's
# live_status_since was 0.3h old against a true 13.6h activation age, ALICEUSDT
# 0.2h against 31.4h. It is the right input for the status badge's "since" — and
# the wrong one for age. No new column is needed; the transition is already
# recorded.


def public_since(activated_at: Optional[datetime],
                 generated_at: Optional[datetime]) -> Optional[datetime]:
    """When this signal became publicly visible.

    Falls back to `generated_at` for a signal born directly ACTIVE — before the
    entry gate was enabled that was the normal path (scheduler.py:638-641), and
    for those rows birth IS activation, so the fallback is the true answer
    rather than an approximation. 3880 of the 4159 post-activation signals in
    production are that shape; every one of the 25 currently public rows takes
    the history path instead.
    """
    return activated_at or generated_at


async def activation_times(db, signal_ids: Iterable[UUID]) -> Dict[UUID, datetime]:
    """EARLIEST waiting_entry -> active transition per signal. ONE query.

    Grouped rather than per-row: a 300-row page must not become 300 round trips.
    `min()` because the transition can legitimately appear more than once — a
    signal may be demoted back to waiting_entry and re-promoted (2 signals in
    production carry two rows today). The FIRST promotion is when it became
    public, so a later one must not reset the age.
    """
    ids = [i for i in signal_ids if i is not None]
    if not ids:
        return {}
    rows = await db.execute(
        select(SignalStatusHistory.signal_id,
               func.min(SignalStatusHistory.created_at))
        .where(SignalStatusHistory.signal_id.in_(ids),
               SignalStatusHistory.from_status == lifecycle.WAITING_ENTRY,
               SignalStatusHistory.to_status == lifecycle.ACTIVE)
        .group_by(SignalStatusHistory.signal_id)
    )
    return {sid: ts for sid, ts in rows.all()}
