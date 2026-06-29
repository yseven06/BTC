"""Differential equivalence: FROZEN copy of the live tracker bar-walk vs the new
resolution_core, over thousands of randomized candle paths.

This is the STRICT byte-identical proof for KEY1-b2: both run on IDENTICAL in-memory
bars, so ANY field mismatch is a core-vs-tracker divergence (not data drift). The
live tracker bar-walk (tracker.py ~L409-507) is transcribed VERBATIM below as
``legacy_bar_walk`` and frozen; resolve_trade_path(..., execution_model='conservative')
must match it on every input (conservative == the live tracker's hardcoded SL-wins).

Run: PYTHONPATH=backend python tests/test_resolution_equivalence.py
"""

import random

from app.backtesting.resolution_core import resolve_trade_path


def legacy_bar_walk(direction, entry, sl, tp1, tp2, tp3, bars):
    """VERBATIM frozen snapshot of the live tracker bar-walk (tracker.py L409-507).
    Do NOT 'tidy' — it is the reference behaviour the core must reproduce."""
    is_bull = direction == "bullish"
    current_sl = sl
    remaining_share = 1.0
    realized = 0.0
    hit_tp1 = hit_tp2 = hit_tp3 = False
    tp1_bar_idx = None
    resolved = False
    resolved_by_sl = False
    max_drawdown = 0.0
    max_favorable = 0.0
    mfe_bar_idx = 0
    mae_bar_idx = 0
    post_tp1_mfe = 0.0
    post_tp1_mae = 0.0
    intrabar_ambiguous = False
    bars_to_outcome = 0
    closed_idx = None

    for k in range(len(bars)):
        o, h, l, c = bars[k]
        bars_to_outcome = k + 1
        if is_bull:
            drawdown = ((entry - l) / entry) * 100.0 if entry > 0 else 0.0
            favorable = ((h - entry) / entry) * 100.0 if entry > 0 else 0.0
        else:
            drawdown = ((h - entry) / entry) * 100.0 if entry > 0 else 0.0
            favorable = ((entry - l) / entry) * 100.0 if entry > 0 else 0.0
        if favorable > max_favorable:
            max_favorable = favorable
            mfe_bar_idx = k
        if drawdown > max_drawdown:
            max_drawdown = drawdown
            mae_bar_idx = k
        if hit_tp1:
            post_tp1_mfe = max(post_tp1_mfe, favorable)
            post_tp1_mae = max(post_tp1_mae, drawdown)

        sl_hit = l <= current_sl if is_bull else h >= current_sl
        if is_bull:
            tp1_triggered = h >= tp1 and not hit_tp1
            tp2_triggered = h >= tp2 and not hit_tp2
            tp3_triggered = h >= tp3 and not hit_tp3
        else:
            tp1_triggered = l <= tp1 and not hit_tp1
            tp2_triggered = l <= tp2 and not hit_tp2
            tp3_triggered = l <= tp3 and not hit_tp3
        tp_hit = tp1_triggered or tp2_triggered or tp3_triggered

        if sl_hit and tp_hit:
            intrabar_ambiguous = True
            tp_hit = False
            tp1_triggered = tp2_triggered = tp3_triggered = False

        if sl_hit:
            ret_sl = ((current_sl - entry) / entry) if is_bull else ((entry - current_sl) / entry)
            realized += remaining_share * ret_sl
            remaining_share = 0.0
            resolved = True
            resolved_by_sl = True
            closed_idx = k
            break
        elif tp_hit:
            if tp1_triggered:
                hit_tp1 = True
                tp1_bar_idx = k
                ret_tp1 = ((tp1 - entry) / entry) if is_bull else ((entry - tp1) / entry)
                realized += 0.50 * ret_tp1
                remaining_share -= 0.50
                current_sl = entry
            if tp2_triggered and remaining_share > 0:
                hit_tp2 = True
                portion = min(0.30, remaining_share)
                ret_tp2 = ((tp2 - entry) / entry) if is_bull else ((entry - tp2) / entry)
                realized += portion * ret_tp2
                remaining_share -= portion
            if tp3_triggered and remaining_share > 0:
                hit_tp3 = True
                portion = remaining_share
                ret_tp3 = ((tp3 - entry) / entry) if is_bull else ((entry - tp3) / entry)
                realized += portion * ret_tp3
                remaining_share = 0.0
                resolved = True
                closed_idx = k
                break
            if remaining_share > 0:
                sl_hit_after_tp = l <= current_sl if is_bull else h >= current_sl
                if sl_hit_after_tp:
                    ret_sl = ((current_sl - entry) / entry) if is_bull else ((entry - current_sl) / entry)
                    realized += remaining_share * ret_sl
                    remaining_share = 0.0
                    resolved = True
                    resolved_by_sl = True
                    closed_idx = k
                    break

    return dict(
        resolved=resolved, resolved_by_sl=resolved_by_sl, hit_tp1=hit_tp1, hit_tp2=hit_tp2,
        hit_tp3=hit_tp3, tp1_bar_idx=tp1_bar_idx, bars_walked=bars_to_outcome, realized=realized,
        remaining=remaining_share, mfe=max_favorable, mae=max_drawdown, mfe_bar_idx=mfe_bar_idx,
        mae_bar_idx=mae_bar_idx, post_tp1_mfe=post_tp1_mfe, post_tp1_mae=post_tp1_mae,
        intrabar=intrabar_ambiguous, closed_idx=closed_idx,
    )


