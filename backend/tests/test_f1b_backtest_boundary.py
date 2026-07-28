"""F1-B' — backtest boundary and timeframe safety.

WHAT THIS IS NOT FIXING
-----------------------
The look-ahead hypothesis that commissioned this work was refuted. The decision
side was already correct and these tests pin it so, rather than "fixing" it:

    features    bars 0..i    — bar i is closed when it is scored
    price       close[i]     — the no-lookahead proxy for production's live price
    execution   bar i+1 on   — the trade's first resolution bar

The bar that produces a signal never resolves that signal: the trade is appended
at the END of the loop iteration while resolution runs at the TOP of the next.

WHAT IT IS FIXING
-----------------
R1  An unsupported timeframe failed twice invisibly — the collector silently
    substituted 1h data, and after F1 the closed-candle helper raised inside the
    backtest's broad except, so the run finished with zero trades and HTTP 200.
    Both read as "the strategy found no setups".

R2  The far end of the dataset was unbounded. The backtest fetches live, so the
    final row is normally the candle still forming; the `i < n - 1` guard kept it
    out of the FEATURES but nothing kept it out of EXECUTION — a decision at
    i = n-2 sets entry_index = n-1, opening a trade on a partial bar and
    resolving it against an incomplete high/low. Not feature look-ahead;
    executing against a bar that has not finished happening.

R3  Deliberately NOT changed: the price proxy stays close[i]. Measured on 24k
    bar pairs, open[i+1] differs by a median 0.02 %. Recorded in metadata.
"""
import inspect
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.backtesting.engine import (
    BACKTEST_INPUT_VERSION,
    DECISION_PRICE_POLICY,
    EXECUTION_START_POLICY,
    FEATURE_CUTOFF_POLICY,
    MTF_PARITY,
    PRODUCTION_INTRABAR_PARITY,
    BacktestEngine,
    BacktestReport,
)
from app.services.candle_window import (
    CLOSE_TIME_COLUMN,
    TIMEFRAME_DURATIONS,
    UnknownTimeframeError,
    closed_candles,
)

UTC = timezone.utc


def _frame(start, n, timeframe, *, with_close_time=True, tz="UTC"):
    dur = TIMEFRAME_DURATIONS[timeframe]
    opens = [start + i * dur for i in range(n)]
    idx = pd.DatetimeIndex(opens)
    if tz is None:
        idx = idx.tz_localize(None)
    df = pd.DataFrame({
        "open":  [100.0 + i * 0.1 for i in range(n)],
        "high":  [100.5 + i * 0.1 for i in range(n)],
        "low":   [ 99.5 + i * 0.1 for i in range(n)],
        "close": [100.2 + i * 0.1 for i in range(n)],
        "volume": [1000.0] * n,
    }, index=idx)
    if with_close_time:
        df[CLOSE_TIME_COLUMN] = [o + dur - timedelta(milliseconds=1) for o in opens]
    return df


def _live_frame(timeframe, n):
    """A frame whose final bar is the one currently forming — what the backtest
    endpoint actually receives, since it fetches live."""
    dur = TIMEFRAME_DURATIONS[timeframe]
    now = datetime.now(UTC)
    secs = int(dur.total_seconds())
    epoch = int(now.timestamp())
    current_open = datetime.fromtimestamp(epoch - (epoch % secs), UTC)
    return _frame(current_open - (n - 1) * dur, n, timeframe)


# ── 1-4 · the decision timing that was ALREADY correct ─────────────────────
def test_1_decision_bar_is_closed_and_2_is_in_the_feature_frame():
    src = inspect.getsource(BacktestEngine.run_backtest)
    assert "sub_df = df.iloc[:i + 1]" in src, \
        "bar i must stay IN the feature frame — it is closed when it is scored"
    assert "df.iloc[:i]" not in src, "removing bar i would be a new off-by-one"


