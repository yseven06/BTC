"""F1 — closed-candle decision integrity.

Every signal job fires 1-3 minutes into a fresh candle and Binance always returns
the candle currently forming, so every indicator, every engine and the regime
detector were measuring a bar that was a fraction complete. Measured on 1 998
production candidate rows, the median `volume_ratio` tracked the elapsed fraction
of each timeframe almost exactly (15m 0.1109 vs 2/15; 4h 0.0081 vs 2/240), and
BREAKOUT — which needs volume > 1.8x — occurred once in 3 375 snapshots.

The fix splits one frame into two views rather than dropping a row:

    df_full    the collector's output, forming candle included
               -> current_price, the anchor for entry/SL/TP
               -> the chart, and the tracker's deliberate use of it

    df_closed  only bars whose close_time has passed, per timeframe, in UTC
               -> ATR, indicators, patterns, regime, all nine engines, MTF

The distinction these tests protect is "closed" vs "last", not "keep" vs "drop":
a bar that has genuinely closed must survive even when it is the final row.
"""
import inspect
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.services.candle_window import (
    CLOSE_TIME_COLUMN,
    TIMEFRAME_DURATIONS,
    UnknownTimeframeError,
    analysis_window,
    closed_candles,
)

UTC = timezone.utc


def _frame(start, n, timeframe, *, tz="UTC", with_close_time=True, volumes=None):
    """A well-formed OHLCV frame, mirroring the collector's output shape."""
    dur = TIMEFRAME_DURATIONS[timeframe]
    opens = [start + i * dur for i in range(n)]
    idx = pd.DatetimeIndex(opens)
    if tz is None:
        idx = idx.tz_localize(None) if idx.tz is not None else idx
    data = {
        "open": [100.0 + i for i in range(n)],
        "high": [101.0 + i for i in range(n)],
        "low": [99.0 + i for i in range(n)],
        "close": [100.5 + i for i in range(n)],
        "volume": list(volumes) if volumes is not None else [1000.0] * n,
    }
    df = pd.DataFrame(data, index=idx)
    if with_close_time:
        # Binance's close_time is the last millisecond of the bar.
        df[CLOSE_TIME_COLUMN] = [o + dur - timedelta(milliseconds=1) for o in opens]
    return df


# ── 4-8 · the closing boundary, per timeframe ──────────────────────────────
@pytest.mark.parametrize("tf", ["15m", "1h", "4h", "1d"])
def test_forming_last_bar_is_excluded(tf):
    dur = TIMEFRAME_DURATIONS[tf]
    start = datetime(2026, 7, 28, 0, 0, tzinfo=UTC)
    df = _frame(start, 5, tf)
    # Two minutes into the final bar — exactly when the jobs fire.
    now = start + 4 * dur + timedelta(minutes=2)

    w = analysis_window(df, tf, now=now)
    assert len(w.df) == 4, f"{tf}: forming bar must be excluded"
    assert w.dropped_forming == 1
    assert w.last_bar_open_time == start + 3 * dur
    assert w.last_bar_closed is True
    assert df.shape[0] == 5, "the caller's frame must not be mutated"


@pytest.mark.parametrize("tf", ["15m", "1h", "4h", "1d"])
def test_closed_last_bar_is_kept(tf):
    """The distinction is closed-vs-last. A blind iloc[:-1] fails this."""
    dur = TIMEFRAME_DURATIONS[tf]
    start = datetime(2026, 7, 28, 0, 0, tzinfo=UTC)
    df = _frame(start, 5, tf)
    now = start + 5 * dur + timedelta(seconds=30)   # every bar has closed

    w = analysis_window(df, tf, now=now)
    assert len(w.df) == 5, f"{tf}: a closed final bar must survive"
    assert w.dropped_forming == 0
    assert w.last_bar_open_time == start + 4 * dur


def test_boundary_is_exact_at_the_closing_instant():
    tf = "15m"
    start = datetime(2026, 7, 28, 0, 0, tzinfo=UTC)
    df = _frame(start, 3, tf)
    last_close = start + 3 * TIMEFRAME_DURATIONS[tf] - timedelta(milliseconds=1)

    assert len(analysis_window(df, tf, now=last_close - timedelta(milliseconds=1)).df) == 2
    assert len(analysis_window(df, tf, now=last_close).df) == 3


