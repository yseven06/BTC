"""CP-F0-1H: the live-SL shortcut books against the bars, not a stale perf row.

The shortcut resolves before the bar-walk runs and read perf.hit_tp1, which is only
as fresh as the last pass. Across a gap (machine off) a trade that banked TP1 inside
the gap still reads False and gets booked as a FULL original-stop loss instead of
50% at TP1 plus the remainder at breakeven. CP-F0-1B widened the window so the walk
can see into the gap; these lock that the shortcut now uses what it sees.

Also locks the field-consistency fix and — importantly — that the birth-candle
policy is NOT what changed.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pandas as pd

from app.backtesting.tracker import (
    _live_ladder_walk, _post_signal_bars, live_sl_realized,
)

GEN = datetime(2026, 7, 16, 0, 0, tzinfo=timezone.utc)
ENTRY, TP1, TP2, TP3, SL = 100.0, 101.5, 103.0, 105.0, 97.0


def _signal(**over):
    base = dict(id="sig-1", generated_at=GEN, direction=NS(value="bullish"),
                signal_type=NS(value="BUY"), entry_zone_low=99.0, entry_zone_high=101.0,
                stop_loss=SL, tp1=TP1, tp2=TP2, tp3=TP3)
    base.update(over)
    return NS(**base)


def _flags(signal, df):
    """(hit_tp1, hit_tp2) from the walk — F0-1A widened _live_ladder_walk to
    return the whole result so hit_time can come off the same replay."""
    bw = _live_ladder_walk(signal, df)
    return None if bw is None else (bool(bw["hit_tp1"]), bool(bw["hit_tp2"]))


def _bars(rows, start_offset_min=15, freq="15min"):
    """rows = [(open, high, low, close), ...] starting AFTER generated_at."""
    idx = pd.date_range(GEN + timedelta(minutes=start_offset_min), periods=len(rows),
                        freq=freq, tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx).assign(
        volume=1.0)


# ── 1 · The bug: TP1 inside the gap, then the stop breaks ────────────────────
def test_tp1_banked_in_the_gap_is_recovered_from_the_bars():
    """The machine was off; perf never recorded the TP1 the bars plainly show."""
    df = _bars([
        (100.0, 102.0, 99.8, 101.8),   # TP1 (101.5) touched — banked, stop → breakeven
        (101.8, 101.9, 99.9, 100.0),   # drifts back to entry
        (100.0, 100.1, 96.0, 96.2),    # blows through the ORIGINAL stop
    ])
    flags = _flags(_signal(), df)
    assert flags == (True, False)              # the walk saw TP1; perf said False

    stale = live_sl_realized("bullish", ENTRY, SL, TP1, TP2, False, False)[0]
    fixed = live_sl_realized("bullish", ENTRY, SL, TP1, TP2, *flags)[0]

    assert stale == (SL - ENTRY) / ENTRY       # -3% : full size at the original stop
    assert fixed > 0                           # +0.75% : 50% at TP1, remainder at BE
    assert round(fixed, 6) == round(0.5 * (TP1 - ENTRY) / ENTRY, 6)


def test_tp2_is_recovered_too():
    df = _bars([
        (100.0, 103.5, 99.8, 103.2),   # TP1 and TP2 in one candle
        (103.2, 103.3, 96.0, 96.1),    # then collapses
    ])
    assert _flags(_signal(), df) == (True, True)


# ── 2/3 · The paths that must NOT move ──────────────────────────────────────
def test_no_tp1_still_books_the_full_original_stop_loss():
    """516 of the 776 live-SL rows are this shape — it must stay byte-identical."""
    df = _bars([
        (100.0, 100.4, 99.5, 99.8),
        (99.8, 99.9, 96.0, 96.1),      # straight to the stop, TP1 never touched
    ])
    flags = _flags(_signal(), df)
    assert flags == (False, False)
    assert live_sl_realized("bullish", ENTRY, SL, TP1, TP2, *flags)[0] == (SL - ENTRY) / ENTRY


def test_agreeing_flags_change_nothing():
    """260 live-SL rows already had hit_tp1=True stored — same answer either way."""
    df = _bars([(100.0, 102.0, 99.8, 101.8), (101.8, 101.9, 96.0, 96.1)])
    flags = _flags(_signal(), df)
    assert flags == (True, False)
    from_walk = live_sl_realized("bullish", ENTRY, SL, TP1, TP2, *flags)
    from_perf = live_sl_realized("bullish", ENTRY, SL, TP1, TP2, True, False)
    assert from_walk == from_perf


# ── 4 · Fallback: no bars → the stored flags, i.e. pre-CP behaviour ─────────
def test_returns_none_when_the_bars_cannot_answer():
    assert _flags(_signal(), None) is None
    assert _flags(_signal(), pd.DataFrame()) is None
    # levels missing → cannot walk
    assert _flags(_signal(tp1=None), _bars([(100.0, 102.0, 99.0, 101.8)])) is None
    assert _flags(_signal(entry_zone_low=None),
                              _bars([(100.0, 102.0, 99.0, 101.8)])) is None


def test_a_broken_frame_falls_back_instead_of_raising():
    """The probe must never take a resolution down with it."""
    bad = pd.DataFrame({"open": [1.0]}, index=[GEN + timedelta(minutes=15)])  # no high/low
    assert _flags(_signal(), bad) is None


# ── 5 · The walk still resolves on its own ──────────────────────────────────
def test_walk_resolves_the_same_gap_independently():
    """The shortcut isn't the only reader — the walk reaches the same conclusion."""
    from app.backtesting.resolution_core import resolve_trade_path
    res = resolve_trade_path(direction="bullish", entry=ENTRY, sl=SL, tp1=TP1, tp2=TP2,
                             tp3=TP3, bars=[(100.0, 102.0, 99.8, 101.8),
                                            (101.8, 101.9, 99.5, 100.0)])
    assert res.hit_tp1 is True
    assert res.resolved and res.resolved_by_sl      # breakeven stop, not the original
    assert res.realized_return_frac > 0


