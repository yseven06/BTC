"""
Concrete policies. FixedCurrent is the first (the fidelity baseline); future
policies (HardBE, Trailing, AdaptiveScaleout) drop in here without touching the
replay engine.
"""

from __future__ import annotations

from app.trade_mgmt.policies.base import Policy
from app.trade_mgmt.types import ManagementDecision, Tp1Context


class FixedCurrent(Policy):
    """The current production behavior baked into the tracker:
    TP1 → exit 50% and move SL to entry (break-even); TP2 → 30%; TP3 → remainder.

    This is the **fidelity baseline**: replaying it must reproduce the tracker's
    realized return / TP1-TP2-SL behavior (verified in Phase 1 Step 3).
    """

    name = "FixedCurrent"

    def decide_tp1(self, ctx: Tp1Context) -> ManagementDecision:
        return ManagementDecision(
            tp1_scale_frac=0.50,
            tp2_scale_frac=0.30,
            tp3_scale_frac=0.20,
            remainder_mode="BREAKEVEN",
            reason="mevcut tracker politikası (50/30/20 + TP1 sonrası SL=entry)",
        )
