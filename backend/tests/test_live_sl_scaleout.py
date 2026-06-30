"""KEY1-d: unit tests for live_sl_realized — the live-SL resolution that honors the
stored TP1/TP2 scale-out (BUG-6/7/8 fix).

TP1-not-hit MUST stay byte-identical to the old full-original-stop loss; TP1/TP2-banked
cases book the banked portions + the remainder at breakeven (NOT a full loss).

Run: PYTHONPATH=backend python tests/test_live_sl_scaleout.py
"""

from app.backtesting.tracker import live_sl_realized

R = 6


def test_tp1_not_hit_bull_byte_identical():
    # Old behaviour: full size at the original stop. realized = (96-100)/100 = -0.04.
    realized, eff, gb = live_sl_realized("bullish", 100.0, 96.0, 103.0, 106.0, hit_tp1=False, hit_tp2=False)
    assert round(realized, R) == round(-0.04, R) and eff == 96.0 and gb is None


def test_tp1_banked_bull():
    # 0.5*TP1 + 0.5*BE(0) = 0.5*0.03 = 0.015; effective stop = breakeven (entry).
    realized, eff, gb = live_sl_realized("bullish", 100.0, 96.0, 103.0, 106.0, hit_tp1=True, hit_tp2=False)
    assert round(realized, R) == round(0.015, R) and eff == 100.0 and gb is True


def test_tp1_tp2_banked_bull():
    # 0.5*0.03 + 0.3*0.06 + 0.2*BE(0) = 0.015 + 0.018 = 0.033.
    realized, eff, gb = live_sl_realized("bullish", 100.0, 96.0, 103.0, 106.0, hit_tp1=True, hit_tp2=True)
    assert round(realized, R) == round(0.033, R) and eff == 100.0 and gb is False


def test_tp1_not_hit_bear_byte_identical():
    realized, eff, gb = live_sl_realized("bearish", 100.0, 104.0, 97.0, 94.0, hit_tp1=False, hit_tp2=False)
    assert round(realized, R) == round(-0.04, R) and eff == 104.0 and gb is None


def test_tp1_banked_bear():
    # 0.5*(100-97)/100 = 0.015; BE = entry.
    realized, eff, gb = live_sl_realized("bearish", 100.0, 104.0, 97.0, 94.0, hit_tp1=True, hit_tp2=False)
    assert round(realized, R) == round(0.015, R) and eff == 100.0 and gb is True


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t(); print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} live_sl_realized tests PASSED")
