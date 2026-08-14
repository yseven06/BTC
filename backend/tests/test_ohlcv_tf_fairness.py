"""CP-OHLCV-A3c REPAIR v3 — (symbol, timeframe) fairness. Still dormant.

WHY. Rotating symbols was not enough. The timeframe loop ran a FIXED
("15m","1h","4h","1d") for every symbol on every run, and a terminal item
failure abandons the symbol's remaining timeframes — so a permanently broken
15m parked every healthy sibling behind it forever. Measured on 33c915d over 24
cadence buckets: a broken 15m starved 1h/4h/1d permanently, and with every
symbol broken on 15m, 18 of 18 healthy pairs were never collected once. The runs
completed comfortably, so this was never budget pressure.

THE BOUND these tests pin: within n = len(STORAGE_TIMEFRAMES) = 4 cadence
buckets in which a symbol is reached, every healthy timeframe of that symbol
gets an unobstructed attempt — regardless of how many siblings are failing.
"""

from __future__ import annotations

import asyncio
import zlib
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from app.services import ohlcv_collector_job as J
from app.services.ohlcv_collector_job import (DEFAULT_CADENCE_SECONDS,
                                              STORAGE_TIMEFRAMES,
                                              CollectionResult, collect_once,
                                              timeframe_offset)

UTC = timezone.utc
T0 = datetime(2026, 8, 1, tzinfo=UTC)
STEP = timedelta(minutes=15)
B0 = datetime(2026, 8, 14, tzinfo=UTC)
TFS = list(STORAGE_TIMEFRAMES)
SYMS = [f"S{i:02d}U" for i in range(6)]


def frame(n=6):
    idx = pd.DatetimeIndex([T0 + i * STEP for i in range(n)], tz=UTC)
    d = pd.DataFrame({"open": np.full(n, 100.0), "high": np.full(n, 110.0),
                      "low": np.full(n, 90.0), "close": np.full(n, 100.0),
                      "volume": np.full(n, 10.0)}, index=idx)
    d["close_time"] = [t + STEP for t in idx]
    return d


class Sess:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *e):
        return False

    def begin_nested(self):
        class _SP:
            async def __aenter__(s):
                return s

            async def __aexit__(s, *e):
                return False
        return _SP()

    async def execute(self, *a, **k):
        class _R:
            rowcount = 1

            def all(s):
                return []

            def scalars(s):
                class _S:
                    def all(x):
                        return []
                return _S()
        return _R()

    async def commit(self):
        return None

    async def rollback(self):
        return None


class Bad:
    """`bad` = set of (symbol, timeframe) pairs that stall past any item bound."""

    def __init__(self, bad=()):
        self.bad = set(bad)
        self.ok: list = []

    async def fetch_ohlcv(self, symbol, timeframe, limit=500, end_time_ms=None):
        if (symbol, timeframe) in self.bad:
            await asyncio.sleep(300)
        self.ok.append((symbol, timeframe))
        return frame()


async def coverage(bad, runs=12, symbols=None, tfs=None, reload_at=None,
                   size_changes=False):
    symbols = list(symbols or SYMS)
    tfs = list(tfs or TFS)
    got: set = set()
    for i in range(runs):
        if reload_at is not None and i == reload_at:
            import importlib
            importlib.reload(J)
        syms = symbols + ([f"X{i}U"] if size_changes and i % 2 else [])
        col = Bad(bad)
        await J.collect_once(lambda: Sess(), col, symbols=syms, timeframes=tfs,
                             spacing=0, item_budget=0.05,
                             now=B0 + timedelta(seconds=1800 * i),
                             result=CollectionResult())
        got |= set(col.ok)
    healthy = [(s, t) for s in symbols for t in tfs if (s, t) not in bad]
    return [x for x in healthy if x not in got]


# ══ THE ALGEBRA ════════════════════════════════════════════════════════════
def test_offset_cycles_through_every_timeframe_within_n_buckets():
    """The bound: n consecutive buckets put each timeframe first exactly once."""
    n = len(TFS)
    offs = [timeframe_offset("BTCUSDT", n, now=B0 + timedelta(seconds=1800 * i))
            for i in range(n)]
    assert sorted(offs) == list(range(n)), f"offsets do not cover 0..{n-1}: {offs}"


def test_same_bucket_is_deterministic():
    for _ in range(5):
        assert (timeframe_offset("BTCUSDT", 4, now=B0)
                == timeframe_offset("BTCUSDT", 4, now=B0))


