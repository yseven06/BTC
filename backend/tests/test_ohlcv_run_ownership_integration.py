"""Real-PostgreSQL gate for RUN-LIFETIME source ownership (A3H8). OPT-IN.

WHY THIS FILE EXISTS
--------------------
A3H7 classified the concurrency defect as L2 — an OWNERSHIP-LIFETIME GAP. The
row locks `select_partition` takes are real and they work, but they end at its
COMMIT, while the work they are supposed to protect (Binance fetches, per-item
persistence) runs for the rest of the collection. Between those two points
nothing said "this source is busy", so a second run could legally be handed
symbols the first was still fetching.

Reproduced deterministically with ZERO transaction concurrency: with N=10/K=5,
a second claim one full ceil(N/K) cycle later returns the first run's symbols
while the first run is provably still in flight. No race is needed. That is why
no amount of locking INSIDE the claim transaction can fix it.

So the property under test here is not "two claims are disjoint". It is:

    at most one collection run per source is in flight at a time

The first test below is written so it can be executed against the PRE-repair
bytes: it drives the public entry point only and asserts on run sequence
consumption, so on pristine 6759b67 it FAILS (both runs collect) and after the
repair it passes.

RUNNING IT / SAFETY
-------------------
Identical contract to test_ohlcv_symbol_ledger_integration.py: reads ONLY
OHLCV_TEST_DSN, never falls back to DATABASE_URL, fails closed if they are
equal, and skips cleanly when the variable is absent.
"""

from __future__ import annotations

import asyncio
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.services.ohlcv_collector_job as J
from app.database import Base
from app.models.ohlcv_progress import OhlcvCollectionProgress as P
from app.models.ohlcv_symbol_progress import OhlcvSymbolProgress as M

pytestmark = pytest.mark.integration

SRC = "binance"


def _dsn() -> str:
    """The ONLY accepted integration DSN. Never DATABASE_URL, never a fallback."""
    dsn = os.environ.get("OHLCV_TEST_DSN")
    if not dsn:
        pytest.skip("OHLCV_TEST_DSN is not set; integration gate is opt-in")
    prod = os.environ.get("DATABASE_URL")
    if prod and prod.strip() == dsn.strip():
        # Fail, never skip: a skip here would read as "gate passed".
        pytest.fail("OHLCV_TEST_DSN equals DATABASE_URL — refusing to touch it")
    return dsn


@pytest.fixture
def dsn():
    return _dsn()


async def _fresh(dsn):
    engine = create_async_engine(dsn, pool_size=15, max_overflow=15)
    async with engine.begin() as conn:
        for t in ("ohlcv_symbol_progress", "ohlcv_collection_progress"):
            await conn.execute(text(f"DROP TABLE IF EXISTS {t}"))
        await conn.run_sync(Base.metadata.create_all,
                            tables=[M.__table__, P.__table__])
    return engine


async def _drop(engine):
    try:
        async with engine.begin() as conn:
            for t in ("ohlcv_symbol_progress", "ohlcv_collection_progress"):
                await conn.execute(text(f"DROP TABLE IF EXISTS {t}"))
    finally:
        await engine.dispose()


class _SlowCollector:
    """Stands in for Binance. Holds the run open so 'in flight' is observable.

    No socket is opened, and the pause is an Event rather than a sleep so the
    second run is attempted at a moment the first is DEFINITELY still working
    rather than at a hopeful wall-clock offset.
    """

    def __init__(self, gate: asyncio.Event, entered: asyncio.Event):
        self.gate, self.entered = gate, entered

    async def fetch_ohlcv(self, *a, **k):
        self.entered.set()
        await self.gate.wait()
        return []

    async def close(self):
        return None


def _install(collector):
    real = J.BinanceCollector
    J.BinanceCollector = lambda *a, **k: collector
    return real


async def _advisory_count(engine) -> int:
    async with engine.connect() as c:
        return (await c.execute(text(
            "SELECT count(*) FROM pg_locks WHERE locktype='advisory'"
            " AND granted"))).scalar()


