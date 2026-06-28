"""
Pure unit tests for PathReader — NO DB required.

Run:  python -m app.trade_mgmt.tests.test_path_reader
(Also pytest-compatible: every test_* function is a standalone assertion.)
"""

import sys

from app.trade_mgmt.path_reader import _derive_sl_before_tp, to_path_record


def _row(**over):
    """A complete, valid signal_trade_path row mapping; override per test."""
    base = dict(
        signal_id="s1", asset_id=None, symbol="BTCUSDT", timeframe="15m",
        direction="bullish", regime="ranging", outcome="breakeven", detail_label="tp1_then_breakeven",
        resolved_at=None, schema_version=1, source="live",
        entry_price=100.0, sl_price=95.0, tp1_price=102.5, tp2_price=105.0, tp3_price=110.0,
        mfe_r=0.8, mae_r=0.3, mfe_atr=1.2, mae_atr=0.4, mfe_pct=2.0, mae_pct=0.7,
        bars_total=10, mfe_bar_idx=4, mae_bar_idx=2, sl_dist_pct=5.0, atr_pct_at_signal=1.0,
        cur_reached_tp1=True, cur_reached_tp2=False, cur_reached_tp3=False, cur_bars_to_tp1=3,
        cur_post_tp1_mfe_r=0.9, cur_post_tp1_mae_r=0.05, cur_gave_back_after_tp1=True,
        cur_realized_return=0.3, intrabar_ambiguous=False, still_forming_resolution=False,
    )
    base.update(over)
    return base


def test_tp1_r_is_reward_over_risk():
    r = to_path_record(_row())                 # |102.5-100| / |100-95| = 2.5/5
    assert r.tp1_r == 0.5, r.tp1_r


def test_tp1_atr_in_atr_units():
    r = to_path_record(_row(tp1_price=102.0, atr_pct_at_signal=1.0))  # 2 / (1% of 100 = 1.0)
    assert r.tp1_atr == 2.0, r.tp1_atr


def test_sl_before_tp_truth_table():
    assert _derive_sl_before_tp(True, "breakeven", False) is False   # TP1 first
    assert _derive_sl_before_tp(False, "loss", False) is True        # clean stop
    assert _derive_sl_before_tp(True, "loss", True) is None          # intrabar wins → unknown
    assert _derive_sl_before_tp(False, "win", False) is None         # no SL, no TP1 → unknown
    assert _derive_sl_before_tp(False, "expired", False) is None


def test_sl_before_tp_wired_into_record():
    assert to_path_record(_row(cur_reached_tp1=True)).sl_before_tp is False
    assert to_path_record(_row(cur_reached_tp1=False, outcome="loss")).sl_before_tp is True
    assert to_path_record(_row(intrabar_ambiguous=True)).sl_before_tp is None


def test_confidence_flags():
    r = to_path_record(_row(still_forming_resolution=True, mfe_r=None))
    assert "still_forming" in r.confidence_flags
    assert "no_mfe" in r.confidence_flags
    assert "intrabar_ambiguous" in to_path_record(_row(intrabar_ambiguous=True)).confidence_flags
    assert "no_tp2_price" in to_path_record(_row(tp2_price=None)).confidence_flags


def test_none_safety_no_crash():
    r = to_path_record(_row(entry_price=None, sl_price=None, tp1_price=None, atr_pct_at_signal=None))
    assert r.tp1_r is None and r.tp1_atr is None
    assert r.entry is None


def test_numeric_coercion():
    # DB Numeric arrives as Decimal/str-like; ensure floats out.
    from decimal import Decimal
    r = to_path_record(_row(entry_price=Decimal("100"), sl_price=Decimal("95"), tp1_price=Decimal("102.5")))
    assert isinstance(r.entry, float) and r.tp1_r == 0.5


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