def test_1d_boundary_is_utc_not_local():
    """A local-midnight boundary would shift the daily cut by hours."""
    start = datetime(2026, 7, 20, 0, 0, tzinfo=UTC)
    df = _frame(start, 3, "1d")
    # 23:30 UTC on the final day: still forming in UTC, already "tomorrow" in
    # UTC+2 — where the local reading would wrongly admit it.
    now = datetime(2026, 7, 22, 23, 30, tzinfo=UTC)
    w = analysis_window(df, "1d", now=now)
    assert len(w.df) == 2
    assert w.last_bar_open_time == datetime(2026, 7, 21, 0, 0, tzinfo=UTC)


# ── 9-10 · close_time is primary, derivation is the fallback ───────────────
def test_binance_close_time_is_the_primary_source():
    tf = "15m"
    start = datetime(2026, 7, 28, 0, 0, tzinfo=UTC)
    df = _frame(start, 4, tf)
    # A close_time that disagrees with open_time + duration: if the column is
    # really primary, the window follows the column.
    df.loc[df.index[-1], CLOSE_TIME_COLUMN] = start + 10 * TIMEFRAME_DURATIONS[tf]
    now = start + 4 * TIMEFRAME_DURATIONS[tf] + timedelta(minutes=1)

    w = analysis_window(df, tf, now=now)
    assert len(w.df) == 3, "close_time column must win over the derived value"


def test_fallback_when_close_time_absent():
    tf = "1h"
    start = datetime(2026, 7, 28, 0, 0, tzinfo=UTC)
    df = _frame(start, 4, tf, with_close_time=False)
    now = start + 3 * TIMEFRAME_DURATIONS[tf] + timedelta(minutes=1)

    w = analysis_window(df, tf, now=now)
    assert len(w.df) == 3
    assert w.last_bar_close_time == start + 3 * TIMEFRAME_DURATIONS[tf]


def test_partially_null_close_time_falls_back_wholesale():
    """A mixture of sources is worse than one consistent rule."""
    tf = "15m"
    start = datetime(2026, 7, 28, 0, 0, tzinfo=UTC)
    df = _frame(start, 4, tf)
    df.loc[df.index[1], CLOSE_TIME_COLUMN] = pd.NaT
    now = start + 3 * TIMEFRAME_DURATIONS[tf] + timedelta(minutes=1)

    w = analysis_window(df, tf, now=now)
    assert len(w.df) == 3, "must use the derived rule for every row, not per-row"


# ── 11-14 · malformed input ────────────────────────────────────────────────
def test_naive_index_is_treated_as_utc():
    tf = "15m"
    start = datetime(2026, 7, 28, 0, 0, tzinfo=UTC)
    df = _frame(start, 4, tf, with_close_time=False)
    df.index = df.index.tz_localize(None)
    now = start + 3 * TIMEFRAME_DURATIONS[tf] + timedelta(minutes=1)

    w = analysis_window(df, tf, now=now)
    assert len(w.df) == 3
    assert w.df.index.tz is not None, "the analysis view must be tz-aware"


def test_naive_now_is_treated_as_utc():
    tf = "15m"
    start = datetime(2026, 7, 28, 0, 0, tzinfo=UTC)
    df = _frame(start, 4, tf)
    naive_now = (start + 3 * TIMEFRAME_DURATIONS[tf] + timedelta(minutes=1)).replace(tzinfo=None)
    assert len(analysis_window(df, tf, now=naive_now).df) == 3


def test_out_of_order_frame_is_sorted():
    tf = "15m"
    start = datetime(2026, 7, 28, 0, 0, tzinfo=UTC)
    df = _frame(start, 5, tf).iloc[[3, 0, 4, 1, 2]]
    now = start + 4 * TIMEFRAME_DURATIONS[tf] + timedelta(minutes=2)

    w = analysis_window(df, tf, now=now)
    assert list(w.df.index) == sorted(w.df.index)
    assert len(w.df) == 4, "ordering must not change which bars are closed"


def test_duplicate_bars_resolve_to_the_last_copy():
    """The exchange re-sends a forming bar; the later copy is the fuller one."""
    tf = "15m"
    start = datetime(2026, 7, 28, 0, 0, tzinfo=UTC)
    df = _frame(start, 4, tf)
    dup = df.iloc[[2]].copy()
    dup["volume"] = 9999.0
    df = pd.concat([df, dup]).sort_index()
    now = start + 4 * TIMEFRAME_DURATIONS[tf]

    w = analysis_window(df, tf, now=now)
    assert len(w.df) == 4
    assert float(w.df["volume"].iloc[2]) == 9999.0


def test_gap_in_series_does_not_close_a_bar_early():
    tf = "15m"
    dur = TIMEFRAME_DURATIONS[tf]
    start = datetime(2026, 7, 28, 0, 0, tzinfo=UTC)
    df = _frame(start, 6, tf).drop(index=[start + 2 * dur, start + 3 * dur])
    now = start + 5 * dur + timedelta(minutes=1)

    w = analysis_window(df, tf, now=now)
    assert w.last_bar_open_time == start + 4 * dur, "gaps must not shift the boundary"
    assert w.dropped_forming == 1


