"""
Golden unit tests for the replay engine — NO DB.

Run:  python -m app.trade_mgmt.tests.test_replay

Covers: FixedCurrent reconstruction math (R-multiples), give-back, full-stop,
determinism, and PLUGGABILITY (a brand-new policy defined here runs through the
unchanged replay core).
"""

import sys

from app.trade_mgmt.path_reader import to_path_record
from app.trade_mgmt.policies.base import Policy
from app.trade_mgmt.policies.catalog import (
    AdaptiveScaleOut, FixedCurrent, HardBE, Trailing, adaptive_tp1_frac,
)
from app.trade_mgmt.replay import build_tp1_context, replay
from app.trade_mgmt.types import ManagementDecision


def _rec(**over):
    """Build a PathRecord via the real reader. Geometry: entry=100, sl=95,
    tp1=105 (1R), tp2=110 (2R), tp3=120 (4R)."""
    row = dict(
        signal_id="s", asset_id=None, symbol="BTCUSDT", timeframe="15m",
        direction="bullish", regime="ranging", outcome="win", detail_label=None,
        resolved_at=None, schema_version=1, source="live",
        entry_price=100.0, sl_price=95.0, tp1_price=105.0, tp2_price=110.0, tp3_price=120.0,
        mfe_r=1.0, mae_r=0.3, mfe_atr=1.0, mae_atr=0.3, mfe_pct=5.0, mae_pct=1.5,
        bars_total=10, mfe_bar_idx=5, mae_bar_idx=2, sl_dist_pct=5.0, atr_pct_at_signal=5.0,
        cur_reached_tp1=True, cur_reached_tp2=True, cur_reached_tp3=True, cur_bars_to_tp1=3,
        cur_post_tp1_mfe_r=1.0, cur_post_tp1_mae_r=0.05, cur_gave_back_after_tp1=False,
        cur_realized_return=1.5, intrabar_ambiguous=False, still_forming_resolution=False,
    )
    row.update(over)
    return to_path_record(row)


def test_fixedcurrent_all_targets():
    # 0.5*1 + 0.3*2 + 0.2*4 = 1.9
    r = replay(_rec(), FixedCurrent())
    assert r.realized_r == 1.9, r.realized_r
    assert r.exit_reason == "scaleout_be"


def test_fixedcurrent_tp1_only_giveback():
    # 0.5*1 + 0.5*0(BE) = 0.5 ; gave_back True
    r = replay(_rec(cur_reached_tp2=False, cur_reached_tp3=False,
                    outcome="breakeven", cur_gave_back_after_tp1=True), FixedCurrent())
    assert r.realized_r == 0.5, r.realized_r
    assert r.gave_back is True


def test_fixedcurrent_tp1_tp2_no_tp3():
    # 0.5*1 + 0.3*2 + 0.2*0(BE) = 1.1 ; not gave_back (reached tp2)
    r = replay(_rec(cur_reached_tp3=False), FixedCurrent())
    assert r.realized_r == 1.1, r.realized_r
    assert r.gave_back is False


def test_full_stop_no_tp1():
    r = replay(_rec(cur_reached_tp1=False, cur_reached_tp2=False, cur_reached_tp3=False,
                    outcome="loss"), FixedCurrent())
    assert r.realized_r == -1.0, r.realized_r
    assert r.exit_reason == "full_sl"


def test_determinism():
    rec = _rec()
    a, b = replay(rec, FixedCurrent()), replay(rec, FixedCurrent())
    assert a == b


def test_replay_core_is_policy_agnostic_pluggable():
    """A NEW policy defined right here runs through the UNCHANGED replay core."""
    class TrailDummy(Policy):
        name = "TrailDummy"
        def decide_tp1(self, ctx):
            return ManagementDecision(tp1_scale_frac=0.20, remainder_mode="TRAIL",
                                      trail_rule="R_K", trail_k=0.5, reason="test")
    # post_tp1_mfe_r=2.0, no tp2 → cap = max(0, 2.0-0.5)=1.5
    # realized = 0.2*1.0 + 0.8*1.5 = 1.4
    r = replay(_rec(cur_reached_tp2=False, cur_reached_tp3=False,
                    cur_post_tp1_mfe_r=2.0, outcome="breakeven"), TrailDummy())
    assert r.realized_r == 1.4, r.realized_r
    assert "trail_approx" in r.flags
    assert r.confidence < 1.0


def test_hardbe_banks_more_on_big_run_less_than_fixed():
    # all TP: HardBE = 0.7*1 + 0.3*2 = 1.3  (< FixedCurrent 1.9 — trades upside)
    rec = _rec()
    assert replay(rec, HardBE()).realized_r == 1.3
    assert replay(rec, FixedCurrent()).realized_r == 1.9


def test_hardbe_protects_more_on_giveback():
    # TP1 only, give-back: HardBE = 0.7*1 + 0.3*0(BE) = 0.7  (> FixedCurrent 0.5)
    rec = _rec(cur_reached_tp2=False, cur_reached_tp3=False,
               outcome="breakeven", cur_gave_back_after_tp1=True)
    hb = replay(rec, HardBE())
    assert hb.realized_r == 0.7 and hb.gave_back is True
    assert replay(rec, FixedCurrent()).realized_r == 0.5


def test_trailing_captures_post_tp1_run_approx():
    # TP1 only, post_tp1_mfe_r=2.0: Trailing = 0.3*1 + 0.7*max(0,2.0-0.5)=0.3+1.05=1.35
    rec = _rec(cur_reached_tp2=False, cur_reached_tp3=False,
               cur_post_tp1_mfe_r=2.0, outcome="win")
    r = replay(rec, Trailing())
    assert r.realized_r == 1.35
    assert "trail_approx" in r.flags and r.confidence < 1.0
    # vs FixedCurrent hard-BE on the same give-back path = 0.5 → trailing captures more
    assert replay(rec, FixedCurrent()).realized_r == 0.5


def test_adaptive_tp1_significance_curve():
    assert adaptive_tp1_frac(0.4) == 0.20   # near TP1 → small
    assert adaptive_tp1_frac(0.8) == 0.33
    assert adaptive_tp1_frac(1.2) == 0.50
    assert adaptive_tp1_frac(2.0) == 0.60
    assert adaptive_tp1_frac(4.0) == 0.70   # meaningful TP1 → bank more
    assert adaptive_tp1_frac(None) == 0.50  # safe default


def test_adaptive_near_tp1_trails_else_be():
    near = AdaptiveScaleOut().decide_tp1(build_tp1_context(_rec(tp1_price=102.0)))  # tp1_r=0.4
    assert near.tp1_scale_frac == 0.20 and near.remainder_mode == "TRAIL"
    far = AdaptiveScaleOut().decide_tp1(build_tp1_context(_rec(tp1_price=106.0)))   # tp1_r=1.2
    assert far.tp1_scale_frac == 0.50 and far.remainder_mode == "BREAKEVEN"


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
