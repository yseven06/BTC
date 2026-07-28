"""F1-C — MTF, adaptive-weight and confidence-gate parity between backtest and live.

THE ORDERING THAT MATTERS
-------------------------
The confidence gate could not be added on its own. `confidence_score` is
`avg_conf - disagreement_penalty*1.5 - mtf_penalty`, and with `mtf_trends = {}`
that third term was structurally 0.0 — so every backtest confidence came out
exactly 15.0 higher per disagreeing frame than production's. Gating THAT number
against 65.0 would have admitted precisely the calls production rejects. MTF had
to be exact first; the gate is exact only because of it.

WHAT AS-OF MEANS HERE
---------------------
Selection is by CLOSE time. The orchestrator's own backtest slice compares OPEN
times (`mtf_df.index <= current_time`), which admits a 4h bar that opened at
08:00 and closes at 11:59:59 to a 15m decision made at 08:15. Frames are
pre-filtered so that bar is already gone and the second slice cannot restore it.

WHAT IS DELIBERATELY NOT DONE
-----------------------------
Adaptive weights stay at the static base. The adaptive layer's OUTPUT is stored
per candidate, so it is measurable — but the state IN FORCE at a past bar needs an
as-of CoinMemory rebuild that has no cutoff parameter and whose existing rebuild
overwrites the live row. Applying today's learned weights to old bars would be
look-ahead wearing a parity label.
"""
import inspect
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.backtesting.engine import (
    ADAPTIVE_WEIGHTS_PARITY,
    ADAPTIVE_WEIGHTS_POLICY,
    CONFIDENCE_GATE_POLICY,
    CONFIDENCE_SCORE_PARITY,
    MIN_ACTIONABLE_CONFIDENCE,
    MTF_ALIGNMENT_POLICY,
    MTF_DATA_SOURCE,
    MTF_PARITY,
    PARITY_LIMITATIONS,
    REVERSAL_GATE_POLICY,
    BacktestEngine,
    BacktestReport,
)
from app.backtesting.mtf_window import (
    MTF_BAR_LIMIT,
    MTF_TIMEFRAMES,
    as_of_frame,
    build_mtf_data,
)
from app.services.candle_window import CLOSE_TIME_COLUMN, TIMEFRAME_DURATIONS

UTC = timezone.utc


def _frame(start, n, timeframe, *, tz="UTC", with_close_time=True, drift=0.0):
    dur = TIMEFRAME_DURATIONS[timeframe]
    opens = [start + i * dur for i in range(n)]
    idx = pd.DatetimeIndex(opens)
    if tz is None:
        idx = idx.tz_localize(None)
    df = pd.DataFrame({
        "open":  [100.0 + i * drift for i in range(n)],
        "high":  [101.0 + i * drift for i in range(n)],
        "low":   [ 99.0 + i * drift for i in range(n)],
        "close": [100.0 + i * drift for i in range(n)],
        "volume": [1000.0] * n,
    }, index=idx)
    if with_close_time:
        df[CLOSE_TIME_COLUMN] = [o + dur - timedelta(milliseconds=1) for o in opens]
    return df


BASE = datetime(2026, 7, 20, 0, 0, tzinfo=UTC)


def _identifiers(module) -> set:
    """Every name the module's CODE references, parsed rather than grepped.

    A text search would match the comments that explain why something is absent —
    this file says "CoinMemory" and "mtf_penalty" repeatedly precisely because it
    is asserting they are NOT used.
    """
    import ast
    import textwrap

    # dedent so a method's source (indented inside its class) still parses.
    tree = ast.parse(textwrap.dedent(inspect.getsource(module)))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.alias):
            names.add(node.name.split(".")[-1])
            if node.asname:
                names.add(node.asname)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.update(node.module.split("."))
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
    return names


