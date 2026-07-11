"""CP-1 entry-detection telemetry (PASSIVE). Pure function of (signal, df) —
observes whether/when price reached the entry (Reading A: zone midpoint), how deep
it pulled, and how long it waited. Read by NOTHING; additive at extra["entry"].

Geometric note asserted below: under Reading A the SL sits BEYOND the entry
(LONG: below the midpoint), so price always reaches entry before SL →
`invalidated_before_entry` is ~always False; the meaningful "died before entry"
signal on a resolved row is `never_entered`.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pandas as pd

from app.engines.ai_decision.entry_telemetry import (
    build_entry_telemetry, ENTRY_TELEMETRY_VERSION,
)

GEN = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)


def _sig(direction="bullish", low=100.0, high=110.0, sl=95.0, gen=GEN):
    return NS(entry_zone_low=low, entry_zone_high=high,
              direction=NS(value=direction), stop_loss=sl, generated_at=gen)


def _df(rows, start=GEN + timedelta(hours=1), freq="1h"):
    """rows = list of (low, high). Index is tz-aware (matches real Binance df)."""
    idx = pd.date_range(start=start, periods=len(rows), freq=freq, tz="UTC")
    return pd.DataFrame(
        {"low": [r[0] for r in rows], "high": [r[1] for r in rows],
         "open": [r[1] for r in rows], "close": [r[0] for r in rows]},
        index=idx,
    )


# ── no trade idea ─────────────────────────────────────────────────────────────
def test_null_zone_returns_none():
    assert build_entry_telemetry(_sig(low=None), _df([(100, 110)])) is None
    assert build_entry_telemetry(_sig(high=None), _df([(100, 110)])) is None


def test_version_present():
    out = build_entry_telemetry(_sig(), _df([(104, 108)]))
    assert out["telemetry_version"] == ENTRY_TELEMETRY_VERSION == 1


# ── LONG entered (price pulls back to midpoint 105) ───────────────────────────
def test_long_entered():
    # bar1 stays high (106), bar2 dips to 104 (<=105 midpoint), never hits SL 95
    out = build_entry_telemetry(_sig(), _df([(106, 109), (104, 107), (103, 106)]))
    assert out["data_available"] is True
    assert out["entry_reached"] is True and out["never_entered"] is False
    assert out["bars_to_entry"] == 2                      # second bar
    assert out["entry_reached_at"] == (GEN + timedelta(hours=2)).replace(tzinfo=None).isoformat()
    assert out["wait_seconds"] == 2 * 3600
    assert 0.0 < out["max_zone_penetration_pct"] <= 1.0
    assert "invalidated_before_entry" not in out          # removed: dead under Reading A


# ── LONG never entered (price runs up, never pulls back to 105) ────────────────
def test_long_never_entered():
    out = build_entry_telemetry(_sig(), _df([(111, 115), (112, 118), (113, 120)]))
    assert out["data_available"] is True
    assert out["entry_reached"] is False and out["never_entered"] is True
    assert out["bars_to_entry"] is None and out["entry_reached_at"] is None
    assert out["wait_seconds"] == 3 * 3600                # gen → last bar
    assert out["max_zone_penetration_pct"] == 0.0         # never even entered zone [100,110]


# ── SHORT entered (price rises to midpoint 105) ───────────────────────────────
def test_short_entered():
    s = _sig(direction="bearish", low=100.0, high=110.0)
    out = build_entry_telemetry(s, _df([(102, 104), (104, 106)]))   # bar2 high 106 >= 105
    assert out["entry_reached"] is True and out["bars_to_entry"] == 2


# ── single gap-down bar still counts as reached (bar-granularity) ──────────────
def test_gap_down_bar_reached():
    out = build_entry_telemetry(_sig(), _df([(90, 108)]))   # low 90 <= 105 midpoint
    assert out["entry_reached"] is True and out["bars_to_entry"] == 1


# ── data-availability guards ─────────────────────────────────────────────────
def test_empty_or_none_df():
    for df in (None, pd.DataFrame()):
        out = build_entry_telemetry(_sig(), df)
        assert out["data_available"] is False and out["entry_reached"] is None


def test_no_post_birth_bars():
    # all bars are BEFORE generation → df_after empty
    df = _df([(104, 107)], start=GEN - timedelta(hours=5))
    out = build_entry_telemetry(_sig(), df)
    assert out["data_available"] is False


def test_degenerate_zone_penetration_none():
    out = build_entry_telemetry(_sig(low=105.0, high=105.0), _df([(105, 106)]))
    assert out["max_zone_penetration_pct"] is None         # zero span → undefined
    assert out["entry_reached"] is True                    # low 105 <= level 105


# ── hard fail-open: a broken df must never raise; returns "no data" base ───────
def test_fail_open_bad_index():
    bad = pd.DataFrame({"low": [1], "high": [2]}, index=[0])   # non-datetime index
    out = build_entry_telemetry(_sig(), bad)
    assert out is not None and out["data_available"] is False