# ── 6 · Field consistency: no orphan timestamp ──────────────────────────────
def test_flag_and_timestamp_come_from_one_walk_result():
    """The 5 known bad rows are hit_tp1=False beside a populated tp1_hit_at.

    Both now come from the same _bw dict, so a pass that stops seeing TP1 clears
    the timestamp with the flag instead of leaving it behind.
    """
    from app.backtesting.tracker import _resolve_signal_bar_walk
    df = _bars([(100.0, 100.4, 99.5, 99.8), (99.8, 99.9, 99.0, 99.2)])   # no TP1
    bw = _resolve_signal_bar_walk(
        direction="bullish", entry=ENTRY, stop_loss=SL, tp1=TP1, tp2=TP2, tp3=TP3,
        opens=df["open"].values, highs=df["high"].values, lows=df["low"].values,
        closes=df["close"].values, times=df.index.tolist(),
        sig_time_aware=pd.Timestamp(GEN),
    )
    assert bw["hit_tp1"] is False and bw["tp1_hit_at"] is None   # they agree
    assert bw["hit_tp2"] is False and bw["tp2_hit_at"] is None


# ── 7 · The birth-candle policy is NOT what changed ─────────────────────────
def test_birth_candle_is_still_collapsed_to_its_close():
    """Deliberate, load-bearing rule: OHLCV has no intra-candle ordering, so the
    candle containing generated_at cannot prove its wick came after the signal.
    _post_signal_bars is a verbatim extraction — this locks that."""
    idx = pd.date_range(GEN - timedelta(minutes=10), periods=1, freq="15min", tz="UTC")
    birth = pd.DataFrame([(100.0, 105.0, 95.0, 100.2)],           # huge wicks both ways
                         columns=["open", "high", "low", "close"], index=idx)
    out = _post_signal_bars(_signal(), birth)

    assert len(out) == 1
    assert out["high"].iloc[0] == 100.2 == out["low"].iloc[0]     # collapsed to close
    assert out["high"].iloc[0] != 105.0                           # the wick is NOT trusted

    # …so a TP1 that only the birth wick touched is still not credited.
    assert _flags(_signal(), birth) == (False, False)


def test_birth_candle_drops_out_once_a_newer_bar_exists():
    """Unchanged behaviour: once it is no longer last, the strict `> sig_time`
    filter excludes it entirely. This is why the 5 historical rows exist, and this
    CP does not alter it."""
    idx = pd.DatetimeIndex([GEN - timedelta(minutes=10), GEN + timedelta(minutes=5)], tz="UTC")
    df = pd.DataFrame([(100.0, 105.0, 95.0, 100.2), (100.2, 100.3, 99.9, 100.0)],
                      columns=["open", "high", "low", "close"], index=idx)
    out = _post_signal_bars(_signal(), df)
    assert len(out) == 1                                  # birth candle gone
    assert out.index[0] == GEN + timedelta(minutes=5)
    assert out["high"].iloc[0] == 100.3                   # newer bar keeps its real wick


def test_post_signal_bars_keeps_completed_bars_intact():
    df = _bars([(100.0, 102.0, 99.0, 101.0), (101.0, 101.5, 100.0, 100.5)])
    out = _post_signal_bars(_signal(), df)
    pd.testing.assert_frame_equal(out, df)                # nothing collapsed