# ── 1-6 · as-of selection: no bar closing after the decision may be seen ────
@pytest.mark.parametrize("tf,expected_open", [
    ("1h", datetime(2026, 7, 20, 7, 0, tzinfo=UTC)),
    ("4h", datetime(2026, 7, 20, 4, 0, tzinfo=UTC)),
])
def test_1_2_forming_higher_timeframe_bar_is_invisible(tf, expected_open):
    """The exact case the open-time slice gets wrong: a 15m decision at 08:15
    must see the 1h bar that closed at 07:59:59, not the one closing at 08:59:59,
    and the 4h bar that closed at 07:59:59, not the one closing at 11:59:59."""
    decision_time = datetime(2026, 7, 20, 8, 15, tzinfo=UTC)
    df = _frame(BASE, 40, tf)
    sel = as_of_frame(df, tf, decision_time)

    assert not sel.empty
    assert sel.index[-1] == expected_open
    closes = pd.to_datetime(sel[CLOSE_TIME_COLUMN], utc=True)
    assert (closes <= decision_time).all(), "a bar closing after the decision leaked in"


@pytest.mark.parametrize("tf", list(MTF_TIMEFRAMES))
def test_3_4_last_closed_bar_is_the_one_selected(tf):
    dur = TIMEFRAME_DURATIONS[tf]
    df = _frame(BASE, 40, tf)
    # One millisecond after bar 9 closes.
    decision_time = BASE + 10 * dur
    sel = as_of_frame(df, tf, decision_time)
    assert sel.index[-1] == BASE + 9 * dur


@pytest.mark.parametrize("tf", list(MTF_TIMEFRAMES))
def test_5_boundary_at_the_exact_close_instant_is_deterministic(tf):
    dur = TIMEFRAME_DURATIONS[tf]
    df = _frame(BASE, 20, tf)
    close_of_5 = BASE + 6 * dur - timedelta(milliseconds=1)
    assert as_of_frame(df, tf, close_of_5).index[-1] == BASE + 5 * dur
    assert as_of_frame(df, tf, close_of_5 - timedelta(milliseconds=1)).index[-1] == BASE + 4 * dur


def test_6_future_bar_is_never_forward_filled():
    tf = "4h"
    df = _frame(BASE, 20, tf)
    decision_time = BASE - timedelta(hours=1)      # before ANY bar closed
    sel = as_of_frame(df, tf, decision_time)
    assert sel.empty, "nothing had closed — the frame must be empty, not back-filled"
    assert tf not in build_mtf_data({tf: df}, decision_time), \
        "an unknowable timeframe must be omitted, not given a fabricated bias"


# ── 7-11 · malformed input ─────────────────────────────────────────────────
def test_7_missing_frame_is_deterministic():
    dt = BASE + timedelta(days=1)
    assert build_mtf_data({}, dt) == {}
    assert build_mtf_data({"1h": None}, dt) == {}
    assert build_mtf_data({"1h": pd.DataFrame()}, dt) == {}


def test_8_utc_is_preserved_for_naive_and_aware_input():
    tf = "1h"
    aware = _frame(BASE, 20, tf, with_close_time=False)
    naive = aware.copy()
    naive.index = naive.index.tz_localize(None)
    dt = BASE + timedelta(hours=10)
    a, b = as_of_frame(aware, tf, dt), as_of_frame(naive, tf, dt)
    assert a.index.tz is not None and b.index.tz is not None
    assert list(a.index) == list(b.index)


def test_9_out_of_order_mtf_timestamps_are_sorted():
    tf = "1h"
    df = _frame(BASE, 12, tf).iloc[[5, 0, 9, 3, 1, 7, 2, 8, 4, 6, 11, 10]]
    sel = as_of_frame(df, tf, BASE + timedelta(hours=12))
    assert list(sel.index) == sorted(sel.index)
    assert len(sel) == 12


def test_10_duplicate_mtf_bars_resolve_to_the_last_copy():
    tf = "1h"
    df = _frame(BASE, 12, tf)
    dup = df.iloc[[4]].copy()
    dup["close"] = 555.0
    sel = as_of_frame(pd.concat([df, dup]), tf, BASE + timedelta(hours=12))
    assert len(sel) == 12
    assert float(sel["close"].iloc[4]) == 555.0


