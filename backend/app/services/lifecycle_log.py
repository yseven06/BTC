"""
Lifecycle observability — status-transition logging helper.

Builds SignalStatusHistory rows. Pure constructor (no DB I/O); the caller adds
the row to its existing session so logging shares the signal's transaction and
adds no extra round-trip. Rows are written ONLY on real transitions / birth /
resolution — never per tracking pass (suppressed flip-flops bump a counter
instead).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.models.intelligence import SignalStatusHistory


def make_event(
    *,
    signal_id,
    to_status: str,
    from_status: Optional[str] = None,
    kind: str = "transition",
    reason: Optional[str] = None,
    regime: Optional[str] = None,
    price: Optional[float] = None,
    retrace_to_sl: Optional[float] = None,
    progress_to_tp: Optional[float] = None,
    structure_event: Optional[str] = None,
    momentum_dir: Optional[str] = None,
    outcome: Optional[str] = None,
    created_at: Optional[datetime] = None,
) -> SignalStatusHistory:
    """Construct (don't persist) a lifecycle history row.

    `created_at` is normally left to the column's server_default. Pass it when
    the row must line up EXACTLY with signals.live_status_since — a reader that
    joins the two cannot tell a real ordering from clock skew otherwise.
    """
    row = SignalStatusHistory(
        signal_id=signal_id,
        from_status=from_status,
        to_status=to_status,
        kind=kind,
        reason=reason,
        regime=regime,
        price=price,
        retrace_to_sl=retrace_to_sl,
        progress_to_tp=progress_to_tp,
        structure_event=structure_event,
        momentum_dir=momentum_dir,
        outcome=outcome,
    )
    # Only when given: assigning None explicitly would insert NULL into a
    # NOT NULL column instead of letting the server_default fire.
    if created_at is not None:
        row.created_at = created_at
    return row


def birth_event(
    signal,
    *,
    reason: str,
    regime: Optional[str] = None,
    created_at: Optional[datetime] = None,
) -> SignalStatusHistory:
    """Birth row DERIVED from the signal's own live_status.

    The birth row used to hardcode to_status="active" a few lines below the
    constructor that set live_status — so when CP-ENTRY-ACTIVATION-GATE made
    birth land in `waiting_entry`, the column and its own audit row disagreed
    and nothing failed. Reading the status back off the signal makes that
    disagreement unrepresentable rather than merely fixed.
    """
    return make_event(
        signal_id=signal.id,
        from_status=None,
        to_status=signal.live_status,
        kind="birth",
        reason=reason,
        regime=regime,
        created_at=created_at or getattr(signal, "live_status_since", None),
    )


def apply_live_status(
    signal,
    *,
    to_status: str,
    reason: Optional[str],
    at: datetime,
    kind: Optional[str] = None,
    regime: Optional[str] = None,
    price: Optional[float] = None,
    retrace_to_sl: Optional[float] = None,
    progress_to_tp: Optional[float] = None,
    structure_event: Optional[str] = None,
    momentum_dir: Optional[str] = None,
) -> Optional[SignalStatusHistory]:
    """Move `signal` into `to_status` and return the row that records the move.

    Returns None when the phase is unchanged — no row, no `live_status_since`
    bump. This is the ONLY place that decides whether a phase change happened,
    so the entry gate and the lifecycle evaluator cannot disagree about it: the
    gate used to promote waiting_entry -> active on its own, which left
    `prev_status` already equal to `active` by the time the evaluator ran, and
    the promotion was never logged at all.

    The caller adds the returned row to its own session, keeping this a pure
    constructor like the rest of this module.

    `reason` and `status_updated_at` are refreshed on EVERY call, changed or
    not, matching the previous inline behaviour: the reason is the current
    assessment, not a property of the transition.
    """
    prev = signal.live_status
    signal.status_reason = reason
    signal.status_updated_at = at

    if prev == to_status and signal.live_status_since is not None:
        return None

    signal.live_status = to_status
    signal.live_status_since = at
    return make_event(
        signal_id=signal.id,
        from_status=prev,
        to_status=to_status,
        kind=kind or ("birth" if prev is None else "transition"),
        reason=reason,
        regime=regime,
        price=price,
        retrace_to_sl=retrace_to_sl,
        progress_to_tp=progress_to_tp,
        structure_event=structure_event,
        momentum_dir=momentum_dir,
        created_at=at,
    )
