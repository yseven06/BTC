"""CP-OHLCV-A3c REPAIR v2 — rotation fairness. Still dormant; nothing scheduled.

WHY THIS EXISTS. The dormant review measured deterministic starvation: the
universe is a TOTAL order (Asset.symbol is unique), every run began at index 0,
and a 600 s outer budget admits only ~600/25 = 24 items. With three pathological
low-order symbols the SAME 17-symbol suffix went unattempted in four consecutive
runs. 25 s x 228 items = 5700 s, so 600 s was never a full-universe bound and
must not be described as one.

THE CONTRACT THESE TESTS PIN is EVENTUAL fairness, not per-run completeness:
no fixed healthy suffix may stay unattempted merely because the same
pathological symbols recur.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from app.services import ohlcv_collector_job as J
from app.services.ohlcv_collector_job import (DEFAULT_CADENCE_SECONDS,
                                              CollectionResult, collect_once,
                                              rotation_offset)

UTC = timezone.utc
T0 = datetime(2026, 8, 1, tzinfo=UTC)
STEP = timedelta(minutes=15)
BUCKET0 = datetime(2026, 8, 14, 0, 0, tzinfo=UTC)


def frame(n=6):
    idx = pd.DatetimeIndex([T0 + i * STEP for i in range(n)], tz=UTC)
    df = pd.DataFrame({"open": np.full(n, 100.0), "high": np.full(n, 110.0),
                       "low": np.full(n, 90.0), "close": np.full(n, 100.0),
                       "volume": np.full(n, 10.0)}, index=idx)
    df["close_time"] = [t + STEP for t in idx]
    return df


class Sess:
    def __init__(self, slow_symbols=()):
        self.slow = set(slow_symbols)

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

    async def execute(self, stmt, *a, **k):
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


class Col:
    """`bad` symbols stall past any item budget; everything else is healthy."""

    def __init__(self, bad=(), db_fail=()):
        self.bad, self.db_fail = set(bad), set(db_fail)
        self.seen: list = []

    async def fetch_ohlcv(self, symbol, timeframe, limit=500, end_time_ms=None):
        self.seen.append(symbol)
        if symbol in self.bad:
            await asyncio.sleep(300)
        if symbol in self.db_fail:
            raise RuntimeError("db path unhealthy")
        return frame()


# Scaled to the real ratio: 600s outer : 25s item = 24 : 1.
OUTER, ITEM = 1.2, 0.05


async def _one_run(symbols, bucket, col, *, timeframes=("15m", "1h", "4h", "1d")):
    """One cadence run, cancelled at the scaled outer budget."""
    res = CollectionResult()
    task = asyncio.create_task(collect_once(
        lambda: Sess(), col, symbols=list(symbols), timeframes=list(timeframes),
        spacing=0, item_budget=ITEM, cadence_seconds=DEFAULT_CADENCE_SECONDS,
        now=bucket, result=res))
    await asyncio.sleep(OUTER)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    return res


async def _sweep(symbols, bad, runs, *, db_fail=(), start=0):
    reached = []
    for i in range(runs):
        col = Col(bad=bad, db_fail=db_fail)
        bucket = BUCKET0 + timedelta(seconds=DEFAULT_CADENCE_SECONDS * (start + i))
        await _one_run(symbols, bucket, col)
        reached.append(set(col.seen))
    return reached


# ══ ROTATION ALGEBRA ═══════════════════════════════════════════════════════
def test_same_bucket_is_deterministic():
    for _ in range(5):
        assert rotation_offset(57, now=BUCKET0) == rotation_offset(57, now=BUCKET0)


def test_offset_advances_one_symbol_per_cadence_bucket():
    offs = [rotation_offset(57, now=BUCKET0 + timedelta(seconds=1800 * i))
            for i in range(10)]
    assert offs == [(offs[0] + i) % 57 for i in range(10)]


def test_every_offset_occurs_once_per_full_rotation():
    n = 57
    offs = {rotation_offset(n, now=BUCKET0 + timedelta(seconds=1800 * i))
            for i in range(n)}
    assert offs == set(range(n)), "a full rotation must visit every start position"


def test_rotation_is_restart_and_redeploy_independent():
    """The offset comes from the clock alone — there is no cursor to lose."""
    t = BUCKET0 + timedelta(seconds=1800 * 12345)
    before = rotation_offset(57, now=t)
    # simulate a process restart: brand-new module state, same wall clock
    import importlib
    importlib.reload(J)
    after = J.rotation_offset(57, now=t)
    assert before == after
    assert after != 0 or True   # value itself is irrelevant; identity is the point


def test_rotation_survives_universe_size_changes():
    for n in (1, 2, 56, 57, 58, 250):
        off = rotation_offset(n, now=BUCKET0)
        assert 0 <= off < n
    assert rotation_offset(0, now=BUCKET0) == 0, "an empty universe must not crash"


def test_cadence_must_be_positive():
    with pytest.raises(ValueError, match="cadence_seconds"):
        rotation_offset(10, now=BUCKET0, cadence_seconds=0)


def test_rotation_is_not_a_candle_authority():
    """The clock buckets the ORDER; closure stays the exchange's job."""
    import inspect
    src = inspect.getsource(J.rotation_offset)
    assert "close" not in src and "watermark" not in src