def test_11_frames_are_keyed_by_timeframe_and_never_mixed():
    dt = BASE + timedelta(days=2)
    frames = {tf: _frame(BASE, 60, tf, drift=1.0 + i) for i, tf in enumerate(MTF_TIMEFRAMES)}
    out = build_mtf_data(frames, dt)
    for tf in out:
        # Each frame's own bar spacing proves it was not swapped for another's.
        if len(out[tf]) >= 2:
            assert out[tf].index[1] - out[tf].index[0] == TIMEFRAME_DURATIONS[tf]


# ── 12-14 · production's own list, bias and penalty ────────────────────────
def test_12_timeframe_list_matches_production_verbatim():
    from app.engines.ai_decision import engine as orch
    from app.engines.ai_decision import signal_generator as sg

    assert MTF_TIMEFRAMES == ("15m", "1h", "4h")
    producer = inspect.getsource(orch.AIDecisionEngine.analyze_and_decide)
    assert 'fetch_tf_trend("15m")' in producer
    assert 'fetch_tf_trend("1h")' in producer
    assert 'fetch_tf_trend("4h")' in producer
    consumer = inspect.getsource(sg.generate_signal)
    assert '["15m", "1h", "4h"]' in consumer, \
        "the consumer ignores any other key silently — the lists must match"


def test_13_bias_uses_productions_own_function_not_a_copy():
    import app.backtesting.mtf_window as mw

    src = inspect.getsource(mw)
    assert "ewm" not in src and "def calculate_trend_bias" not in src, \
        "the bias formula must not be re-implemented here"
    # And the horizon matches production's limit=60, since the EMA seed depends on it.
    from app.engines.ai_decision import engine as orch
    assert "limit=60" in inspect.getsource(orch.AIDecisionEngine.analyze_and_decide)
    assert MTF_BAR_LIMIT == 60


def test_14_penalty_is_productions_and_is_not_duplicated():
    import app.backtesting.engine as bt
    from app.engines.ai_decision import signal_generator as sg

    assert "mtf_penalty" not in _identifiers(bt), \
        "the penalty must come from generate_signal, not a second implementation"
    gen = inspect.getsource(sg.generate_signal)
    assert "disagreeing_tf_count * 15.0" in gen
    assert "disagreeing_tf_count >= 2" in gen


def test_bar_horizon_is_clipped_to_production_limit():
    tf = "1h"
    df = _frame(BASE, 300, tf)
    sel = as_of_frame(df, tf, BASE + timedelta(hours=300))
    assert len(sel) == MTF_BAR_LIMIT, "a longer window changes the EMA and the bias"


# ── 15-20 · confidence gate ────────────────────────────────────────────────
def test_15_confidence_formula_is_productions_and_reaches_the_backtest():
    from app.engines.ai_decision import engine as orch
    from app.engines.ai_decision import signal_generator as sg
    import app.backtesting.engine as bt

    assert "max(20.0, min(98.0, avg_conf" in inspect.getsource(sg.generate_signal)
    assert '"confidence_score": signal_data.confidence_score' in \
        inspect.getsource(orch.AIDecisionEngine.analyze_and_decide)
    run = inspect.getsource(bt.BacktestEngine.run_backtest)
    assert 'decision.get("confidence_score")' in run
    assert "avg_conf" not in inspect.getsource(bt), "no second confidence formula"


def test_16_threshold_matches_production_and_cannot_drift():
    """The live value is a function-local inside _generate_signal, so it cannot be
    imported. It is duplicated — and this test is what keeps the copy honest."""
    from app.services import scheduler

    src = inspect.getsource(scheduler._generate_signal)
    assert f"MIN_ACTIONABLE_CONFIDENCE = {MIN_ACTIONABLE_CONFIDENCE}" in src, \
        "backtest threshold drifted from the scheduler's"
    assert MIN_ACTIONABLE_CONFIDENCE == 65.0