def test_default_now_is_utc_aware_not_local():
    """Every other test passes `now` explicitly, so the default path needs its
    own cover: a local-clock default would shift the boundary by the machine's
    UTC offset — silently correct on a UTC host and wrong everywhere else."""
    src = inspect.getsource(analysis_window)
    assert "datetime.now(timezone.utc)" in src
    assert "datetime.now()" not in src.replace("datetime.now(timezone.utc)", "")

    # And behaviourally: a bar closing an hour from now must be excluded, one
    # that closed an hour ago must be kept — with no `now` argument at all.
    tf = "1h"
    dur = TIMEFRAME_DURATIONS[tf]
    start = datetime.now(UTC) - 3 * dur - timedelta(minutes=30)
    df = _frame(start, 4, tf)          # last bar closes ~30 min in the future
    w = analysis_window(df, tf)
    assert w.dropped_forming == 1
    assert w.last_bar_close_time is not None and w.last_bar_close_time < datetime.now(UTC)


def test_unknown_timeframe_raises_rather_than_guessing():
    df = _frame(datetime(2026, 7, 28, tzinfo=UTC), 3, "15m")
    with pytest.raises(UnknownTimeframeError):
        analysis_window(df, "3m")


def test_empty_and_all_forming_frames_are_safe():
    tf = "15m"
    start = datetime(2026, 7, 28, 0, 0, tzinfo=UTC)
    assert analysis_window(pd.DataFrame(), tf).df.empty
    assert analysis_window(None, tf).df.empty

    df = _frame(start, 2, tf)
    w = analysis_window(df, tf, now=start + timedelta(minutes=1))
    assert w.df.empty and w.last_bar_closed is False and w.last_bar_open_time is None


# ── 16 · the measured defect ───────────────────────────────────────────────
def test_volume_ratio_uses_only_closed_volume():
    """The defect in one assertion: the forming bar carried 2/15 of a bar's
    volume, so `volume_ratio` read ~0.13 and thin_tape fired on 83.6 % of 15m
    evaluations."""
    from app.engines.market_regime.detector import detect_regime

    tf = "15m"
    dur = TIMEFRAME_DURATIONS[tf]
    start = datetime(2026, 7, 20, 0, 0, tzinfo=UTC)
    vols = [1000.0] * 40 + [130.0]          # last bar = 2/15 of a normal bar
    df = _frame(start, 41, tf, volumes=vols)
    now = start + 40 * dur + timedelta(minutes=2)

    full = detect_regime(df)
    closed = detect_regime(analysis_window(df, tf, now=now).df)

    assert full.volume_ratio < 0.2, "reproduces the production reading"
    assert closed.volume_ratio > 0.9, "closed bars restore a truthful ratio"
    assert full.regime != closed.regime or full.volume_ratio != closed.volume_ratio


# ── 1-3 · what must NOT change ─────────────────────────────────────────────
def test_collector_still_returns_the_full_frame_with_the_forming_bar():
    from app.collectors import binance_collector

    src = inspect.getsource(binance_collector.BinanceCollector.fetch_ohlcv)
    assert "iloc[:-1]" not in src, "the collector must not go closed-only"
    assert "closed_candles" not in src and "analysis_window" not in src
    assert '"close_time"' in src, "close_time must be preserved"
    assert "utc=True" in src, "timestamps must be UTC-aware"
    for col in ("open", "high", "low", "close", "volume"):
        assert f'"{col}"' in src


def test_chart_and_tracker_consumers_are_untouched():
    from app.api.routes import prices
    from app.backtesting import tracker

    assert "closed_candles" not in inspect.getsource(prices)
    assert "analysis_window" not in inspect.getsource(prices)
    tsrc = inspect.getsource(tracker)
    assert "closed_candles" not in tsrc and "analysis_window" not in tsrc
    # The tracker's deliberate handling of the forming bar is still there.
    assert "still_forming" in tsrc


