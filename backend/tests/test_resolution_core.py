"""Golden characterization tests for the shared resolution core.

Hand-computed scenarios covering every resolution path (SL-first, TP1+break-even,
full TP ladder, inside-bar ambiguity conservative vs optimistic, run-to-end, bear
mirror). These LOCK the geometry behaviour so the live tracker and backtest engine
can be refactored to call resolve_trade_path() without any behaviour drift.

Run: PYTHONPATH=backend python tests/test_resolution_core.py   (or via pytest)
"""

from app.backtesting.resolution_core import resolve_trade_path

R = 6  # float compare precision


def _bull(**kw):
    base = dict(direction="bullish", entry=100.0, sl=96.0, tp1=103.0, tp2=106.0, tp3=110.0)
    base.update(kw)
    return base


def test_sl_first_bull():
    r = resolve_trade_path(**_bull(), bars=[(100, 101, 99, 100), (100, 101, 96, 97)])
    assert r.resolved and r.resolved_by_sl and not r.hit_tp1
    assert round(r.realized_return_frac, R) == round(-0.04, R)   # full size at SL -4%
    assert r.closed_bar_idx == 1 and r.bars_walked == 2
    assert round(r.mae_pct, R) == 4.0 and round(r.mfe_pct, R) == 1.0


def test_tp1_then_breakeven_bull():
    # bar0 hits TP1 (low stays above BE), bar1 low touches BE stop (=entry)
    r = resolve_trade_path(**_bull(), bars=[(100, 103, 100.5, 102), (102, 104, 100, 101)])
    assert r.resolved and r.resolved_by_sl and r.hit_tp1 and not r.hit_tp2
    assert round(r.realized_return_frac, R) == round(0.015, R)   # 0.5*TP1 + 0.5*BE(0)
    assert r.tp1_bar_idx == 0 and r.closed_bar_idx == 1


def test_full_tp_ladder_bull():
    r = resolve_trade_path(**_bull(), bars=[(100, 111, 100.5, 110)])
    assert r.resolved and r.hit_tp1 and r.hit_tp2 and r.hit_tp3 and not r.resolved_by_sl
    # 0.5*0.03 + 0.3*0.06 + 0.2*0.10 = 0.053
    assert round(r.realized_return_frac, R) == round(0.053, R)


def test_intrabar_conservative_sl_wins():
    r = resolve_trade_path(**_bull(), bars=[(100, 103, 96, 100)], execution_model="conservative")
    assert r.intrabar_ambiguous and r.resolved_by_sl and not r.hit_tp1
    assert round(r.realized_return_frac, R) == round(-0.04, R)


def test_intrabar_optimistic_tp_wins():
    # same bar, optimistic → TP1 taken, then BE hit same candle (low 96 <= BE 100)
    r = resolve_trade_path(**_bull(), bars=[(100, 103, 96, 100)], execution_model="optimistic")
    assert r.intrabar_ambiguous and r.hit_tp1
    assert round(r.realized_return_frac, R) == round(0.015, R)


def test_run_to_end_unresolved_bull():
    r = resolve_trade_path(**_bull(), bars=[(100, 102, 99, 101), (101, 102, 99.5, 100)])
    assert not r.resolved and r.remaining_share == 1.0 and not r.hit_tp1
    assert round(r.realized_return_frac, R) == 0.0
    assert round(r.mfe_pct, R) == 2.0 and round(r.mae_pct, R) == 1.0


def test_sl_first_bear():
    r = resolve_trade_path(direction="bearish", entry=100.0, sl=104.0, tp1=97.0, tp2=94.0, tp3=90.0,
                           bars=[(100, 104, 99, 103)])
    assert r.resolved and r.resolved_by_sl and not r.hit_tp1
    assert round(r.realized_return_frac, R) == round(-0.04, R)


def test_full_tp_ladder_bear():
    r = resolve_trade_path(direction="bearish", entry=100.0, sl=104.0, tp1=97.0, tp2=94.0, tp3=90.0,
                           bars=[(100, 100.5, 89, 91)])
    assert r.resolved and r.hit_tp1 and r.hit_tp2 and r.hit_tp3 and not r.resolved_by_sl
    assert round(r.realized_return_frac, R) == round(0.053, R)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
        passed += 1
    print(f"\n{passed}/{len(tests)} golden resolution-core tests PASSED")