def test_3_entry_bar_is_the_one_after_the_decision_bar():
    src = inspect.getsource(BacktestEngine.run_backtest)
    assert "entry_index=i + 1" in src
    assert "entry_time=timestamps[i + 1]" in src
    assert "entry_index=i + 2" not in src


def test_4_decision_bar_never_resolves_its_own_trade():
    """The ordering is the guarantee: resolution runs at the TOP of the loop,
    the new trade is appended at the BOTTOM."""
    src = inspect.getsource(BacktestEngine.run_backtest)
    resolve_at = src.index("apply_backtest_bar(trade, trade.age - 1")
    append_at = src.index("active_trades.append(new_trade)")
    assert resolve_at < append_at, \
        "a trade appended before the resolution block would be resolved by its own decision bar"
    # And the first resolution index is 0 == the bar after entry.
    assert "trade.age += 1" in src and "trade.age - 1" in src


# ── 5-9 · R2: the forming bar is out of the dataset entirely ───────────────
@pytest.mark.parametrize("tf", ["15m", "1h", "4h"])
def test_5_6_7_forming_final_bar_leaves_the_dataset(tf):
    df = _live_frame(tf, 80)
    cut = closed_candles(df, tf)
    assert len(cut) == len(df) - 1, f"{tf}: the forming bar must be dropped"
    assert cut.index[-1] < df.index[-1]
    # Being out of the dataset means it cannot be a feature bar, an entry bar or
    # an outcome bar — all three are indexed off this one frame.
    src = inspect.getsource(BacktestEngine.run_backtest)
    assert "df = closed_candles(df, timeframe)" in src
    assert src.index("closed_candles(df, timeframe)") < src.index("n = len(df)"), \
        "the cut must happen before the walk is sized"


def test_8_no_trade_opens_when_no_entry_bar_follows():
    src = inspect.getsource(BacktestEngine.run_backtest)
    assert "if len(active_trades) == 0 and i < n - 1:" in src, \
        "the last closed bar may decide, but only if a following bar exists to enter on"


def test_9_fully_closed_dataset_is_unchanged():
    """Historical backtests must behave exactly as before — the cut is a no-op
    when nothing is still forming."""
    tf = "1h"
    df = _frame(datetime(2026, 1, 1, tzinfo=UTC), 120, tf)
    cut = closed_candles(df, tf)
    assert len(cut) == len(df)
    pd.testing.assert_frame_equal(cut[["open", "high", "low", "close", "volume"]],
                                  df[["open", "high", "low", "close", "volume"]])


# ── 10-14 · malformed input ────────────────────────────────────────────────
def test_10_out_of_order_timestamps_are_sorted():
    tf = "1h"
    df = _frame(datetime(2026, 1, 1, tzinfo=UTC), 10, tf).iloc[[5, 0, 9, 3, 1, 7, 2, 8, 4, 6]]
    cut = closed_candles(df, tf)
    assert list(cut.index) == sorted(cut.index)
    assert len(cut) == 10


def test_11_duplicate_timestamps_resolve_deterministically():
    tf = "1h"
    df = _frame(datetime(2026, 1, 1, tzinfo=UTC), 10, tf)
    dup = df.iloc[[4]].copy()
    dup["close"] = 777.0
    df = pd.concat([df, dup])
    cut = closed_candles(df, tf)
    assert len(cut) == 10
    assert float(cut["close"].iloc[4]) == 777.0, "the last copy must win, every time"


def test_12_naive_and_aware_indexes_both_normalise_to_utc():
    tf = "1h"
    aware = _frame(datetime(2026, 1, 1, tzinfo=UTC), 10, tf, with_close_time=False)
    naive = aware.copy()
    naive.index = naive.index.tz_localize(None)
    a, b = closed_candles(aware, tf), closed_candles(naive, tf)
    assert a.index.tz is not None and b.index.tz is not None
    assert list(a.index) == list(b.index)