def _core_as_dict(r):
    return dict(
        resolved=r.resolved, resolved_by_sl=r.resolved_by_sl, hit_tp1=r.hit_tp1, hit_tp2=r.hit_tp2,
        hit_tp3=r.hit_tp3, tp1_bar_idx=r.tp1_bar_idx, bars_walked=r.bars_walked,
        realized=r.realized_return_frac, remaining=r.remaining_share, mfe=r.mfe_pct, mae=r.mae_pct,
        mfe_bar_idx=r.mfe_bar_idx, mae_bar_idx=r.mae_bar_idx, post_tp1_mfe=r.post_tp1_mfe_pct,
        post_tp1_mae=r.post_tp1_mae_pct, intrabar=r.intrabar_ambiguous, closed_idx=r.closed_bar_idx,
    )


def _random_scenario(rng):
    direction = rng.choice(["bullish", "bearish"])
    entry = 100.0
    if direction == "bullish":
        sl = entry - rng.uniform(0.5, 8.0)
        tp1 = entry + rng.uniform(0.5, 4.0)
        tp2 = tp1 + rng.uniform(0.5, 4.0)
        tp3 = tp2 + rng.uniform(0.5, 5.0)
    else:
        sl = entry + rng.uniform(0.5, 8.0)
        tp1 = entry - rng.uniform(0.5, 4.0)
        tp2 = tp1 - rng.uniform(0.5, 4.0)
        tp3 = tp2 - rng.uniform(0.5, 5.0)
    # random-walk candles with realistic high>=max(o,c), low<=min(o,c)
    bars = []
    price = entry
    for _ in range(rng.randint(1, 30)):
        o = price
        price = price + rng.uniform(-4.0, 4.0)
        c = price
        hi = max(o, c) + rng.uniform(0.0, 2.5)
        lo = min(o, c) - rng.uniform(0.0, 2.5)
        bars.append((round(o, 4), round(hi, 4), round(lo, 4), round(c, 4)))
    return direction, entry, sl, tp1, tp2, tp3, bars


def run_differential(n=8000, seed=1337):
    rng = random.Random(seed)
    mismatches = []
    for i in range(n):
        direction, entry, sl, tp1, tp2, tp3, bars = _random_scenario(rng)
        leg = legacy_bar_walk(direction, entry, sl, tp1, tp2, tp3, bars)
        core = _core_as_dict(resolve_trade_path(
            direction=direction, entry=entry, sl=sl, tp1=tp1, tp2=tp2, tp3=tp3,
            bars=bars, execution_model="conservative"))
        # exact compare; floats are produced by identical ops in identical order
        diff = {k: (leg[k], core[k]) for k in leg if leg[k] != core[k]}
        if diff:
            mismatches.append((i, diff, (direction, entry, sl, tp1, tp2, tp3, bars)))
    return mismatches


def test_differential_equivalence():
    mismatches = run_differential()
    assert not mismatches, f"{len(mismatches)} mismatches; first: {mismatches[0][:2]}"


if __name__ == "__main__":
    ms = run_differential()
    if ms:
        print(f"FAIL — {len(ms)} mismatch(es). First:")
        idx, diff, scen = ms[0]
        print(f"  scenario #{idx}: {diff}")
        print(f"  inputs: {scen}")
    else:
        print("PASS — 8000/8000 randomized scenarios: legacy tracker bar-walk == resolution_core (byte-identical)")
