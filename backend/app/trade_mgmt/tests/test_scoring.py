"""
Unit tests for scoring + policy comparison — NO DB.

Run:  python -m app.trade_mgmt.tests.test_scoring
"""

import sys

from app.trade_mgmt.path_reader import to_path_record
from app.trade_mgmt.policies.base import Policy
from app.trade_mgmt.policies.catalog import FixedCurrent
from app.trade_mgmt.scoring import _pct, compare_policies, score_policy
from app.trade_mgmt.types import ManagementDecision


def _rec(**over):
    """entry=100, sl=95; tp1=105(1R), tp2=110(2R), tp3=120(4R). Default = all TP."""
    row = dict(
        signal_id="s", asset_id=None, symbol="BTCUSDT", timeframe="15m",
        direction="bullish", regime="ranging", outcome="win", detail_label="tp3_hit",
        resolved_at=None, schema_version=1, source="live",
        entry_price=100.0, sl_price=95.0, tp1_price=105.0, tp2_price=110.0, tp3_price=120.0,
        mfe_r=4.0, mae_r=0.2, mfe_atr=4.0, mae_atr=0.2, mfe_pct=20.0, mae_pct=1.0,
        bars_total=12, mfe_bar_idx=8, mae_bar_idx=2, sl_dist_pct=5.0, atr_pct_at_signal=5.0,
        cur_reached_tp1=True, cur_reached_tp2=True, cur_reached_tp3=True, cur_bars_to_tp1=3,
        cur_post_tp1_mfe_r=1.0, cur_post_tp1_mae_r=0.05, cur_gave_back_after_tp1=False,
        cur_realized_return=9.5, intrabar_ambiguous=False, still_forming_resolution=False,
    )
    row.update(over)
    return to_path_record(row)


def _set3():
    return [
        _rec(),  # all TP → FixedCurrent 1.9R
        _rec(tp1_price=105.0, cur_reached_tp2=False, cur_reached_tp3=False,
             cur_gave_back_after_tp1=True, outcome="breakeven", cur_realized_return=2.5,
             detail_label="tp1_then_breakeven"),  # tp1 only → 0.5R, give-back
        _rec(cur_reached_tp1=False, cur_reached_tp2=False, cur_reached_tp3=False,
             outcome="loss", cur_realized_return=-5.0, detail_label="sl_hit"),  # -1.0R
    ]


def test_pct_helper():
    assert _pct([-1.0, 0.5, 1.9], 0.5) == 0.5
    assert abs(_pct([-1.0, 0.5, 1.9], 0.25) - (-0.25)) < 1e-9


def test_metrics_known_set():
    s = score_policy(_set3(), FixedCurrent())          # rs = [1.9, 0.5, -1.0]
    assert s.n == 3
    assert abs(s.expectancy_r - 0.4667) < 1e-3
    assert s.profit_factor == 2.4                       # 2.4 / 1.0
    assert s.win_rate == 66.7
    assert s.median_r == 0.5
    assert abs(s.p25_r - (-0.25)) < 1e-9
    assert s.giveback_rate == 50.0                      # 1 of 2 TP1-reached gave back


def test_compare_baseline_and_uplift():
    class AllOutTp1(Policy):
        name = "AllOutTP1"
        def decide_tp1(self, ctx):
            return ManagementDecision(tp1_scale_frac=1.0, remainder_mode="BREAKEVEN")
    rep = compare_policies(_set3(), [FixedCurrent(), AllOutTp1()])
    assert rep["baseline"] == "FixedCurrent" and rep["n"] == 3
    base, alt = rep["rows"][0], rep["rows"][1]
    assert base["uplift_vs_baseline"] == {"expectancy_r": 0.0, "giveback_rate": 0.0, "p25_r": 0.0}
    # AllOutTP1 takes 100% at TP1 → all-TP rec yields 1.0R (not 1.9R) → lower expectancy
    assert alt["uplift_vs_baseline"]["expectancy_r"] < 0


def test_reconstructable_filter_applied():
    recs = _set3() + [_rec(detail_label="expired_loss", cur_reached_tp1=False,
                           outcome="loss", cur_realized_return=-3.0)]
    rep = compare_policies(recs, [FixedCurrent()])
    assert rep["n"] == 3  # the expiry row is filtered out


_TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]


def main() -> int:
    failed = 0
    for t in _TESTS:
        try:
            t()
            print(f"  ok   {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"{'PASS' if not failed else 'FAILED'} {len(_TESTS) - failed}/{len(_TESTS)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