def test_offset_is_stable_across_processes_not_salted():
    """Builtin hash() is salted per process; a salted order would make fairness
    restart-dependent, which is exactly what this design must not be."""
    import ast
    import inspect
    src = inspect.getsource(timeframe_offset)
    assert "zlib.crc32" in src
    # AST, not substring: the docstring legitimately explains why hash() is
    # unusable, and a prose mention must not read as a call.
    tree = ast.parse(src.lstrip())
    calls = {getattr(n.func, "id", None) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert "hash" not in calls, "a salted hash would break restart independence"
    assert (timeframe_offset("BTCUSDT", 4, now=B0)
            == (int(B0.timestamp() // DEFAULT_CADENCE_SECONDS)
                + zlib.crc32(b"BTCUSDT")) % 4)


def test_reload_does_not_change_the_order():
    import importlib
    buckets = [B0 + timedelta(seconds=1800 * i) for i in range(8)]
    before = [J.timeframe_offset("BTCUSDT", 4, now=b) for b in buckets]
    importlib.reload(J)
    after = [J.timeframe_offset("BTCUSDT", 4, now=b) for b in buckets]
    assert before == after


def test_degenerate_inputs():
    assert timeframe_offset("X", 0, now=B0) == 0
    assert timeframe_offset("X", 1, now=B0) == 0
    with pytest.raises(ValueError, match="cadence_seconds"):
        timeframe_offset("X", 4, now=B0, cadence_seconds=0)


def test_rotation_is_not_a_candle_authority():
    import inspect
    src = inspect.getsource(timeframe_offset)
    assert "close" not in src and "watermark" not in src


def test_storage_timeframes_membership_is_unchanged():
    assert STORAGE_TIMEFRAMES == ("15m", "1h", "4h", "1d")


# ══ A-Q · ADVERSARIAL (symbol, timeframe) COVERAGE ═════════════════════════
@pytest.mark.asyncio
@pytest.mark.parametrize("broken", ["15m", "1h", "4h", "1d"])
async def test_ABCD_a_permanently_broken_timeframe_never_starves_its_siblings(broken):
    starved = await coverage({("S00U", broken)})
    assert starved == [], f"{broken} broken -> starved {starved}"


@pytest.mark.asyncio
async def test_EF_multiple_broken_timeframes_on_one_symbol():
    assert await coverage({("S00U", "15m"), ("S00U", "1h")}) == []
    assert await coverage({("S00U", "15m"), ("S00U", "1h"), ("S00U", "4h")}) == []


@pytest.mark.asyncio
async def test_G_only_one_healthy_timeframe_remains():
    starved = await coverage({("S00U", t) for t in TFS if t != "1d"})
    assert starved == [], f"the last healthy timeframe was starved: {starved}"


@pytest.mark.asyncio
async def test_H_every_symbol_broken_on_the_same_timeframe():
    """The worst pre-repair case: 18 of 18 healthy pairs never collected."""
    starved = await coverage({(s, "15m") for s in SYMS})
    assert starved == [], f"starved {len(starved)} pairs: {starved[:6]}"


@pytest.mark.asyncio
async def test_I_different_symbols_broken_on_different_timeframes():
    starved = await coverage({("S00U", "15m"), ("S01U", "1h"),
                              ("S02U", "4h"), ("S03U", "1d")})
    assert starved == []


@pytest.mark.asyncio
async def test_JKL_pathology_position_does_not_matter():
    assert await coverage({("S00U", "15m"), ("S01U", "15m")}) == []   # low
    assert await coverage({("S04U", "1h"), ("S05U", "1h")}) == []     # high
    assert await coverage({("S05U", "15m"), ("S00U", "4h")}) == []    # across wrap


@pytest.mark.asyncio
async def test_M_universe_size_changes_between_buckets():
    assert await coverage({("S00U", "15m")}, size_changes=True) == []


@pytest.mark.asyncio
async def test_NO_reload_between_buckets_does_not_reset_fairness():
    assert await coverage({("S00U", "15m")}, reload_at=5) == []


@pytest.mark.asyncio
async def test_PQ_skipped_buckets_and_day_boundary():
    """A delayed or missed run only changes WHICH bucket is sampled."""
    got: set = set()
    # Gaps and hour/day boundaries, but spanning all four bucket residues —
    # a sparse list that happened to hit only two residues would prove nothing.
    for i in (0, 1, 2, 3, 47, 48, 49, 50, 96, 97, 98, 99):
        col = Bad({("S00U", "15m")})
        await J.collect_once(lambda: Sess(), col, symbols=SYMS, timeframes=TFS,
                             spacing=0, item_budget=0.05,
                             now=B0 + timedelta(seconds=1800 * i),
                             result=CollectionResult())
        got |= set(col.ok)
    healthy = [(s, t) for s in SYMS for t in TFS if (s, t) != ("S00U", "15m")]
    assert [x for x in healthy if x not in got] == []


# ══ BLAST RADIUS MUST NOT REGRESS ══════════════════════════════════════════
@pytest.mark.asyncio
async def test_one_pathological_symbol_still_costs_about_one_item_budget():
    """The abandon rule must survive: a fully broken symbol must not spend four
    item budgets, which is the shape the previous repair removed."""
    import time
    IB = 0.05
    worst = 0.0
    for i in range(8):
        col = Bad({("S00U", t) for t in TFS})
        t0 = time.monotonic()
        await J.collect_once(lambda: Sess(), col, symbols=["S00U"], timeframes=TFS,
                             spacing=0, item_budget=IB,
                             now=B0 + timedelta(seconds=1800 * i),
                             result=CollectionResult())
        worst = max(worst, time.monotonic() - t0)
    assert worst < 2.5 * IB, f"blast radius regressed to {worst/IB:.1f}x item budget"


@pytest.mark.asyncio
async def test_abandon_still_skips_siblings_within_a_single_run():
    col = Bad({("S00U", "15m")})
    res = CollectionResult()
    # bucket chosen so the broken 15m is FIRST for this symbol
    n = len(TFS)
    want = TFS.index("15m")
    i = next(k for k in range(n)
             if timeframe_offset("S00U", n, now=B0 + timedelta(seconds=1800 * k)) == want)
    await J.collect_once(lambda: Sess(), col, symbols=["S00U"], timeframes=TFS,
                         spacing=0, item_budget=0.05,
                         now=B0 + timedelta(seconds=1800 * i), result=res)
    assert res.timeframes_skipped_after_failure == n - 1
    assert res.symbols_abandoned == 1


# ══ SYMBOL-LEVEL FAIRNESS MUST STILL HOLD ══════════════════════════════════
@pytest.mark.asyncio
async def test_symbol_rotation_survives_the_timeframe_change():
    offs = [J.rotation_offset(len(SYMS), now=B0 + timedelta(seconds=1800 * i))
            for i in range(len(SYMS))]
    assert sorted(offs) == list(range(len(SYMS)))
