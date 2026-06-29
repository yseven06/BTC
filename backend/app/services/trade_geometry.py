"""Pure trade-geometry math — single source shared by birth + trade-path telemetry.

No DB, no engine state, no I/O — just price arithmetic. Used by
``build_birth_telemetry`` (generation time) and ``build_trade_path_extra``
(resolution time) so the planned-R:R and distance DEFINITIONS stay identical across
the two telemetry waves (no duplicated formula drifting out of sync).
"""

from __future__ import annotations

from typing import Optional


def safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """a / b rounded to 4dp, or None when undefined (None operand or b == 0)."""
    if a is None or b is None or b == 0:
        return None
    return round(a / b, 4)


def planned_rr(entry: Optional[float], sl: Optional[float], tp: Optional[float]) -> Optional[float]:
    """Planned reward:risk = |tp - entry| / |entry - sl| (None if any input missing
    or risk distance is zero)."""
    if entry is None or sl is None or tp is None:
        return None
    return safe_div(abs(tp - entry), abs(entry - sl))


def dist_pct(entry: Optional[float], price: Optional[float]) -> Optional[float]:
    """|price - entry| as a percent of entry (None if entry missing/zero)."""
    if price is None or not entry:
        return None
    return round(abs(price - entry) / entry * 100.0, 4)
