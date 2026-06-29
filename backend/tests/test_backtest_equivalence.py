"""Differential equivalence for the BACKTEST per-trade resolution: a FROZEN copy of
the run_backtest inline per-trade loop vs the new ``apply_backtest_bar`` (which uses
the shared resolution_core.step_bar + capital-weighted fill accounting + bar-count
expiry).

Both run on IDENTICAL inputs, so any field mismatch — including a single float ULP in
``realized_pnl_capital`` — is a real accounting/behaviour divergence (not data drift).
Covers all three execution models. Asserts EXACT equality (capital accounting replays
fills in the same order/float ops as the legacy).

Run: PYTHONPATH=backend python tests/test_backtest_equivalence.py
"""

import random
from types import SimpleNamespace

from app.backtesting.engine import apply_backtest_bar
from app.backtesting.resolution_core import new_walk_state, resolve_inside_bar_ambiguity
from tests.test_resolution_equivalence import _random_scenario


def legacy_resolve_backtest_trade(direction, entry, sl, tp1, tp2, tp3, allocated_capital,
                                  bars, max_age, execution_model):
    """VERBATIM frozen snapshot of the run_backtest per-trade resolution
    (engine.py per-bar loop, capital-weighted) — the reference behaviour."""
    is_bull = direction == "bullish"
    current_sl = sl
    remaining_share = 1.0
    realized_pnl_capital = 0.0
    tp1_hit = tp2_hit = tp3_hit = False
    max_price_reached = 0.0
    min_price_reached = 999999999.0
    age = 0
    is_expired = False
    resolved = False

    for k in range(len(bars)):
        current_open, current_high, current_low, current_price = bars[k]
        age += 1
        max_price_reached = max(max_price_reached, current_high)
        min_price_reached = min(min_price_reached, current_low)

        sl_hit = current_low <= current_sl if is_bull else current_high >= current_sl
        if is_bull:
            tp1_triggered = current_high >= tp1 and not tp1_hit
            tp2_triggered = current_high >= tp2 and not tp2_hit
            tp3_triggered = current_high >= tp3 and not tp3_hit
        else:
            tp1_triggered = current_low <= tp1 and not tp1_hit
            tp2_triggered = current_low <= tp2 and not tp2_hit
            tp3_triggered = current_low <= tp3 and not tp3_hit
        tp_hit = tp1_triggered or tp2_triggered or tp3_triggered

        if sl_hit and tp_hit:
            winner = resolve_inside_bar_ambiguity(direction, current_open, current_price, execution_model)
            if winner == "sl":
                tp_hit = False
                tp1_triggered = tp2_triggered = tp3_triggered = False
            else:
                sl_hit = False

        if sl_hit:
            ret_sl = ((current_sl - entry) / entry) if is_bull else ((entry - current_sl) / entry)
            realized_pnl_capital += remaining_share * allocated_capital * ret_sl
            remaining_share = 0.0
        elif tp_hit:
            if tp1_triggered:
                tp1_hit = True
                portion = 0.50
                ret_tp1 = ((tp1 - entry) / entry) if is_bull else ((entry - tp1) / entry)
                realized_pnl_capital += portion * allocated_capital * ret_tp1
                remaining_share -= portion
                current_sl = entry
            if tp2_triggered and remaining_share > 0:
                tp2_hit = True
                portion = min(0.30, remaining_share)
                ret_tp2 = ((tp2 - entry) / entry) if is_bull else ((entry - tp2) / entry)
                realized_pnl_capital += portion * allocated_capital * ret_tp2
                remaining_share -= portion
            if tp3_triggered and remaining_share > 0:
                tp3_hit = True
                portion = remaining_share
                ret_tp3 = ((tp3 - entry) / entry) if is_bull else ((entry - tp3) / entry)
                realized_pnl_capital += portion * allocated_capital * ret_tp3
                remaining_share = 0.0
            if remaining_share > 0:
                sl_hit_after_tp = current_low <= current_sl if is_bull else current_high >= current_sl
                if sl_hit_after_tp:
                    ret_sl = ((current_sl - entry) / entry) if is_bull else ((entry - current_sl) / entry)
                    realized_pnl_capital += remaining_share * allocated_capital * ret_sl
                    remaining_share = 0.0

        if remaining_share > 0 and age >= max_age:
            is_expired = True
            portion = remaining_share
            ret_close = ((current_price - entry) / entry) if is_bull else ((entry - current_price) / entry)
            realized_pnl_capital += portion * allocated_capital * ret_close
            remaining_share = 0.0

        if remaining_share <= 0.0:
            resolved = True
            break

    if is_bull:
        max_dd_trade = ((entry - min_price_reached) / entry) * 100.0
    else:
        max_dd_trade = ((max_price_reached - entry) / entry) * 100.0

    return dict(realized_pnl_capital=realized_pnl_capital, max_dd_trade=max(0.0, max_dd_trade),
                age=age, is_expired=is_expired, resolved=resolved)


def step_resolve_backtest_trade(direction, entry, sl, tp1, tp2, tp3, allocated_capital,
                                bars, max_age, execution_model):
    """The NEW path: apply_backtest_bar (step_bar + fills) over the trade's bars."""
    trade = SimpleNamespace(
        state=new_walk_state(direction=direction, entry=entry, sl=sl, tp1=tp1, tp2=tp2,
                             tp3=tp3, execution_model=execution_model),
        allocated_capital=allocated_capital, entry_price=entry,
        realized_pnl_capital=0.0, is_expired=False, age=0,
    )
    for k in range(len(bars)):
        trade.age += 1
        if apply_backtest_bar(trade, trade.age - 1, bars[k], max_age):
            break
    return dict(realized_pnl_capital=trade.realized_pnl_capital,
                max_dd_trade=max(0.0, trade.state.max_drawdown),
                age=trade.age, is_expired=trade.is_expired,
                resolved=trade.state.remaining_share <= 0.0)


def run_backtest_differential(n=9000, seed=4242):
    rng = random.Random(seed)
    mism = []
    for i in range(n):
        direction, entry, sl, tp1, tp2, tp3, bars = _random_scenario(rng)
        alloc = round(rng.uniform(50.0, 5000.0), 2)
        max_age = rng.randint(3, 30)
        model = rng.choice(["conservative", "optimistic", "neutral"])
        leg = legacy_resolve_backtest_trade(direction, entry, sl, tp1, tp2, tp3, alloc, bars, max_age, model)
        new = step_resolve_backtest_trade(direction, entry, sl, tp1, tp2, tp3, alloc, bars, max_age, model)
        diff = {k: (leg[k], new[k]) for k in leg if leg[k] != new[k]}
        if diff:
            mism.append((i, model, diff))
    return mism


def test_backtest_equivalence():
    mism = run_backtest_differential()
    assert not mism, f"{len(mism)} mismatches; first: {mism[0]}"


if __name__ == "__main__":
    ms = run_backtest_differential()
    if ms:
        print(f"FAIL — {len(ms)} backtest mismatch(es). First: {ms[0]}")
    else:
        print("PASS — backtest 9000/9000 (x3 execution models): legacy run_backtest per-trade "
              "resolution == apply_backtest_bar (realized_pnl_capital EXACT, max_dd/age/expired)")