@pytest.mark.asyncio
async def test_a_second_same_source_run_does_not_collect_while_the_first_is_in_flight(dsn):
    """THE lifetime property, and the one that is RED on the pre-repair bytes.

    Run A is parked inside its first fetch — claim committed, network work
    unfinished. Run B is then started on the same source. Exactly one of them
    may consume a fairness sequence and claim symbols; the other must decline
    without touching the queue.
    """
    engine = await _fresh(dsn)
    sess = async_sessionmaker(engine, expire_on_commit=False)
    gate, entered = asyncio.Event(), asyncio.Event()
    real = _install(_SlowCollector(gate, entered))
    try:
        a = asyncio.create_task(J.run_collection_once(
            sess, symbols=["AAAUSDT"], timeframes=["15m"], source=SRC,
            spacing=0.0, bind=engine))
        await asyncio.wait_for(entered.wait(), timeout=10)

        b = await J.run_collection_once(
            sess, symbols=["AAAUSDT"], timeframes=["15m"], source=SRC,
            spacing=0.0, bind=engine)

        assert b.run_seq == -1, (
            "the second run consumed a fairness sequence while the first was "
            f"still in flight (run_seq={b.run_seq})")
        assert b.symbols_attempted == 0, "the second run performed collection work"
        assert b.ownership_declined is True, "the decline was not reported"
        assert b.healthy is True, "a decline was reported as an unhealthy run"

        gate.set()
        ra = await asyncio.wait_for(a, timeout=15)
        assert ra.run_seq >= 1, "the first run lost its sequence"
    finally:
        gate.set()
        J.BinanceCollector = real
        await _drop(engine)


@pytest.mark.asyncio
async def test_two_simultaneous_same_source_runs_leave_exactly_one_collector(dsn):
    """Started together rather than staggered: still exactly one winner."""
    engine = await _fresh(dsn)
    sess = async_sessionmaker(engine, expire_on_commit=False)
    gate, entered = asyncio.Event(), asyncio.Event()
    gate.set()                                    # no parking; pure race
    real = _install(_SlowCollector(gate, entered))
    try:
        out = await asyncio.gather(*[
            J.run_collection_once(sess, symbols=["AAAUSDT"], timeframes=["15m"],
                                  source=SRC, spacing=0.0, bind=engine)
            for _ in range(3)])
        collected = [r for r in out if not r.ownership_declined]
        declined = [r for r in out if r.ownership_declined]
        assert len(collected) == 1, \
            f"{len(collected)} runs collected concurrently on one source"
        assert all(r.run_seq == -1 for r in declined), \
            "a declined run still consumed a fairness sequence"
        async with engine.connect() as c:
            seq = (await c.execute(text(
                "SELECT run_seq FROM ohlcv_collection_progress WHERE source=:s"),
                {"s": SRC})).scalar()
        assert seq == 1, f"progression advanced {seq} times for one real run"
    finally:
        J.BinanceCollector = real
        await _drop(engine)


@pytest.mark.asyncio
async def test_a_different_source_is_not_blocked(dsn):
    """Ownership is per source. Kraken must not wait behind binance."""
    engine = await _fresh(dsn)
    sess = async_sessionmaker(engine, expire_on_commit=False)
    gate, entered = asyncio.Event(), asyncio.Event()
    real = _install(_SlowCollector(gate, entered))
    try:
        a = asyncio.create_task(J.run_collection_once(
            sess, symbols=["AAAUSDT"], timeframes=["15m"], source=SRC,
            spacing=0.0, bind=engine))
        await asyncio.wait_for(entered.wait(), timeout=10)

        gate.set()                                # let kraken's fetch return
        b = await asyncio.wait_for(J.run_collection_once(
            sess, symbols=["AAAUSDT"], timeframes=["15m"], source="kraken",
            spacing=0.0, bind=engine), timeout=15)
        assert b.ownership_declined is False, "kraken was blocked by binance"
        assert b.run_seq >= 1, "kraken never claimed its own sequence"
        await asyncio.wait_for(a, timeout=15)
    finally:
        gate.set()
        J.BinanceCollector = real
        await _drop(engine)


