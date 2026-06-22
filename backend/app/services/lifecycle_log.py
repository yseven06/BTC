"""
Lifecycle observability — status-transition logging helper.

Builds SignalStatusHistory rows. Pure constructor (no DB I/O); the caller adds
the row to its existing session so logging shares the signal's transaction and
adds no extra round-trip. Rows are written ONLY on real transitions / birth /
resolution — never per tracking pass (suppressed flip-flops bump a counter
instead).
"""

from __future__ import annotations

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
) -> SignalStatusHistory:
    """Construct (don't persist) a lifecycle history row."""
    return SignalStatusHistory(
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