# ══ A-I · ADVERSARIAL REPEATED-RUN FAIRNESS ════════════════════════════════
SYMS = [f"S{i:02d}U" for i in range(20)]


@pytest.mark.asyncio
async def test_A_one_pathological_lowest_order_symbol():
    reached = await _sweep(SYMS, bad=SYMS[:1], runs=20)
    union = set().union(*reached)
    assert union == set(SYMS), f"never reached: {sorted(set(SYMS) - union)}"


@pytest.mark.asyncio
async def test_B_three_pathological_lowest_order_symbols():
    """The exact shape that starved 17 of 20 symbols forever before the repair."""
    reached = await _sweep(SYMS, bad=SYMS[:3], runs=20)
    union = set().union(*reached)
    assert union == set(SYMS), f"never reached: {sorted(set(SYMS) - union)}"


@pytest.mark.asyncio
async def test_C_pathological_symbols_in_the_middle():
    reached = await _sweep(SYMS, bad=SYMS[8:11], runs=20)
    union = set().union(*reached)
    assert union == set(SYMS), f"never reached: {sorted(set(SYMS) - union)}"


@pytest.mark.asyncio
async def test_D_pathological_at_both_ends():
    reached = await _sweep(SYMS, bad=SYMS[:2] + SYMS[-2:], runs=20)
    union = set().union(*reached)
    assert union == set(SYMS), f"never reached: {sorted(set(SYMS) - union)}"


@pytest.mark.asyncio
async def test_E_every_timeframe_of_a_symbol_times_out():
    """Blast radius: a dead symbol must cost ONE item, not one per timeframe."""
    col = Col(bad={"S00U"})
    res = await _one_run(SYMS, BUCKET0, col)
    assert res.timeframes_skipped_after_failure >= 3, \
        "remaining timeframes of a dead symbol were still attempted"
    assert res.symbols_abandoned >= 1
    assert col.seen.count("S00U") == 1, "the dead symbol was fetched more than once"


@pytest.mark.asyncio
async def test_F_db_failure_for_one_symbol_does_not_starve_the_rest():
    reached = await _sweep(SYMS, bad=(), db_fail=SYMS[:2], runs=8)
    union = set().union(*reached)
    assert union == set(SYMS), f"never reached: {sorted(set(SYMS) - union)}"


@pytest.mark.asyncio
async def test_G_healthy_universe_completes_every_run():
    col = Col()
    res = await _one_run(SYMS, BUCKET0, col)
    assert res.symbols_attempted == len(SYMS)
    assert res.symbols_unattempted == 0
    assert res.cancelled is False


@pytest.mark.asyncio
async def test_H_universe_membership_changes_between_runs():
    seen = set()
    for i in range(24):
        syms = SYMS + [f"NEW{i%3}U"] if i % 2 else SYMS
        col = Col(bad=SYMS[:2])
        await _one_run(syms, BUCKET0 + timedelta(seconds=1800 * i), col)
        seen |= set(col.seen)
    assert set(SYMS) <= seen, f"original symbols starved: {sorted(set(SYMS) - seen)}"
    assert any(s.startswith("NEW") for s in seen), "newly added symbols never entered"