# ── 15, 17-23 · the decision path uses the closed view ─────────────────────
def test_analysis_view_actually_excludes_the_forming_bar():
    """Behavioural, not a source grep: the view is CALLED and its contents
    checked, so re-pointing it at the full frame cannot pass by leaving the
    variable name intact."""
    from app.engines.ai_decision.engine import _analysis_view

    tf = "15m"
    dur = TIMEFRAME_DURATIONS[tf]
    # The final bar must be the one CURRENTLY forming, so align the series to the
    # live 15m boundary rather than to an arbitrary offset in the past — building
    # it from `now - 10 bars` would make every bar closed and the assertion vacuous.
    now = datetime.now(UTC)
    current_open = now.replace(second=0, microsecond=0) - timedelta(minutes=now.minute % 15)
    df = _frame(current_open - 5 * dur, 6, tf)

    view, window = _analysis_view(df, tf, "TESTUSDT")
    assert len(view) < len(df), "the forming bar is still in the analysis view"
    assert window.dropped_forming >= 1
    assert view.index[-1] < df.index[-1]


def test_analysis_view_keeps_everything_when_all_bars_have_closed():
    from app.engines.ai_decision.engine import _analysis_view

    tf = "1h"
    dur = TIMEFRAME_DURATIONS[tf]
    start = datetime.now(UTC) - 20 * dur
    df = _frame(start, 5, tf)
    view, window = _analysis_view(df, tf, "TESTUSDT")
    assert len(view) == len(df)
    assert window.dropped_forming == 0


def test_orchestrator_feeds_engines_the_closed_frame():
    from app.engines.ai_decision import engine as orch

    import ast
    import textwrap

    src = inspect.getsource(orch.AIDecisionEngine.analyze_and_decide)
    assert "self._safe_run_engine(engine, symbol, timeframe, analysis_df" in src, \
        "all nine engines must receive the closed frame"
    assert "_derive_htf_boundaries(analysis_df" in src
    assert "generate_signal(\n            symbol, timeframe, analysis_df" in src

    # Where `analysis_df` COMES FROM, parsed rather than pattern-matched: a
    # string check passes even when the call is made and its result discarded
    # (`_analysis_view(...)[1]` alongside `analysis_df = ohlcv_data`), which is
    # exactly how this invariant would be broken by accident.
    tree = ast.parse(textwrap.dedent(src))
    sources = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = []
        for t in node.targets:
            targets.extend(
                [e.id for e in t.elts if isinstance(e, ast.Name)]
                if isinstance(t, ast.Tuple) else
                ([t.id] if isinstance(t, ast.Name) else [])
            )
        if "analysis_df" in targets:
            sources.append(node.value)

    assert len(sources) == 1, f"analysis_df must be assigned exactly once, got {len(sources)}"
    value = sources[0]
    assert isinstance(value, ast.Call) and isinstance(value.func, ast.Name) \
        and value.func.id == "_analysis_view", \
        "analysis_df must come straight from _analysis_view, not from the full frame"


def test_scheduler_feeds_regime_and_candidate_key_the_closed_frame():
    from app.services import scheduler

    src = inspect.getsource(scheduler._generate_signal)
    assert "analysis_window(df, timeframe)" in src
    assert "detect_regime(df_closed)" in src
    assert src.count("df=df_closed") == 3, "all three candidate writes"


def test_mtf_frames_close_on_their_own_timeframe():
    from app.engines.ai_decision import engine as orch

    src = inspect.getsource(orch.AIDecisionEngine.analyze_and_decide)
    assert "closed_candles(df_tf, tf)" in src, \
        "each MTF frame must use ITS OWN timeframe, not the primary's"
    assert "closed_candles(df_tf, timeframe)" not in src


def test_backtest_branch_is_untouched():
    """D3 — backtest is a separate checkpoint."""
    from app.backtesting import engine as bt

    assert "closed_candles" not in inspect.getsource(bt)
    assert "analysis_window" not in inspect.getsource(bt)


# ── 24-26 · price separation ───────────────────────────────────────────────
def test_current_price_comes_from_the_full_frame():
    from app.engines.ai_decision import engine as orch

    live = inspect.getsource(orch._live_price)
    assert 'df["close"].iloc[-1]' in live
    call = inspect.getsource(orch.AIDecisionEngine.analyze_and_decide)
    assert "current_price=_live_price(ohlcv_data)" in call, \
        "the live price must read the FULL frame, not the closed one"
    assert "_live_price(analysis_df)" not in call


def test_generator_anchors_levels_on_current_price_and_atr_on_closed():
    from app.engines.ai_decision import signal_generator as sg

    src = inspect.getsource(sg.generate_signal)
    assert "current_price = float(current_price) if current_price is not None" in src
    assert "atr_series = calculate_atr(df)" in src, "ATR from the closed frame (D2)"
    # Levels still anchored on current_price — coefficients untouched.
    for level in ("tp1 = current_price + (atr * 1.5)", "tp2 = current_price + (atr * 3.0)",
                  "tp3 = current_price + (atr * 5.0)"):
        assert level in src
    assert "current_price = float(df[\"close\"].iloc[-1])" not in src


