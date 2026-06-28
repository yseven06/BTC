"""
Unit tests for the fidelity comparator — NO DB.

Run:  python -m app.trade_mgmt.tests.test_fidelity
"""

import sys

from app.trade_mgmt.fidelity import compare_record, run_fidelity
from app.trade_mgmt.path_reader import to_path_record


def _rec(**over):
    """entry=100, sl=95 (sl_dist=5%); tp1=105(1R), tp2=110(2R), tp3=120(4R)."""
    row = dict(
        signal_id="sig-xxxxxxxx", asset_id=None, symbol="BTCUSDT", timeframe="15m",
        direction="bullish", regime="ranging", outcome="win", detail_label="tp3_hit",
        resolved_at=None, schema_version=1, source="live",
        entry_price=100.0, sl_price=95.0, tp1_price=105.0, tp2_price=110.0, tp3_price=120.0,
        mfe_r=4.0, mae_r=0.2, mfe_atr=4.0, mae_atr=0.2, mfe_pct=20.0, mae_pct=1.0,
        bars_total=12, mfe_bar_idx=8, mae_bar_idx=2, sl_dist_pct=5.0, atr_pct_at_signal=5.0,
        cur_reached_tp1=True, cur_reached_tp2=True, cur_reached_tp3=True, cur_bars_to_tp1=3,
        cur_post_tp1_mfe_r=1.0, cur_post_tp1_mae_r=0.05, cur_gave_back_after_tp1=False,
        cur_realized_return=9.5,  # = 1.9R * 5%   (matches FixedCurrent replay)
        intrabar_ambiguous=False, still_forming_resolution=False,
    )
    row.update(over)
    return to_path_record(row)


def test_eligible_exact_match():
    f = compare_record(_rec())          # replay_r = 1.9 ; observed = 9.5/5 = 1.9
    assert f.eligible and f.realized_match and f.outcome_match and f.giveback_match
    assert abs(f.replay_r - 1.9) < 1e-9


def test_giveback_tiny_tp1_breakeven():
    # +0.25% "TP1 alındı ama küçük" senaryosu: tp1=100.5 → tp1_r=0.1 → replay 0.05R → 0.25%
    f = compare_record(_rec(
        tp1_price=100.5, cur_reached_tp2=False, cur_reached_tp3=False,
        cur_gave_back_after_tp1=True, outcome="breakeven", cur_realized_return=0.25,
        detail_label="tp1_then_breakeven"))
    assert f.realized_match, (f.replay_r, f.observed_r)
    assert f.replay_outcome == "breakeven" and f.outcome_match
    assert f.giveback_match and f.replay_giveback is True


def test_full_stop_match():
    f = compare_record(_rec(
        cur_reached_tp1=False, cur_reached_tp2=False, cur_reached_tp3=False,
        outcome="loss", cur_realized_return=-5.0, detail_label="sl_hit"))
    assert f.replay_r == -1.0 and f.realized_match and f.outcome_match


def test_still_forming_excluded():
    f = compare_record(_rec(still_forming_resolution=True))
    assert f.eligible is False and f.exclude_reason == "live_sl/still_forming"


def test_expiry_excluded():
    # expired loss without TP1 — close price not stored → not reconstructable
    f = compare_record(_rec(
        cur_reached_tp1=False, cur_reached_tp2=False, cur_reached_tp3=False,
        outcome="loss", detail_label="expired_loss", cur_realized_return=-3.86))
    assert f.eligible is False and f.exclude_reason == "expiry"


def test_tp1_then_expiry_excluded():
    f = compare_record(_rec(cur_reached_tp2=False, cur_reached_tp3=False,
                            detail_label="tp1_hit", outcome="win", cur_realized_return=1.87))
    assert f.eligible is False and f.exclude_reason == "tp1_then_expiry"


def test_low_precision_excluded():
    # micro-cap: stored 8-decimal prices can't reproduce stored sl_dist_pct
    f = compare_record(_rec(
        entry_price=0.00000422, sl_price=0.00000424, tp1_price=0.00000420,
        tp2_price=0.00000416, tp3_price=0.00000413, sl_dist_pct=0.5931,
        detail_label="tp1_then_breakeven", cur_reached_tp2=False, cur_reached_tp3=False,
        outcome="breakeven", cur_realized_return=0.1779))
    assert f.eligible is False and f.exclude_reason == "low_precision"


def test_mismatch_detected_and_rejected():
    # reached all TP (replay 1.9R) but observed realized inconsistent (0.0) → mismatch
    bad = _rec(cur_realized_return=0.0)
    f = compare_record(bad)
    assert f.realized_match is False
    rep = run_fidelity([bad])
    assert rep["accept"] is False and len(rep["mismatches"]) == 1


def test_accept_on_clean_set():
    recs = [
        _rec(),  # tp3_hit
        _rec(tp1_price=100.5, cur_reached_tp2=False, cur_reached_tp3=False,
             cur_gave_back_after_tp1=True, outcome="breakeven", cur_realized_return=0.25,
             detail_label="tp1_then_breakeven"),
        _rec(cur_reached_tp1=False, cur_reached_tp2=False, cur_reached_tp3=False,
             outcome="loss", cur_realized_return=-5.0, detail_label="sl_hit"),
    ]
    rep = run_fidelity(recs)
    assert rep["accept"] is True, rep
    assert rep["eligible"]["realized_rate"] == 100.0


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
