"""CP-OHLCV-A3c REPAIR v4 — (symbol, timeframe) coverage. Still dormant.

WHAT CHANGED, AND WHY THIS FILE NO LONGER TESTS A ROTATION
----------------------------------------------------------
v3 rotated the timeframe order, `(bucket + crc32(symbol)) mod 4`, so that a
permanently broken timeframe could not sit in front of its healthy siblings
forever. An independent review then proved that bound INVALID: the timeframe
offset keyed on the GLOBAL bucket, but under outer-budget truncation a symbol is
reached only on the subsequence b, b+N, b+2N..., and whenever gcd(N, 4) > 1 the
offset FROZE. A healthy pair stayed unattempted for 2000 consecutive buckets.

The repair does not replace that modulus with a better one. It removes the
DEPENDENCY: a terminal failure no longer abandons the symbol's remaining
timeframes, it only DEGRADES their per-item budget. Every timeframe of a reached
symbol is therefore ALWAYS attempted, and ordering can no longer decide
reachability at all — so there is nothing left for a rotation to make fair.

THE PROPERTY THIS FILE PINS is consequently stronger and simpler than v3's:
    a reached symbol attempts EVERY timeframe, in EVERY bucket, under EVERY
    failure pattern — not merely "eventually, within n buckets".
The adversarial matrix below is the one v3 used, re-aimed at that property, so
the cases that caught the original starvation still run.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from app.services import ohlcv_collector_job as J
from app.services.ohlcv_collector_job import (DEGRADED_ITEM_BUDGET_SECONDS,
                                              ITEM_BUDGET_SECONDS,
                                              STORAGE_TIMEFRAMES,
                                              CollectionResult, collect_once)

UTC = timezone.utc
T0 = datetime(2026, 8, 1, tzinfo=UTC)
STEP = timedelta(minutes=15)
B0 = datetime(2026, 8, 14, tzinfo=UTC)
TFS = list(STORAGE_TIMEFRAMES)
SYMS = [f"S{i:02d}U" for i in range(6)]
IB = 0.05
DG = 0.01


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
    """`bad` = (symbol, timeframe) pairs that stall past any item bound."""

    def __init__(self, bad=()):
        self.bad = set(bad)
        self.att: list = []
        self.ok: list = []

    async def fetch_ohlcv(self, symbol, timeframe, limit=500, end_time_ms=None):
        self.att.append((symbol, timeframe))
        if (symbol, timeframe) in self.bad:
            await asyncio.sleep(300)
        self.ok.append((symbol, timeframe))
        return frame()


async def _run(bad, bucket=0, symbols=None, tfs=None):
    col = Bad(bad)
    res = CollectionResult()
    await J.collect_once(lambda: Sess(), col, symbols=list(symbols or SYMS),
                         timeframes=list(tfs or TFS), spacing=0,
                         item_budget=IB, item_budget_degraded=DG,
                         now=B0 + timedelta(seconds=1800 * bucket), result=res)
    return col, res


async def attempted_pairs(bad, runs=1, **kw):
    """Union of ATTEMPTED (not merely successful) pairs over `runs` buckets."""
    seen: set = set()
    for i in range(runs):
        col, _ = await _run(bad, bucket=i, **kw)
        seen |= set(col.att)
    return seen


# ══ THE STRUCTURAL PROPERTY ════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_a_reached_symbol_attempts_every_timeframe_in_a_single_bucket():
    """The whole point: ONE bucket is enough. No 'eventually', no horizon."""
    col, res = await _run({("S00U", "15m")})
    for tf in TFS:
        assert ("S00U", tf) in col.att, f"{tf} was never attempted"
    assert res.timeframes_attempted == len(SYMS) * len(TFS)


@pytest.mark.asyncio
async def test_no_timeframe_rotation_exists_to_go_wrong():
    """A rotation that does not exist cannot freeze. Guards the design, not a
    formula: if a future change reintroduces timeframe ordering, this fails."""
    assert not hasattr(J, "timeframe_offset"), \
        "a timeframe rotation is back; the v3 modular-lock proof applies again"
    import inspect
    src = inspect.getsource(J.collect_once)
    assert "tfs[" not in src, "the timeframe loop is slicing/rotating again"


# ══ A-Q · THE v3 ADVERSARIAL MATRIX, RE-AIMED ══════════════════════════════
@pytest.mark.asyncio
@pytest.mark.parametrize("broken", ["15m", "1h", "4h", "1d"])
async def test_ABCD_a_permanently_broken_timeframe_never_hides_its_siblings(broken):
    seen = await attempted_pairs({("S00U", broken)}, runs=4)
    missing = [(s, t) for s in SYMS for t in TFS if (s, t) not in seen]
    assert missing == [], f"{broken} broken -> unattempted {missing}"


@pytest.mark.asyncio
async def test_EF_multiple_broken_timeframes_on_one_symbol():
    for bad in ({("S00U", "15m"), ("S00U", "1h")},
                {("S00U", "15m"), ("S00U", "1h"), ("S00U", "4h")}):
        seen = await attempted_pairs(bad, runs=2)
        assert [(s, t) for s in SYMS for t in TFS if (s, t) not in seen] == []


@pytest.mark.asyncio
async def test_G_only_one_healthy_timeframe_remains():
    bad = {("S00U", t) for t in TFS if t != "1d"}
    seen = await attempted_pairs(bad, runs=2)
    assert ("S00U", "1d") in seen, "the last healthy timeframe was never attempted"


@pytest.mark.asyncio
async def test_H_every_symbol_broken_on_the_same_timeframe():
    """The worst v3 case: 18 of 18 healthy pairs were never collected."""
    seen = await attempted_pairs({(s, "15m") for s in SYMS}, runs=2)
    missing = [(s, t) for s in SYMS for t in TFS if (s, t) not in seen]
    assert missing == [], f"{len(missing)} pairs unattempted: {missing[:6]}"


@pytest.mark.asyncio
async def test_I_different_symbols_broken_on_different_timeframes():
    bad = {("S00U", "15m"), ("S01U", "1h"), ("S02U", "4h"), ("S03U", "1d")}
    seen = await attempted_pairs(bad, runs=2)
    assert [(s, t) for s in SYMS for t in TFS if (s, t) not in seen] == []


@pytest.mark.asyncio
async def test_JKL_pathology_position_does_not_matter():
    for bad in ({("S00U", "15m"), ("S01U", "15m")},
                {("S04U", "1h"), ("S05U", "1h")},
                {("S05U", "15m"), ("S00U", "4h")}):
        seen = await attempted_pairs(bad, runs=2)
        assert [(s, t) for s in SYMS for t in TFS if (s, t) not in seen] == []


@pytest.mark.asyncio
async def test_M_universe_size_changes_between_buckets():
    seen: set = set()
    for i in range(6):
        syms = SYMS + ([f"X{i}U"] if i % 2 else [])
        col, _ = await _run({("S00U", "15m")}, bucket=i, symbols=syms)
        seen |= set(col.att)
    assert [(s, t) for s in SYMS for t in TFS if (s, t) not in seen] == []


@pytest.mark.asyncio
async def test_NO_reload_between_buckets_changes_nothing():
    import importlib
    col_a, _ = await _run({("S00U", "15m")}, bucket=3)
    importlib.reload(J)
    col_b, _ = await _run({("S00U", "15m")}, bucket=3)
    assert col_a.att == col_b.att, "a reload changed the traversal"


@pytest.mark.asyncio
async def test_PQ_skipped_buckets_and_day_boundary():
    """A delayed or missed run only changes WHICH bucket is sampled — and since
    coverage no longer depends on the bucket at all, it changes nothing here."""
    for i in (0, 1, 2, 3, 47, 48, 49, 50, 96, 97, 98, 99):
        col, _ = await _run({("S00U", "15m")}, bucket=i)
        assert [(s, t) for s in SYMS for t in TFS if (s, t) not in set(col.att)] == []


# ══ THE COST THAT REPLACES ABANDON ═════════════════════════════════════════
@pytest.mark.asyncio
async def test_degraded_budget_bounds_a_fully_pathological_symbol():
    """Coverage is complete, so the bound has to come from the BUDGET. A symbol
    with all four timeframes broken must cost about one full slice plus three
    degraded ones — not four full slices, which is what abandon prevented."""
    worst = 0.0
    for i in range(4):
        col = Bad({("S00U", t) for t in TFS})
        t0 = time.monotonic()
        await J.collect_once(lambda: Sess(), col, symbols=["S00U"], timeframes=TFS,
                             spacing=0, item_budget=IB, item_budget_degraded=DG,
                             now=B0 + timedelta(seconds=1800 * i),
                             result=CollectionResult())
        worst = max(worst, time.monotonic() - t0)
    ceiling = IB + (len(TFS) - 1) * DG
    assert len(col.att) == len(TFS), "coverage was traded away for the bound"
    assert worst < ceiling * 1.6, f"blast radius {worst:.3f}s exceeds {ceiling:.3f}s"
    assert worst < len(TFS) * IB, "cost regressed to the uncapped 4x shape"


@pytest.mark.asyncio
async def test_a_healthy_symbol_is_never_degraded():
    """The reduced budget must only ever apply AFTER a terminal failure on the
    same symbol — a healthy symbol keeps the full slice on every timeframe."""
    col, res = await _run(set())
    assert res.timeframes_degraded_after_failure == 0
    assert res.symbols_degraded == 0
    assert res.healthy is True


@pytest.mark.asyncio
async def test_degradation_does_not_leak_between_symbols():
    col, res = await _run({("S00U", "15m")})
    assert res.symbols_degraded == 1, "degradation escaped to a healthy symbol"
    assert res.timeframes_degraded_after_failure == len(TFS) - 1


def test_the_degraded_budget_is_smaller_but_usable():
    """A degraded budget at or above the full one would defeat the bound; one at
    zero would fail every sibling instantly, which is starvation by another
    name. It must sit strictly between, with room for a healthy item (~1.7s p95)."""
    assert 0 < DEGRADED_ITEM_BUDGET_SECONDS < ITEM_BUDGET_SECONDS
    assert DEGRADED_ITEM_BUDGET_SECONDS >= 2.0, \
        "too small for a healthy sibling to complete — starvation by timeout"


@pytest.mark.asyncio
async def test_a_degraded_budget_of_zero_is_refused():
    with pytest.raises(ValueError, match="item_budget_degraded"):
        await J.collect_once(lambda: Sess(), Bad(), symbols=["S00U"],
                             timeframes=TFS, item_budget=IB,
                             item_budget_degraded=0, result=CollectionResult())


def test_storage_timeframes_membership_is_unchanged():
    assert STORAGE_TIMEFRAMES == ("15m", "1h", "4h", "1d")
