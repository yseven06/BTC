"""P11-0: additive backtest observability (realized-R helper + BacktestReport defaults)."""
from app.backtesting.engine import _realized_r, BacktestReport


def test_realized_r():
    assert _realized_r(100, 96, 4.0) == 1.0       # +4% over 4% risk = 1R
    assert _realized_r(100, 96, -4.0) == -1.0      # full SL hit = -1R
    assert _realized_r(100, 96, 6.0) == 1.5
    assert _realized_r(100, 100, 5.0) is None      # zero risk distance
    assert _realized_r(0, 96, 5.0) is None         # zero entry


def test_backtest_report_new_fields_default():
    """The P11-0 fields are additive with defaults → existing constructors don't break."""
    r = BacktestReport(
        total_trades=0, wins=0, losses=0, breakevens=0, expired=0,
        win_rate=0.0, loss_rate=0.0, profit_factor=0.0, sharpe_ratio=0.0,
        sortino_ratio=None, max_drawdown_pct=0.0, average_return_pct=0.0,
        average_rr=0.0, expectancy_pct=0.0, max_consecutive_wins=0, max_consecutive_losses=0,
    )
    assert r.avg_planned_rr_tp1 is None and r.median_planned_rr_tp1 is None
    assert r.sub_1_rr_pct is None
    assert r.tp1_reach_rate == 0.0 and r.tp2_reach_rate == 0.0 and r.tp3_reach_rate == 0.0
    assert r.avg_realized_r is None and r.median_realized_r is None


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t(); print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} P11-0 backtest-metric tests PASSED")
