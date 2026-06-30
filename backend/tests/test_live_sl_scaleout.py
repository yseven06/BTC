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


def _old_live_sl_realized(direction, entry, original_sl):
    """FROZEN snapshot of the OLD live-SL accounting (always full position at the
    original stop) — the before/after baseline."""
    ret = (original_sl - entry) / entry if direction == "bullish" else (entry - original_sl) / entry
    return ret  # full notional


_SCENARIOS = [
    # (label, direction, entry, original_sl, tp1, tp2, hit_tp1, hit_tp2)
    ("TP1-not-hit",  "bullish", 100.0, 96.0, 103.0, 106.0, False, False),
    ("TP1-banked",   "bullish", 100.0, 96.0, 103.0, 106.0, True,  False),
    ("TP1+TP2",      "bullish", 100.0, 96.0, 103.0, 106.0, True,  True),
    ("TP1-not-hit-bear", "bearish", 100.0, 104.0, 97.0, 94.0, False, False),
    ("TP1-banked-bear",  "bearish", 100.0, 104.0, 97.0, 94.0, True,  False),
]


def _build_live_sl_row(direction, entry, original_sl, tp1, tp2, hit_tp1, hit_tp2):
    from app.backtesting.trade_path import compute_trade_path
    realized, eff_sl, gave_back = live_sl_realized(direction, entry, original_sl, tp1, tp2, hit_tp1, hit_tp2)
    row = compute_trade_path(
        signal_id="00000000-0000-0000-0000-000000000001",
        direction=direction, entry=entry, sl=eff_sl, tp1=tp1, tp2=tp2, tp3=tp2,
        mfe_pct=None, mae_pct=None, atr_pct=2.0,
        reached_tp1=hit_tp1, reached_tp2=hit_tp2, reached_tp3=False,
        gave_back_after_tp1=gave_back, realized_return=realized,
        still_forming_resolution=True, resolution_source="live_sl", source="live",
        generated_at=None,
    )
    return realized, eff_sl, gave_back, row


def test_live_sl_trade_path_consistency():
    """trade_path row must be self-consistent: reached_tp1 ↔ realized ↔ gave_back ↔
    schema_version=2; and TP1-not-hit realized == OLD (byte-identical)."""
    from app.models.intelligence import TRADE_PATH_SCHEMA_VERSION
    assert TRADE_PATH_SCHEMA_VERSION == 2
    for label, d, e, osl, t1, t2, h1, h2 in _SCENARIOS:
        realized, eff_sl, gave_back, row = _build_live_sl_row(d, e, osl, t1, t2, h1, h2)
        assert row.schema_version == 2, label
        assert bool(row.cur_reached_tp1) == h1 and bool(row.cur_reached_tp2) == h2, label
        assert round(float(row.cur_realized_return), 4) == round(realized, 4), label
        if h1:
            assert row.cur_gave_back_after_tp1 == (h1 and not h2), label
            assert realized >= 0.0, label                       # banked, not a full loss
            assert round(eff_sl, 6) == round(e, 6), label       # effective stop = breakeven (entry)
        else:
            assert row.cur_gave_back_after_tp1 is None, label
            assert round(realized, 6) == round(_old_live_sl_realized(d, e, osl), 6), label  # byte-identical
            assert round(eff_sl, 6) == round(osl, 6), label     # original stop unchanged


def test_legacy_contradictory_predicate():
    from types import SimpleNamespace as NS
    from app.backtesting.trade_path import is_legacy_contradictory_live_sl
    P = is_legacy_contradictory_live_sl
    # v1 live-SL, TP1 banked, gave_back NULL -> CONTRADICTORY
    assert P(NS(schema_version=1, still_forming_resolution=True, cur_reached_tp1=True, cur_gave_back_after_tp1=None)) is True
    # v2 (post-KEY1-d) -> not contradictory
    assert P(NS(schema_version=2, still_forming_resolution=True, cur_reached_tp1=True, cur_gave_back_after_tp1=None)) is False
    # v1 but TP1 not hit -> not contradictory
    assert P(NS(schema_version=1, still_forming_resolution=True, cur_reached_tp1=False, cur_gave_back_after_tp1=None)) is False
    # v1 bar-walk (not still_forming) -> not contradictory
    assert P(NS(schema_version=1, still_forming_resolution=False, cur_reached_tp1=True, cur_gave_back_after_tp1=None)) is False
    # v1 live-SL but gave_back already set -> not contradictory
    assert P(NS(schema_version=1, still_forming_resolution=True, cur_reached_tp1=True, cur_gave_back_after_tp1=True)) is False


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t(); print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} live_sl tests PASSED")

    print("\n==== BEFORE/AFTER (live-SL accounting) ====")
    print(f"{'scenario':<18} {'OLD realized%':>13} {'NEW realized%':>13} {'NEW outcome':>12} "
          f"{'reached_tp1':>11} {'gave_back':>10}")
    for label, d, e, osl, t1, t2, h1, h2 in _SCENARIOS:
        old_r = _old_live_sl_realized(d, e, osl) * 100.0
        realized, eff_sl, gb, row = _build_live_sl_row(d, e, osl, t1, t2, h1, h2)
        new_r = realized * 100.0
        oc = "WIN" if new_r > 0.5 else ("LOSS" if new_r < -0.5 else "BREAKEVEN")
        print(f"{label:<18} {round(old_r,2):>13} {round(new_r,2):>13} {oc:>12} "
              f"{str(h1):>11} {str(gb):>10}")