def test_13_gaps_do_not_create_look_ahead():
    tf = "1h"
    dur = TIMEFRAME_DURATIONS[tf]
    start = datetime(2026, 1, 1, tzinfo=UTC)
    df = _frame(start, 12, tf).drop(index=[start + 4 * dur, start + 5 * dur])
    cut = closed_candles(df, tf)
    assert len(cut) == 10
    assert list(cut.index) == sorted(cut.index)
    assert cut.index[-1] == start + 11 * dur, "a gap must not shift the far boundary"


def test_14_min_bars_and_long_windows_keep_their_margin():
    """min_bars=60 is what lets EMA/SMA windows compute; the cut removes at most
    one trailing bar, so it cannot silently eat that margin."""
    src = inspect.getsource(BacktestEngine.run_backtest)
    assert "min_bars = 60" in src
    assert "n < min_bars + 10" in src
    df = _live_frame("1h", 71)
    assert len(closed_candles(df, "1h")) == 70, "exactly one trailing bar, never more"


# ── 15 · symmetry ──────────────────────────────────────────────────────────
def test_15_long_and_short_paths_are_symmetric():
    src = inspect.getsource(BacktestEngine.run_backtest)
    assert 'sig_type in ["STRONG_BUY", "BUY", "SELL", "STRONG_SELL"]' in src, \
        "both directions enter through one branch — no asymmetric handling"
    # Entry/levels come from the decision for both directions alike.
    assert 'entry_mid = (float(decision["entry_zone_low"]) + float(decision["entry_zone_high"])) / 2.0' in src


# ── 16-20 · R1: timeframe safety ───────────────────────────────────────────
def test_16_17_unsupported_timeframe_raises_instead_of_returning_nothing():
    df = _frame(datetime(2026, 1, 1, tzinfo=UTC), 100, "1h")
    with pytest.raises(UnknownTimeframeError):
        closed_candles(df, "30m")

    src = inspect.getsource(BacktestEngine.run_backtest)
    # The cut runs before the walk, so an unsupported timeframe fails immediately
    # rather than once per bar inside a swallowing except.
    assert src.index("closed_candles(df, timeframe)") < src.index("for i in range(min_bars, n)")


def test_18_every_supported_timeframe_actually_works():
    for tf in ("1m", "5m", "15m", "1h", "4h", "1d", "1w"):
        dur = TIMEFRAME_DURATIONS[tf]
        # Anchor per timeframe so the final bar is definitively closed: a fixed
        # calendar start would put 30 weekly bars into the future and the helper
        # would rightly drop the last one.
        df = _frame(datetime.now(UTC) - 31 * dur, 30, tf)
        assert len(closed_candles(df, tf)) == 30, f"{tf} must be supported"


def test_19_no_silent_fallback_to_1h():
    from app.schemas.signal import BacktestRequest

    src = inspect.getsource(BacktestEngine.run_backtest)
    assert '_TF_HOURS.get(timeframe, 1.0)' in src, "max-age table keeps its own default"
    # But the request can no longer deliver an unsupported value to it.
    with pytest.raises(Exception):
        BacktestRequest(symbol="BTCUSDT", timeframe="30m")
    with pytest.raises(Exception):
        BacktestRequest(symbol="BTCUSDT", timeframe="nonsense")
    assert BacktestRequest(symbol="BTCUSDT", timeframe="4h").timeframe == "4h"
    assert BacktestRequest(symbol="BTCUSDT").timeframe == "1h"


def test_20_broad_except_does_not_swallow_unknown_timeframe():
    src = inspect.getsource(BacktestEngine.run_backtest)
    assert "except UnknownTimeframeError:" in src
    assert src.index("except UnknownTimeframeError:") < src.index("except Exception as e:"), \
        "the narrow handler must come first or the broad one wins"
    handler = src[src.index("except UnknownTimeframeError:"):src.index("except Exception as e:")]
    assert "raise" in handler and "logger.debug" not in handler


