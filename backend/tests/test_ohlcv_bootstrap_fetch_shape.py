"""CP-OHLCV-A3D — the bootstrap request shape.

The first genuine production run fetched 24500 bars to keep 196: every bootstrap
item reused the 500-bar catch-up window and then trimmed to 4. These guards pin
the repair AND the reason the obvious version of it is wrong — `drop_newest=True`
means a 4-bar request yields 3 usable bars.

Nothing here activates or registers anything.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.services.ohlcv_collector_job import (
    BOOTSTRAP_FETCH_LIMIT, BOOTSTRAP_MAX_BARS, DEFAULT_FETCH_LIMIT,
    MIN_FETCH_LIMIT, bootstrap_fetch_limit,
)
from app.services.ohlcv_writer import WriteResult, apply_lower_bound, eligible_bars

BACKEND = pathlib.Path(__file__).resolve().parent.parent
STEP = timedelta(minutes=15)


def _frame(n: int, now: datetime) -> pd.DataFrame:
    """A Binance-shaped 15m frame whose newest bar is still forming."""
    opens = [(now - STEP * (n - 1 - i)).replace(second=0, microsecond=0)
             for i in range(n)]
    return pd.DataFrame(
        {"open": [100.0 + i for i in range(n)],
         "high": [101.0 + i for i in range(n)],
         "low": [99.0 + i for i in range(n)],
         "close": [100.5 + i for i in range(n)],
         "volume": [10.0 + i for i in range(n)],
         "close_time": [o + STEP - timedelta(milliseconds=1) for o in opens]},
        index=pd.DatetimeIndex(opens, name="open_time"))


def _kept(limit: int, *, max_bars: int = BOOTSTRAP_MAX_BARS) -> int:
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    cands, _ = eligible_bars(_frame(limit, now), "BTCUSDT", "15m", now=now)
    return len(apply_lower_bound(cands, after=None, max_bars=max_bars,
                                 result=WriteResult()))


# ══ THE DEFECT THE NAIVE REPAIR WOULD SHIP ═════════════════════════════════
def test_a_four_bar_request_under_seeds_and_that_is_why_plus_two_exists():
    """THE regression. `drop_newest=True` discards the newest element of every
    response, so limit == BOOTSTRAP_MAX_BARS yields one bar too few — silently,
    on a series' only bootstrap run."""
    assert _kept(BOOTSTRAP_MAX_BARS) == BOOTSTRAP_MAX_BARS - 1 == 3


def test_the_shipped_limit_yields_the_full_seed_with_one_bar_to_spare():
    assert BOOTSTRAP_FETCH_LIMIT == BOOTSTRAP_MAX_BARS + 2 == 6
    assert _kept(BOOTSTRAP_FETCH_LIMIT) == BOOTSTRAP_MAX_BARS
    # the spare: one MORE unexpected drop still leaves a full seed
    assert _kept(BOOTSTRAP_FETCH_LIMIT - 1) == BOOTSTRAP_MAX_BARS


def test_the_helper_tracks_the_callers_own_bootstrap_value():
    for b in (1, 2, 3, 4, 7, 20):
        assert bootstrap_fetch_limit(b) == b + 2
        # >= MIN_FETCH_LIMIT holds by construction, not by a clamp: the
        # `bootstrap >= 1` guard puts the floor at 3. A clamp here would be
        # unreachable code, and an unkillable mutant proved exactly that.
        assert bootstrap_fetch_limit(b) >= MIN_FETCH_LIMIT
    assert bootstrap_fetch_limit(BOOTSTRAP_MAX_BARS) == BOOTSTRAP_FETCH_LIMIT
    with pytest.raises(ValueError):
        bootstrap_fetch_limit(0)


# ══ BOOTSTRAP vs INCREMENTAL ARE DIFFERENT REQUESTS ════════════════════════
def test_the_call_site_branches_on_the_watermark_not_on_a_constant():
    """AST, so a comment mentioning either constant cannot satisfy it. The
    bootstrap arm must use the small request; the incremental arm must keep
    `limit`, which is the 500-bar catch-up window."""
    src = inspect.getsource(
        __import__("app.services.ohlcv_collector_job", fromlist=["collect_once"]).collect_once)
    tree = ast.parse(ast.unparse(ast.parse(src)))
    ifexps = [n for n in ast.walk(tree) if isinstance(n, ast.IfExp)]
    shaped = [n for n in ifexps
              if "bootstrap_fetch_limit" in ast.unparse(n.body)
              and ast.unparse(n.orelse).strip() == "limit"]
    assert len(shaped) == 1, "the request shape is not chosen by the watermark"
    assert "mark is None" in ast.unparse(shaped[0].test)


def test_the_incremental_window_is_still_five_hundred():
    """The catch-up depth is the ONE thing 500 was actually buying: 500 x 15m is
    ~5.2 days of downtime recovery. Shrinking it would cap how far a stalled
    series can catch up, which is a different decision from the seed size."""
    assert DEFAULT_FETCH_LIMIT == 500
    assert BOOTSTRAP_FETCH_LIMIT < DEFAULT_FETCH_LIMIT


def test_the_trading_collector_is_untouched_by_this_change():
    """`DEFAULT_FETCH_LIMIT`/`MIN_FETCH_LIMIT`/`BOOTSTRAP_*` must stay OHLCV-only:
    the shared BinanceCollector is on the trading path."""
    hits = []
    for p in (BACKEND / "app").rglob("*.py"):
        if p.name == "ohlcv_collector_job.py":
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for token in ("DEFAULT_FETCH_LIMIT", "MIN_FETCH_LIMIT",
                      "BOOTSTRAP_FETCH_LIMIT", "BOOTSTRAP_MAX_BARS",
                      "bootstrap_fetch_limit"):
            if token in text:
                hits.append(f"{p.relative_to(BACKEND).as_posix()}:{token}")
    assert hits == [], f"an OHLCV request constant leaked outside the subsystem: {hits}"


# ══ RESPONSES THAT ARE NOT THE HAPPY CASE ══════════════════════════════════
@pytest.mark.parametrize("available,expected", [(1, 0), (2, 1), (3, 2), (4, 3),
                                                (5, 4), (6, 4), (10, 4)])
def test_a_short_or_new_listing_response_stays_valid(available, expected):
    """A freshly listed symbol returns fewer bars than requested. That must seed
    what exists rather than fail — under-seeding is self-healing, because the
    watermark simply advances from wherever it lands."""
    assert _kept(available) == expected


def test_the_open_final_candle_is_withheld_at_the_small_limit_too():
    """The saving must not come from admitting the forming candle."""
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    _, res = eligible_bars(_frame(BOOTSTRAP_FETCH_LIMIT, now), "BTCUSDT", "15m", now=now)
    assert res.forming_or_not_closed >= 1
    assert res.fetched == BOOTSTRAP_FETCH_LIMIT


def test_a_watermarked_series_is_not_capped_at_all():
    """max_bars is None on the incremental path: the whole catch-up window is
    offered, and only `after` decides what is new."""
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    cands, _ = eligible_bars(_frame(20, now), "BTCUSDT", "15m", now=now)
    after = cands[5].open_time
    kept = apply_lower_bound(cands, after=after, max_bars=None, result=WriteResult())
    assert len(kept) == len(cands) - 6
    assert all(c.open_time > after for c in kept)
