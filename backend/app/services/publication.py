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

from typing import Optional

from app.backtesting import lifecycle

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