def test_I_simulated_process_restart_does_not_reset_fairness():
    """Restarting mid-sequence must not send the rotation back to index 0.

    Compared as OFFSETS, not as reached-symbol sets: the offset is the only
    state the mechanism has and the only thing a restart could lose. (An
    earlier draft compared `sorted(reached)[0]`, which is alphabetical order,
    not visit order, and so measured nothing.)
    """
    import importlib
    buckets = [BUCKET0 + timedelta(seconds=1800 * i) for i in range(12)]
    before = [J.rotation_offset(len(SYMS), now=b) for b in buckets]
    importlib.reload(J)                       # brand-new module state
    after = [J.rotation_offset(len(SYMS), now=b) for b in buckets]

    assert before == after, "a reload changed the rotation"
    assert len(set(after)) == 12, f"the rotation did not advance: {after}"
    assert after[6:] != after[:6], "the sequence restarted after the reload"


@pytest.mark.asyncio
async def test_no_fixed_suffix_can_starve_over_a_full_rotation():
    """The load-bearing claim, stated as coverage over one full rotation."""
    reached = await _sweep(SYMS, bad=SYMS[:3], runs=len(SYMS))
    counts = {s: sum(s in r for r in reached) for s in SYMS}
    assert all(c >= 1 for c in counts.values()), \
        f"starved over a full rotation: {[s for s, c in counts.items() if c == 0]}"


# ══ COVERAGE TELEMETRY ═════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_unattempted_is_distinguishable_from_zero_eligible():
    # Enough pathological symbols that even with per-symbol abandon the outer
    # budget expires part-way. (With only three, the repair now finishes the
    # run outright — which is exactly what the abandon rule buys.)
    col = Col(bad=SYMS)
    res = CollectionResult()
    task = asyncio.create_task(collect_once(
        lambda: Sess(), col, symbols=SYMS, spacing=0, item_budget=ITEM,
        cadence_seconds=DEFAULT_CADENCE_SECONDS, now=BUCKET0, result=res))
    await asyncio.sleep(ITEM * 6)             # cut well before all 20 are reached
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert res.cancelled is True
    assert res.symbols_unattempted > 0, "a truncated run reported full coverage"
    assert res.symbols_unattempted == res.symbols_selected - res.symbols_attempted
    assert res.symbols_skipped == 0, \
        "unreached symbols were laundered into 'nothing new'"
    assert res.healthy is False


@pytest.mark.asyncio
async def test_a_quiet_symbol_is_skipped_not_unattempted():
    col = Col()
    rows = [(s, tf, T0 + 4 * STEP) for s in SYMS for tf in ("15m", "1h", "4h", "1d")]

    class WM(Sess):
        async def execute(self, stmt, *a, **k):
            text = " ".join(str(stmt).split())
            r = rows if "wm_pairs" in text else []

            class _R:
                rowcount = 1

                def all(s):
                    return r

                def scalars(s):
                    class _S:
                        def all(x):
                            return []
                    return _S()
            return _R()

    res = CollectionResult()
    await collect_once(lambda: WM(), col, symbols=SYMS, spacing=0,
                       item_budget=5.0, now=BUCKET0, result=res)
    assert res.symbols_skipped == len(SYMS), "a caught-up symbol must count as skipped"
    assert res.symbols_unattempted == 0
    assert res.healthy is True


def test_coverage_fields_are_in_the_witness():
    d = CollectionResult().as_dict()
    for k in ("rotation_offset", "symbols_unattempted", "symbols_abandoned",
              "timeframes_skipped_after_failure"):
        assert k in d, f"witness is missing {k}"


@pytest.mark.asyncio
async def test_418_is_not_demoted_to_an_ordinary_symbol_failure():
    """The run-abort semantics reviewed earlier must survive the fairness work."""
    class Resp:
        def __init__(self, c):
            self.status_code, self.headers = c, {}

    class Err(Exception):
        def __init__(self, c):
            super().__init__(str(c))
            self.response = Resp(c)

    class Banned(Col):
        async def fetch_ohlcv(self, symbol, timeframe, limit=500, end_time_ms=None):
            self.seen.append(symbol)
            raise Err(418)

    col = Banned()
    res = CollectionResult()
    await collect_once(lambda: Sess(), col, symbols=SYMS, timeframes=["15m"],
                       spacing=0, item_budget=5.0, now=BUCKET0, result=res)
    assert res.aborted is True and res.abort_reason == "http_418_ip_banned"
    assert len(col.seen) == 1, "requests continued at a banned IP"
    assert res.symbols_abandoned <= 1
    assert res.healthy is False