@pytest.mark.asyncio
async def test_losing_the_owner_connection_releases_ownership(dsn):
    """No lease, no reaper, no expiry column — PostgreSQL does the cleanup.

    This is the reason a session advisory lock was chosen over a durable lease
    row: a lease has to be given an expiry, an expiry needs a clock, and a clock
    in the correctness path is what blocked this track three times already.
    """
    from app.services.ohlcv_progression import source_run_ownership

    engine = await _fresh(dsn)
    try:
        async with source_run_ownership(engine, SRC) as owned:
            assert owned is True
            assert await _advisory_count(engine) == 1
            # Kill the owner the way a crashed process would: terminate its
            # backend outright. Nothing runs an unlock.
            async with engine.connect() as c:
                await c.execute(text(
                    "SELECT pg_terminate_backend(pid) FROM pg_locks"
                    " WHERE locktype='advisory' AND granted"))
            await asyncio.sleep(0.2)
            assert await _advisory_count(engine) == 0, \
                "ownership survived the loss of its connection"
            async with source_run_ownership(engine, SRC) as again:
                assert again is True, "a later run could not take ownership"
    finally:
        await _drop(engine)


@pytest.mark.asyncio
async def test_nothing_sits_idle_in_transaction_while_the_run_works(dsn):
    """The owner connection is PINNED but must hold no open transaction.

    This repository has already been bitten by connections left
    idle-in-transaction against the Supavisor pooler, and the whole point of a
    SESSION advisory lock is that it survives COMMIT — so ownership costs one
    checked-out connection and zero open transactions.
    """
    from app.services.ohlcv_progression import source_run_ownership

    engine = await _fresh(dsn)
    try:
        async with source_run_ownership(engine, SRC) as owned:
            assert owned is True
            await asyncio.sleep(0.3)              # stand-in for network work
            async with engine.connect() as c:
                # Ask about the LOCK HOLDER, not about the server. A plain
                # "nobody is idle in transaction" count also indicts the
                # connection doing the asking, which opens its own transaction
                # on first execute — measured, and it is an artefact of the
                # measurement rather than a property of the run.
                stuck = (await c.execute(text(
                    "SELECT count(*) FROM pg_stat_activity a"
                    " JOIN pg_locks l ON l.pid = a.pid"
                    " WHERE l.locktype = 'advisory' AND l.granted"
                    "   AND a.state = 'idle in transaction'"))).scalar()
                held = (await c.execute(text(
                    "SELECT count(*) FROM pg_locks WHERE locktype='advisory'"
                    " AND granted"))).scalar()
                state = (await c.execute(text(
                    "SELECT a.state FROM pg_stat_activity a JOIN pg_locks l"
                    " ON l.pid = a.pid WHERE l.locktype='advisory'"
                    " AND l.granted"))).scalar()
            assert stuck == 0, \
                f"the owner connection is idle in transaction (state={state!r})"
            assert held == 1, "ownership was lost across the commit"
    finally:
        await _drop(engine)


@pytest.mark.asyncio
async def test_ownership_is_released_on_normal_completion_and_on_cancellation(dsn):
    from app.services.ohlcv_progression import source_run_ownership

    engine = await _fresh(dsn)
    try:
        async with source_run_ownership(engine, SRC) as owned:
            assert owned is True
        assert await _advisory_count(engine) == 0, "normal exit leaked ownership"

        async def cancelled_run():
            async with source_run_ownership(engine, SRC) as owned:
                assert owned is True
                await asyncio.sleep(30)

        t = asyncio.create_task(cancelled_run())
        while await _advisory_count(engine) == 0:
            await asyncio.sleep(0.01)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t
        assert await _advisory_count(engine) == 0, "cancellation leaked ownership"
        # And the connection must not have gone back to the pool still locked.
        async with source_run_ownership(engine, SRC) as again:
            assert again is True
    finally:
        await _drop(engine)
