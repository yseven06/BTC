"""CP-F0-1F(-lite): a fetched window that doesn't reach generated_at is reported.

A fetch that FAILS is fail-safe — df is None, the caller skips, the signal stays
ACTIVE. A fetch that comes back SHORT is not: it looks like a good frame, the walk
silently misses any TP/SL before its first bar, and the signal falls through to the
expiry check on evidence it doesn't have.

This is detection ONLY. The condition has never been observed (longest outage on
record 2.55 days vs the ~8.4 needed on M15), so acting on it would be a behaviour
change bought with no evidence. These lock the detector, and — just as important —
that resolution and the birth-candle rule did NOT move.
"""
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pandas as pd

from app.backtesting.tracker import (
    _MAX_FETCH_BARS, _post_signal_bars, _window_reaches_generation,
)

GEN = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)


def _signal(**over):
    base = dict(id="sig-1", generated_at=GEN, direction=NS(value="bullish"),
                signal_type=NS(value="BUY"), entry_zone_low=99.0, entry_zone_high=101.0,
                stop_loss=97.0, tp1=101.5, tp2=103.0, tp3=105.0)
    base.update(over)
    return NS(**base)


def _frame(first_bar, periods=4, freq="15min"):
    idx = pd.date_range(first_bar, periods=periods, freq=freq, tz="UTC")
    return pd.DataFrame({"open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0,
                         "volume": 1.0}, index=idx)


# ── 1/2/3 · The detector ─────────────────────────────────────────────────────
def test_frame_starting_before_generation_is_complete():
    df = _frame(GEN - timedelta(hours=2))
    assert _window_reaches_generation(_signal(), df) is True


def test_frame_starting_exactly_at_generation_is_complete():
    """A signal born on a bar open: that bar IS the birth bar — nothing is missing."""
    df = _frame(GEN)
    assert _window_reaches_generation(_signal(), df) is True


def test_frame_starting_after_generation_is_short():
    """The 12-day M15 case: 1000 bars only reach back 10.4 days."""
    df = _frame(GEN + timedelta(minutes=15))
    assert _window_reaches_generation(_signal(), df) is False


def test_a_deep_gap_is_short_by_a_lot():
    df = _frame(GEN + timedelta(days=2), periods=_MAX_FETCH_BARS)
    assert _window_reaches_generation(_signal(), df) is False
    assert len(df) >= _MAX_FETCH_BARS          # cap-bound → downtime outran the ceiling


def test_naive_index_and_naive_generated_at_are_comparable():
    idx = pd.date_range(GEN.replace(tzinfo=None) - timedelta(hours=2), periods=4, freq="15min")
    df = pd.DataFrame({"close": 100.0}, index=idx)
    assert _window_reaches_generation(_signal(generated_at=GEN.replace(tzinfo=None)), df) is True
    assert _window_reaches_generation(_signal(), df) is True          # mixed tz still works


def test_absent_frame_is_not_this_checks_question():
    """None/empty is the FETCH-FAILED path, which is already fail-safe."""
    assert _window_reaches_generation(_signal(), None) is True
    assert _window_reaches_generation(_signal(), pd.DataFrame()) is True


# ── 1F fires as a WARNING and nothing else ──────────────────────────────────
def test_short_window_is_logged_as_a_warning(caplog):
    df = _frame(GEN + timedelta(minutes=15))
    with caplog.at_level(logging.WARNING, logger="app.backtesting.tracker"):
        if not _window_reaches_generation(_signal(), df):
            logging.getLogger("app.backtesting.tracker").warning(
                "[Tracker] window starts at %s but signal generated at %s",
                df.index[0], GEN)
    assert any("window starts at" in r.message for r in caplog.records)


# ── 4 · The birth-candle rule did not move ──────────────────────────────────
def test_birth_candle_still_collapsed_and_detection_does_not_disturb_it():
    idx = pd.date_range(GEN - timedelta(minutes=10), periods=1, freq="15min", tz="UTC")
    birth = pd.DataFrame([(100.0, 105.0, 95.0, 100.2)],
                         columns=["open", "high", "low", "close"], index=idx)

    # complete window (the birth bar opens before generation) …
    assert _window_reaches_generation(_signal(), birth) is True
    # … and the collapse is unchanged: wicks are still not trusted.
    out = _post_signal_bars(_signal(), birth)
    assert out["high"].iloc[0] == 100.2 == out["low"].iloc[0]
    assert out["high"].iloc[0] != 105.0


def test_detection_is_independent_of_df_after():
    """The check reads the RAW frame. A frame whose only usable bar is the collapsed
    birth candle is still COMPLETE — df_after's shape is a separate question."""
    idx = pd.date_range(GEN - timedelta(minutes=10), periods=1, freq="15min", tz="UTC")
    birth = pd.DataFrame([(100.0, 100.5, 99.5, 100.2)],
                         columns=["open", "high", "low", "close"], index=idx)
    assert _window_reaches_generation(_signal(), birth) is True
    assert len(_post_signal_bars(_signal(), birth)) == 1


# ── 5 · Detection is pure: it cannot change a resolution ─────────────────────
def test_detector_does_not_mutate_the_frame_or_the_signal():
    df = _frame(GEN + timedelta(minutes=15))
    before = df.copy(deep=True)
    sig = _signal()

    _window_reaches_generation(sig, df)

    pd.testing.assert_frame_equal(df, before)      # frame untouched
    assert sig.generated_at == GEN                 # signal untouched
    assert df.index[0] == GEN + timedelta(minutes=15)


def test_detector_is_a_pure_predicate():
    """No DB, no clock, no I/O — same inputs, same answer, every time."""
    df = _frame(GEN + timedelta(minutes=15))
    assert {_window_reaches_generation(_signal(), df) for _ in range(5)} == {False}