def test_generator_still_works_when_called_without_current_price():
    """Direct callers that predate F1 must not break."""
    from app.engines.ai_decision import signal_generator as sg

    sig = inspect.signature(sg.generate_signal)
    assert sig.parameters["current_price"].default is None


# ── 27-30 · idempotency and provenance ─────────────────────────────────────
def test_evaluated_bar_time_is_the_last_closed_analysis_bar():
    from app.services import candidate_log

    tf = "15m"
    dur = TIMEFRAME_DURATIONS[tf]
    start = datetime(2026, 7, 28, 0, 0, tzinfo=UTC)
    df = _frame(start, 5, tf)
    now = start + 4 * dur + timedelta(minutes=2)
    closed = analysis_window(df, tf, now=now).df

    assert candidate_log._bar_time(closed) == start + 3 * dur
    assert candidate_log._bar_time(df) == start + 4 * dur, "the full frame keys on the forming bar"


def test_same_closed_bar_keys_identically_though_price_moved():
    """A retry mid-candle sees a different live price but the same analysis bar,
    so it must land on the same idempotency key."""
    from app.services import candidate_log

    tf = "15m"
    dur = TIMEFRAME_DURATIONS[tf]
    start = datetime(2026, 7, 28, 0, 0, tzinfo=UTC)
    df = _frame(start, 5, tf)

    first = analysis_window(df, tf, now=start + 4 * dur + timedelta(minutes=2)).df
    moved = df.copy()
    moved.loc[moved.index[-1], "close"] = 999.0        # price moved, bar did not close
    second = analysis_window(moved, tf, now=start + 4 * dur + timedelta(minutes=13)).df

    assert candidate_log._bar_time(first) == candidate_log._bar_time(second)


def test_new_closed_bar_produces_a_new_key():
    from app.services import candidate_log

    tf = "15m"
    dur = TIMEFRAME_DURATIONS[tf]
    start = datetime(2026, 7, 28, 0, 0, tzinfo=UTC)
    df = _frame(start, 6, tf)

    a = analysis_window(df, tf, now=start + 4 * dur + timedelta(minutes=2)).df
    b = analysis_window(df, tf, now=start + 5 * dur + timedelta(minutes=2)).df
    assert candidate_log._bar_time(b) - candidate_log._bar_time(a) == dur


def test_candidate_extra_carries_the_version_and_price_split():
    from app.services import candidate_log

    src = inspect.getsource(candidate_log.build_candidate_values)
    for field in ("decision_input_version", "candle_policy", "current_price",
                  "decision_current_price_source", "analysis_close_price",
                  "last_analysis_bar_open_time", "last_analysis_bar_close_time",
                  "last_analysis_bar_closed", "current_vs_analysis_close_pct",
                  "current_vs_analysis_close_atr"):
        assert field in src, f"{field} missing from candidate extra"

    from app.engines.ai_decision.signal_generator import CANDLE_POLICY, DECISION_INPUT_VERSION
    assert DECISION_INPUT_VERSION == "closed_candle_v1"
    assert CANDLE_POLICY == "closed_features_live_geometry"


def test_atr_normalised_gap_is_null_rather_than_fabricated():
    from app.engines.ai_decision import signal_generator as sg

    src = inspect.getsource(sg.generate_signal)
    assert "if (atr_raw and atr_raw > 0) else None" in src, \
        "a missing ATR must leave the ratio NULL, not divide by the fallback"


# ── 31 · nothing about the decision changed ────────────────────────────────
def test_thresholds_weights_and_branches_are_unchanged():
    from app.engines.ai_decision import signal_generator as sg
    from app.services import scheduler

    src = inspect.getsource(sg.generate_signal)
    for band in ("composite_score >= 68.0", "composite_score >= 54.0",
                 "composite_score >= 46.0", "composite_score >= 32.0"):
        assert band in src
    assert "min(bullish_count, bearish_count) * 4.0" in src
    assert sg.BASE_ENGINE_WEIGHTS == {
        "technical_analysis": 0.17, "market_structure": 0.17,
        "smart_money_concepts": 0.13, "volume_analysis": 0.13,
        "candle_range_theory": 0.10, "onchain_analysis": 0.10,
        "risk_management": 0.08, "fundamental_analysis": 0.07,
        "macro_analysis": 0.05,
    }
    sch = inspect.getsource(scheduler._generate_signal)
    assert "MIN_ACTIONABLE_CONFIDENCE = 65.0" in sch
    assert "REVERSAL_MIN_CONFIDENCE = 72.0" in sch
    assert sch.count("await record_candidate(") == 3
