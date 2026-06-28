"""
Counterfactual replay engine — POLICY-INDEPENDENT core.

Given one `PathRecord` (the observed price-path summary) and any `Policy`, it
reconstructs the realized return in R-multiples that the policy *would* have
produced. The engine reads only the `Policy` abstraction + the record's
observed path summary; it contains zero policy-specific logic, so new policies
plug in without changing this file.

Determinism: pure function — no time, no randomness, no IO. Same (record,
policy) → same ReplayResult, always.

Replay fidelity scope (Phase 1): reconstruction is summary-based (MFE/MAE
extremes + TP/SL flags), not a full intrabar walk. BREAKEVEN / fixed scale-out
schedules reconstruct exactly; TRAIL modes are APPROXIMATE (flagged, lower
confidence) since the full post-TP1 path isn't stored. See phase1-spec §6.

R convention: unit = entry↔SL distance. A full stop = -1.0R. A target's reward
= |target-entry| / |entry-sl| (favorable magnitude; direction-agnostic).
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from app.trade_mgmt.policies.base import Policy
from app.trade_mgmt.types import PathRecord, ReplayResult, Tp1Context

_EPS = 1e-9


def _r_mult(price: Optional[float], entry: Optional[float], sl: Optional[float]) -> Optional[float]:
    """Reward of a target in R-multiples (favorable magnitude, direction-agnostic)."""
    if price is None or entry is None or sl is None or entry == sl:
        return None
    return round(abs(price - entry) / abs(entry - sl), 6)


def _observed_r(rec: PathRecord) -> float:
    """Observed realized return expressed in R (only used for the rare no-TP1
    non-loss/expiry fallback)."""
    if rec.cur_realized_return is None or not rec.sl_dist_pct:
        return 0.0
    return round(rec.cur_realized_return / rec.sl_dist_pct, 4)


def build_tp1_context(rec: PathRecord) -> Tp1Context:
    """Pre-decision context for a policy (no observed/future fields)."""
    return Tp1Context(
        direction=rec.direction,
        entry=rec.entry, sl=rec.sl, tp1=rec.tp1, tp2=rec.tp2, tp3=rec.tp3,
        tp1_r=rec.tp1_r,
        tp2_r=_r_mult(rec.tp2, rec.entry, rec.sl),
        tp3_r=_r_mult(rec.tp3, rec.entry, rec.sl),
        tp1_atr=rec.tp1_atr,
        atr_pct=rec.atr_pct_at_signal,
        regime=rec.regime, timeframe=rec.timeframe, symbol=rec.symbol,
    )


def replay(rec: PathRecord, policy: Policy) -> ReplayResult:
    """Replay one path under one policy → realized R. Pure & deterministic."""
    flags: List[str] = list(rec.confidence_flags)

    # --- No TP1 reached: Phase-1 policies take no pre-TP1 action ---
    if not rec.cur_reached_tp1:
        if (rec.outcome or "").lower() == "loss":
            return ReplayResult(
                realized_r=-1.0, exit_reason="full_sl",
                scale_events=((1.0, -1.0, "sl"),), gave_back=False,
                bars_held=rec.bars_total, flags=tuple(flags), confidence=1.0,
            )
        obs = _observed_r(rec)  # expiry / breakeven-without-TP — observed fallback
        flags.append("observed_fallback")
        return ReplayResult(
            realized_r=obs, exit_reason="no_tp1_" + (rec.outcome or "unknown"),
            scale_events=((1.0, obs, "close"),), gave_back=False,
            bars_held=rec.bars_total, flags=tuple(flags), confidence=0.6,
        )

    # --- TP1 reached: ask the policy, then apply mechanically ---
    ctx = build_tp1_context(rec)
    d = policy.decide_tp1(ctx)
    tp1_r = rec.tp1_r or 0.0

    realized = d.tp1_scale_frac * tp1_r
    events: List[Tuple[float, float, str]] = [(round(d.tp1_scale_frac, 4), round(tp1_r, 4), "tp1")]
    remaining = 1.0 - d.tp1_scale_frac
    gave_back = False

    if d.remainder_mode == "BREAKEVEN":
        if rec.cur_reached_tp2 and ctx.tp2_r is not None and remaining > _EPS:
            f2 = min(d.tp2_scale_frac, remaining)
            realized += f2 * ctx.tp2_r
            remaining -= f2
            events.append((round(f2, 4), round(ctx.tp2_r, 4), "tp2"))
            if rec.cur_reached_tp3 and ctx.tp3_r is not None and remaining > _EPS:
                f3 = min(d.tp3_scale_frac, remaining)
                realized += f3 * ctx.tp3_r
                remaining -= f3
                events.append((round(f3, 4), round(ctx.tp3_r, 4), "tp3"))
        if remaining > _EPS:
            # leftover rides with SL=entry → exits at break-even (0R)
            realized += remaining * 0.0
            events.append((round(remaining, 4), 0.0, "breakeven"))
            gave_back = not bool(rec.cur_reached_tp2)
        reason = "scaleout_be"
        confidence = 0.85 if rec.still_forming_resolution else 1.0

    elif d.remainder_mode == "TRAIL":
        # APPROXIMATE: remainder captures up to the post-TP1 peak minus the trail
        # distance; at least the realized TP2 region if it got there.
        cap = max(0.0, (rec.cur_post_tp1_mfe_r or 0.0) - (d.trail_k or 0.0))
        if rec.cur_reached_tp2 and ctx.tp2_r is not None:
            cap = max(cap, ctx.tp2_r)
        realized += remaining * cap
        events.append((round(remaining, 4), round(cap, 4), "trail~"))
        flags.append("trail_approx")
        reason = "trail"
        confidence = 0.5

    else:
        reason = "unknown_mode:" + str(d.remainder_mode)
        confidence = 0.3

    return ReplayResult(
        realized_r=round(realized, 4), exit_reason=reason,
        scale_events=tuple(events), gave_back=gave_back,
        bars_held=rec.bars_total, flags=tuple(flags), confidence=confidence,
    )