def test_17_18_gate_rejects_below_and_admits_above():
    src = inspect.getsource(BacktestEngine.run_backtest)
    assert "float(conf) < MIN_ACTIONABLE_CONFIDENCE" in src
    assert "rejected_by_confidence += 1" in src
    assert "actionable = False" in src
    # Above threshold, the trade still has to clear the remaining conditions.
    assert "if actionable:" in src and "trade_counter += 1" in src


def test_19_reversal_gate_is_marked_not_applicable_with_a_reason():
    from app.services import scheduler

    assert "REVERSAL_MIN_CONFIDENCE = 72.0" in inspect.getsource(scheduler._generate_signal)
    assert REVERSAL_GATE_POLICY == "not_applicable_single_position"
    # The backtest genuinely cannot reach that branch: it decides nothing while a
    # position is open, so an "active opposite signal" never exists.
    assert "if len(active_trades) == 0 and i < n - 1:" in \
        inspect.getsource(BacktestEngine.run_backtest)


def test_as_of_result_is_what_actually_reaches_the_orchestrator():
    """Calling build_mtf_data is not enough — its RESULT has to be the argument.
    Passing a literal `{}` alongside a live call would leave every string check
    satisfied while mtf_penalty silently returned to zero."""
    import ast
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(BacktestEngine.run_backtest)))
    passed = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg == "mtf_data":
                passed.append(kw.value)

    assert len(passed) == 1, f"expected exactly one mtf_data argument, got {len(passed)}"
    arg = passed[0]
    assert isinstance(arg, ast.Name) and arg.id == "mtf_data", \
        "mtf_data must be the variable built by build_mtf_data, not a literal"

    # And that variable must be assigned from build_mtf_data, once.
    assigns = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == "mtf_data" for t in n.targets)]
    assert len(assigns) == 1
    val = assigns[0].value
    assert isinstance(val, ast.Call) and isinstance(val.func, ast.Name) \
        and val.func.id == "build_mtf_data"


def test_20_gate_order_matches_production():
    """Production: engines -> MTF demotion -> actionable -> confidence.
    The backtest must apply the gate AFTER the decision, not before."""
    src = inspect.getsource(BacktestEngine.run_backtest)
    mtf_at = src.index("mtf_data = build_mtf_data")
    decide_at = src.index("decision = await self.decision_engine.analyze_and_decide")
    gate_at = src.index("float(conf) < MIN_ACTIONABLE_CONFIDENCE")
    trade_at = src.index("trade_counter += 1")
    assert mtf_at < decide_at < gate_at < trade_at


# ── 21-23 · weights ────────────────────────────────────────────────────────
def test_21_22_base_weights_are_normalised():
    from app.engines.ai_decision.signal_generator import BASE_ENGINE_WEIGHTS
    from app.services.coin_memory import get_effective_weights

    assert abs(sum(BASE_ENGINE_WEIGHTS.values()) - 1.0) < 1e-9
    eff = get_effective_weights(None, None)          # no regime, no memory
    assert abs(sum(eff.values()) - 1.0) < 1e-6
    assert len(eff) == len(BASE_ENGINE_WEIGHTS)


def test_23_current_coin_memory_is_never_applied_to_past_bars():
    import app.backtesting.engine as bt

    names = _identifiers(bt)
    for banned in ("CoinMemory", "load_effective_weights", "load_effective_weights_meta",
                   "get_effective_weights", "coin_memory"):
        assert banned not in names, \
            f"{banned} in the backtest would apply today's learned state to old bars"
    assert "engine_weights" not in _identifiers(bt.BacktestEngine.run_backtest)
    assert ADAPTIVE_WEIGHTS_PARITY == "not_applied"
    assert ADAPTIVE_WEIGHTS_POLICY == "static_base_weights"


# ── 24-25, 30 · reporting ──────────────────────────────────────────────────
def test_24_25_gate_effects_are_reported():
    fields = BacktestReport.__dataclass_fields__
    for f in ("confidence_distribution", "candidates_rejected_by_confidence",
              "candidates_holded_by_mtf", "mtf_frames_available"):
        assert f in fields

    from app.backtesting.engine import _confidence_summary
    s = _confidence_summary([50.0, 60.0, 65.0, 70.0, 80.0])
    assert s["n"] == 5 and s["median"] == 65.0
    assert s["pct_at_or_above_threshold"] == 60.0
    assert _confidence_summary([]) == {}


