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


class HardBE(Policy):
    """Defensive break-even policy — bank most of the position at TP1.

    Thesis: directly minimize give-back by taking 70% off at TP1 and holding the
    small remainder at a hard break-even (out at TP2 if reached, else BE). Trades
    upside in big runs for far less give-back exposure.

    (In summary-based replay the ONLY break-even variant distinguishable from
    FixedCurrent is the scale-out schedule — "move BE earlier" is invisible
    without a tick path — so Hard-BE is expressed as a heavier TP1 bank.)
    """

    name = "HardBE"

    def decide_tp1(self, ctx: Tp1Context) -> ManagementDecision:
        return ManagementDecision(
            tp1_scale_frac=0.70,
            tp2_scale_frac=0.30,
            tp3_scale_frac=0.0,
            remainder_mode="BREAKEVEN",
            reason="erken banka (TP1 %70) + hard break-even",
        )


class Trailing(Policy):
    """Let-winners-run policy — take little at TP1, trail the rest.

    Thesis: the data shows ~1R of post-TP1 favorable movement is given back under
    hard-BE; a trailing stop should capture part of that. Takes 30% at TP1 and
    trails the remaining 70% at `trail_k` R behind the post-TP1 peak.

    NOTE: trailing replay is APPROXIMATE (the stored summary has post-TP1 MFE/MAE
    extremes, not the full path) → these results carry lower confidence (flagged
    'trail_approx'). Direction is meaningful; exact magnitude is not.
    """

    name = "Trailing"

    def decide_tp1(self, ctx: Tp1Context) -> ManagementDecision:
        return ManagementDecision(
            tp1_scale_frac=0.30,
            remainder_mode="TRAIL",
            trail_rule="R_K",
            trail_k=0.5,
            reason="TP1 %30 + kalan trailing (0.5R)",
        )


def registered_policies():
    """Policy comparison set; FixedCurrent is the baseline (index 0). Each Phase-1
    Step-5 commit appends one alternative here and it shows up in the report."""
    return [FixedCurrent(), HardBE(), Trailing()]
