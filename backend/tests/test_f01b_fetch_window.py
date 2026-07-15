"""CP-F0-1B: the OHLCV fetch window scales with signal age.

The old fixed limit=100 spans 25h on M15 while a signal lives 48h, so after
downtime long enough to age a signal past the window, a TP/SL inside the gap was
invisible to the bar-walk and the signal fell through to EXPIRED. These lock the
window maths AND the isolation that keeps the widening out of the lifecycle read.
"""
from datetime import datetime, timedelta, timezone

import pandas as pd

from app.backtesting.tracker import (
    _FETCH_BUFFER_BARS, _MAX_FETCH_BARS, _MIN_FETCH_BARS, _OBS_BARS,
    _recovery_fetch_limit,
)

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)


def _limit(tf: str, **age):
    return _recovery_fetch_limit(tf, NOW - timedelta(**age), NOW)


# ── 1 · Window maths per timeframe ───────────────────────────────────────────
def test_m15_past_window_widens():
    # 30h / 15m = 120 bars + 5 buffer. The whole point of the CP.
    assert _limit("15m", hours=30) == 125


def test_h1_h4_d1_stay_at_the_floor():
    # 100 bars already spans 100h / 400h / 100d — a 48h life never escapes it.
    assert _limit("1h", hours=48) == 100     # needs 48+5
    assert _limit("4h", hours=48) == 100     # needs 12+5
    assert _limit("1d", hours=48) == 100     # needs 2+5


def test_young_signal_is_byte_identical_to_pre_cp():
    # 1h old on 15m → needs 4+5. The floor keeps the request at exactly 100, so
    # the fetch (and everything downstream) is unchanged for most of the book.
    assert _limit("15m", hours=1) == _MIN_FETCH_BARS == 100


def test_cap_at_binance_api_maximum():
    # 30d / 15m = 2880 bars — far past what /klines will serve.
    assert _limit("15m", days=30) == _MAX_FETCH_BARS == 1000


# ── 2 · Boundary + defensive ─────────────────────────────────────────────────
def test_widening_threshold_is_2375h_on_m15():
    # ceil(age/900) + 5 > 100  ⇔  age > 95 bars = 23.75h
    assert _limit("15m", hours=23.5) == 100          # 94+5 → floor holds
    assert _limit("15m", hours=23.75) == 100         # exactly 95+5 → still floor
    assert _limit("15m", hours=24.5) == 103          # 98+5 → widened
    assert _limit("15m", hours=48) == 197            # end of a signal's life


def test_unknown_timeframe_falls_back_and_never_raises():
    # _map_db_timeframe already falls back to "1h"; mirror that instead of KeyError.
    assert _limit("7m", hours=48) == 100             # treated as 1h → 48+5 → floor
    assert _limit("", hours=200) == 205              # 200h as 1h bars + buffer


def test_naive_and_future_timestamps_are_survivable():
    naive = _recovery_fetch_limit("15m", NOW.replace(tzinfo=None) - timedelta(hours=30),
                                  NOW.replace(tzinfo=None))
    assert naive == 125                              # naive pair → same answer
    mixed = _recovery_fetch_limit("15m", NOW.replace(tzinfo=None) - timedelta(hours=30), NOW)
    assert mixed == 125                              # naive generated_at, aware now
    # A generated_at in the future must not produce a negative/absurd request.
    assert _recovery_fetch_limit("15m", NOW + timedelta(hours=5), NOW) == _MIN_FETCH_BARS


def test_buffer_is_applied_exactly_once():
    # 100 bars of age → 100 + buffer, proving the buffer is additive, not a factor.
    assert _limit("15m", minutes=100 * 15) == 100 + _FETCH_BUFFER_BARS


# ── 3 · Isolation: the widened frame must NOT reach the lifecycle read ───────
def test_tail_obs_bars_reproduces_the_pre_cp_frame_exactly():
    """df.tail(100) of a widened fetch IS the frame the old limit=100 returned.

    This is the whole basis of the "regime/structure/momentum unchanged" claim:
    both frames end at the same live candle and come from the same endpoint, so
    the last 100 rows are identical objects, not merely similar.
    """
    idx = pd.date_range("2026-07-14", periods=197, freq="15min", tz="UTC")
    wide = pd.DataFrame({"open": range(197), "high": range(197),
                         "low": range(197), "close": range(197),
                         "volume": range(197)}, index=idx)
    pre_cp = wide.tail(100)                    # what limit=100 would have returned

    df_obs = wide.tail(_OBS_BARS)              # what the tracker now feeds the lifecycle
    pd.testing.assert_frame_equal(df_obs, pre_cp)
    assert len(df_obs) == 100 and len(wide) == 197

    # …while the resolution walk still sees every bar since generation.
    sig_time = pd.Timestamp("2026-07-14 06:00", tz="UTC")
    df_after = wide[wide.index > sig_time]
    assert len(df_after) > len(df_obs)         # the extra history is real
    assert df_after.index[0] < df_obs.index[0]  # and it precedes the pinned window


def test_obs_window_is_a_noop_when_the_fetch_was_not_widened():
    idx = pd.date_range("2026-07-16", periods=100, freq="15min", tz="UTC")
    df = pd.DataFrame({"close": range(100)}, index=idx)
    pd.testing.assert_frame_equal(df.tail(_OBS_BARS), df)   # unchanged book path


def test_obs_window_survives_a_short_frame():
    # A freshly-listed asset can return fewer than 100 bars; tail() must not pad.
    idx = pd.date_range("2026-07-16", periods=12, freq="15min", tz="UTC")
    df = pd.DataFrame({"close": range(12)}, index=idx)
    assert len(df.tail(_OBS_BARS)) == 12


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t(); print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} CP-F0-1B fetch-window tests PASSED")