def test_30_and_metadata_legacy_fields_survive():
    from app.schemas.signal import BacktestResponse

    for f in ("mtf_parity", "mtf_alignment_policy", "mtf_data_source",
              "adaptive_weights_parity", "adaptive_weights_policy",
              "confidence_score_parity", "confidence_gate_policy",
              "confidence_threshold", "reversal_gate_policy",
              "overall_decision_parity", "parity_limitations",
              "candidates_rejected_by_confidence", "confidence_distribution"):
        assert f in BacktestResponse.model_fields, f"{f} not exposed on the API"

    for f in ("total_trades", "wins", "losses", "win_rate", "profit_factor",
              "equity_curve", "trades_log"):
        assert f in BacktestResponse.model_fields

    assert MTF_PARITY == "exact"
    assert MTF_ALIGNMENT_POLICY == "as_of_close_time_per_timeframe"
    assert MTF_DATA_SOURCE == "binance_klines_historical"
    assert CONFIDENCE_SCORE_PARITY == "exact"
    assert CONFIDENCE_GATE_POLICY == "min_actionable_confidence"
    assert len(PARITY_LIMITATIONS) >= 3, \
        "the remaining gaps must stay stated, not quietly dropped"
    assert any("intrabar" in x for x in PARITY_LIMITATIONS)
    assert any("weights" in x for x in PARITY_LIMITATIONS)


# ── 26-29 · nothing else moved ─────────────────────────────────────────────
def test_26_f1b_closed_boundary_still_holds():
    src = inspect.getsource(BacktestEngine.run_backtest)
    assert "df = closed_candles(df, timeframe)" in src
    assert "sub_df = df.iloc[:i + 1]" in src
    assert "entry_index=i + 1" in src


def test_27_unknown_timeframe_still_rejected():
    from app.schemas.signal import BacktestRequest

    with pytest.raises(Exception):
        BacktestRequest(symbol="BTCUSDT", timeframe="30m")
    assert BacktestRequest(symbol="BTCUSDT", timeframe="4h").timeframe == "4h"
    assert "except UnknownTimeframeError:" in inspect.getsource(BacktestEngine.run_backtest)


def test_28_production_decision_modules_are_untouched():
    from app.collectors import binance_collector
    from app.engines.ai_decision import engine as orch
    from app.engines.ai_decision import signal_generator as sg
    from app.services import candidate_log, scheduler

    for mod in (sg, scheduler, candidate_log, binance_collector, orch):
        src = inspect.getsource(mod)
        assert "build_mtf_data" not in src, "backtest helper leaked into production"
        assert "app.backtesting" not in src or mod is scheduler  # scheduler imports labels/tracker

    gen = inspect.getsource(sg.generate_signal)
    for band in ("composite_score >= 68.0", "composite_score >= 54.0",
                 "composite_score >= 46.0", "composite_score >= 32.0"):
        assert band in gen
    assert "min(bullish_count, bearish_count) * 4.0" in gen
    sch = inspect.getsource(scheduler._generate_signal)
    assert "MIN_ACTIONABLE_CONFIDENCE = 65.0" in sch
    assert "REVERSAL_MIN_CONFIDENCE = 72.0" in sch
    assert "analysis_window(df, timeframe)" in sch
    # The orchestrator's own MTF branches are as they were.
    osrc = inspect.getsource(orch.AIDecisionEngine.analyze_and_decide)
    assert "mtf_df[mtf_df.index <= current_time]" in osrc
    assert "closed_candles(df_tf, tf)" in osrc


def test_mtf_helper_is_pure():
    import app.backtesting.mtf_window as mw

    src = inspect.getsource(mw)
    for banned in ("async def", "await", "httpx", "requests", "session",
                   "BinanceCollector", "app.database"):
        assert banned not in src, f"the as-of helper must stay pure, found {banned}"