# ── 21-22 · R3: the price proxy is unchanged, and stays no-lookahead ───────
def test_21_current_price_still_comes_from_the_decision_bar_close():
    from app.engines.ai_decision import engine as orch

    assert 'df["close"].iloc[-1]' in inspect.getsource(orch._live_price)
    src = inspect.getsource(BacktestEngine.run_backtest)
    assert "current_price = closes[i]" in src
    assert "current_price = opens[i + 1]" not in src, \
        "F1-B' deliberately does NOT switch to the next bar's open"
    assert DECISION_PRICE_POLICY == "previous_closed_bar_close_proxy"


def test_22_no_bar_after_the_decision_bar_reaches_the_features():
    src = inspect.getsource(BacktestEngine.run_backtest)
    decision = src[src.index("sub_df = df.iloc[:i + 1]"):src.index("active_trades.append(new_trade)")]
    for leak in ("opens[i + 1]", "highs[i + 1]", "lows[i + 1]", "closes[i + 1]"):
        assert leak not in decision, f"{leak} leaked into the decision block"


# ── 23 · metadata ──────────────────────────────────────────────────────────
def test_23_report_carries_every_policy_field():
    fields = BacktestReport.__dataclass_fields__
    for f in ("backtest_input_version", "feature_cutoff_policy", "execution_start_policy",
              "decision_price_policy", "production_intrabar_parity", "mtf_parity",
              "dropped_forming_bars"):
        assert f in fields, f"{f} missing from BacktestReport"

    assert BACKTEST_INPUT_VERSION == "closed_candle_v1"
    assert FEATURE_CUTOFF_POLICY == "through_previous_closed_decision_bar"
    assert EXECUTION_START_POLICY == "next_closed_bar"
    assert DECISION_PRICE_POLICY == "previous_closed_bar_close_proxy"
    assert PRODUCTION_INTRABAR_PARITY == "approximate"
    assert MTF_PARITY == "unavailable"

    from app.schemas.signal import BacktestResponse
    for f in ("backtest_input_version", "decision_price_policy", "mtf_parity",
              "dropped_forming_bars"):
        assert f in BacktestResponse.model_fields, f"{f} not exposed on the API response"

    src = inspect.getsource(BacktestEngine.run_backtest)
    assert "dropped_forming_bars=dropped_forming" in src


# ── 25 · production is untouched ───────────────────────────────────────────
def test_25_production_decision_path_is_unchanged():
    from app.engines.ai_decision import signal_generator as sg
    from app.services import candidate_log, scheduler
    from app.collectors import binance_collector

    # No backtest concept reached the live path.
    for mod in (sg, scheduler, candidate_log, binance_collector):
        src = inspect.getsource(mod)
        assert "BACKTEST_INPUT_VERSION" not in src
        assert "closed_candles(df, timeframe)" not in src or mod is not binance_collector

    # The live gates are exactly where F1 left them.
    gen = inspect.getsource(sg.generate_signal)
    for band in ("composite_score >= 68.0", "composite_score >= 54.0",
                 "composite_score >= 46.0", "composite_score >= 32.0"):
        assert band in gen
    sch = inspect.getsource(scheduler._generate_signal)
    assert "MIN_ACTIONABLE_CONFIDENCE = 65.0" in sch
    assert "REVERSAL_MIN_CONFIDENCE = 72.0" in sch
    assert "analysis_window(df, timeframe)" in sch
    assert "detect_regime(df_closed)" in sch
    # The collector still hands back the forming candle for the chart and tracker.
    coll = inspect.getsource(binance_collector.BinanceCollector.fetch_ohlcv)
    assert "iloc[:-1]" not in coll


def test_shared_helper_stays_side_effect_free():
    """The backtest now imports it, so an import-time side effect would run in a
    second context."""
    import app.services.candle_window as cw

    src = inspect.getsource(cw)
    for banned in ("async_session_factory", "BinanceCollector", "httpx",
                   "requests", "app.database", "app.collectors"):
        assert banned not in src, f"candle_window reached for {banned}"
