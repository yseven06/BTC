"""Real-PostgreSQL gate for the batched writer and its per-row fallback. OPT-IN.

WHY THIS FILE EXISTS
--------------------
`persist_bars` now attempts a whole page as ONE multi-row INSERT inside ONE
savepoint and drops to the original per-row savepoint loop only when the database
rejects that batch. The unit tests drive a fake session, and a fake rejects
nothing — delete the fallback entirely and every one of them stays green. The
property that actually matters cannot be faked:

  * a CHECK violation anywhere in a 159-row page must cost exactly that one row,
  * the caller's transaction must survive it usable, and
  * `persisted` / `duplicate` / `db_rejected` must come out identical to what the
    per-row writer produced before the batch existed.

Those are PostgreSQL's semantics, not SQLAlchemy's, so they are measured here
against the real DDL. The round-trip assertions are the other half: the whole
point of the change is that a healthy page costs a CONSTANT number of statements,
and a count is the only measurement that survives being run on a fast local
database. A2's own note is why the fallback is still tested rather than deleted —
a lone multi-row INSERT loses every valid row in the page to one bad one.

RUNNING IT
----------
    OHLCV_TEST_DSN=postgresql+asyncpg://user:pw@127.0.0.1:5432/throwaway \\
        pytest -m integration

Without OHLCV_TEST_DSN every test here skips, so the ordinary unit suite never
needs a database.

SAFETY
------
It reads ONE variable and never falls back to DATABASE_URL, because a fallback is
exactly how a "test" ends up pointed at production. If both are set and equal, it
fails closed rather than skipping — a silent skip would look like a pass. It
creates and drops only `ohlcv_bars`.

TIMING IS NOT ASSERTED. A local database answers in microseconds, so wall clock
here would prove nothing about production; the RTT-sensitive claim is the
STATEMENT COUNT, which is latency-independent. Measured against an injected
129 ms RTT, the same counts priced 159 bars at 120.3 s before and 0.94 s after.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.ohlcv_bar import OhlcvBar
from app.services.ohlcv_writer import BarCandidate, persist_bars

pytestmark = pytest.mark.integration

TABLE = "ohlcv_bars"
T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
STEP = timedelta(minutes=15)


def _dsn() -> str:
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
    """Sync, exactly like the neighbouring integration gates: each test builds
    its own engine inside its own event loop, so nothing depends on an async
    fixture outliving the loop pytest-asyncio hands the test."""
    return _dsn()


class RoundTrips:
    """Every statement the engine actually sends.

    SAVEPOINT, RELEASE and ROLLBACK TO all travel through `before_cursor_execute`
    in SQLAlchemy, so this is the true statement count of the writer — which is
    the quantity production latency multiplies. COMMIT does NOT pass through it
    and is counted separately, because `persist_bars` issuing one would be a
    contract violation this file has to be able to see.
    """

    def __init__(self, engine):
        self.statements: list[str] = []
        self.commits = 0

        @event.listens_for(engine.sync_engine, "before_cursor_execute")
        def _before(conn, cursor, statement, params, context, executemany):
            self.statements.append(statement.strip().split("\n")[0])

        @event.listens_for(engine.sync_engine, "commit")
        def _commit(conn):
            self.commits += 1

    def reset(self):
        self.statements.clear()
        self.commits = 0

    @property
    def count(self):
        return len(self.statements)

    def starting(self, word):
        return sum(1 for s in self.statements if s.upper().startswith(word))


@asynccontextmanager
async def disposable(dsn):
    """A fresh `ohlcv_bars`, a sessionmaker, and a statement counter."""
    engine = create_async_engine(dsn)
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
        await conn.run_sync(OhlcvBar.__table__.create)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False), RoundTrips(engine)
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
        await engine.dispose()


def bar(symbol, i, *, bad=None):
    """One candidate. `bad` breaks a CHECK the DATABASE declares — which is the
    only class of failure the fallback exists for. `validate_bar` would catch
    each of these upstream, so reaching `persist_bars` with one is deliberate."""
    ot, ct = T0 + i * STEP, T0 + (i + 1) * STEP
    o = h = lo = c = 100.0 + i
    vol = 10.0
    if bad == "bounds":
        h, lo = 1.0, 500.0                       # ck_ohlcv_bars_bounds
    elif bad == "window":
        ct = ot - STEP                           # ck_ohlcv_bars_window
    elif bad == "volume":
        vol = -1.0                               # ck_ohlcv_bars_volume
    return BarCandidate(source="binance", symbol=symbol, timeframe="15m",
                        open_time=ot, close_time=ct, open=o, high=h, low=lo,
                        close=c, volume=vol)


async def _stored(db, symbol):
    return (await db.execute(text(
        f"SELECT count(*) FROM {TABLE} WHERE symbol = :s"), {"s": symbol})).scalar()


# ── the healthy path is CONSTANT in the number of bars ───────────────────────
@pytest.mark.asyncio
@pytest.mark.parametrize("n", [1, 9, 39, 159, 500])
async def test_a_healthy_page_costs_three_statements_whatever_its_size(dsn, n):
    """SAVEPOINT + INSERT + RELEASE. Three, for one bar and for five hundred.

    The per-row writer cost exactly 3n — measured 477 statements for 159 bars,
    which at production's 129 ms RTT is the 120 s that was blowing a 25 s item
    budget on a series with nothing wrong with it.
    """
    async with disposable(dsn) as (Session, trips):
        sym = f"CONST{n}"
        async with Session() as db:
            trips.reset()
            res = await persist_bars(db, [bar(sym, i) for i in range(n)])
            assert trips.count == 3, (
                f"{n} bars cost {trips.count} statements: {trips.statements[:6]}")
            assert trips.starting("SAVEPOINT") == 1
            assert trips.starting("INSERT") == 1
            assert trips.starting("RELEASE") == 1
            assert trips.commits == 0, "persist_bars must not commit"
            assert res.persisted == n and res.duplicate == 0
            assert res.db_rejected == 0 and res.db_error == 0
            await db.commit()
            assert await _stored(db, sym) == n


@pytest.mark.asyncio
async def test_an_empty_page_touches_the_database_not_at_all(dsn):
    async with disposable(dsn) as (Session, trips):
        async with Session() as db:
            trips.reset()
            res = await persist_bars(db, [])
            assert trips.count == 0 and trips.commits == 0
            assert res.persisted == 0 and res.duplicate == 0


# ── ONE bad row costs ONE row, wherever it sits ──────────────────────────────
@pytest.mark.asyncio
@pytest.mark.parametrize("pos,label", [(0, "first"), (79, "middle"), (158, "last")])
async def test_one_rejected_row_in_a_page_of_159_costs_exactly_that_row(
        dsn, pos, label):
    """THE measurement the per-row writer was built for, now proven to survive
    the batch. A lone multi-row INSERT would keep 0 of 158 here and leave the
    session in InFailedSQLTransactionError."""
    async with disposable(dsn) as (Session, trips):
        sym = f"BAD{label}"
        page = [bar(sym, i) for i in range(159)]
        page[pos] = bar(sym, pos, bad="bounds")
        async with Session() as db:
            trips.reset()
            res = await persist_bars(db, page)
            assert res.persisted == 158, "158 valid rows must survive the bad one"
            assert res.db_rejected == 1
            assert res.duplicate == 0 and res.db_error == 0
            assert trips.commits == 0
            # The batch was attempted and rolled back, then every row retried.
            assert trips.starting("ROLLBACK") == 2, "batch savepoint + the bad row"
            # THE CALLER'S TRANSACTION IS STILL USABLE — this is what a bare
            # batch destroys, and why the batch has its own savepoint.
            assert (await db.execute(text("SELECT 1"))).scalar() == 1
            await db.commit()
            assert await _stored(db, sym) == 158


@pytest.mark.asyncio
async def test_several_rejected_rows_across_different_checks(dsn):
    async with disposable(dsn) as (Session, trips):
        sym = "MULTIBAD"
        page = [bar(sym, i) for i in range(39)]
        page[3] = bar(sym, 3, bad="bounds")
        page[20] = bar(sym, 20, bad="window")
        page[38] = bar(sym, 38, bad="volume")
        async with Session() as db:
            trips.reset()
            res = await persist_bars(db, page)
            assert res.persisted == 36 and res.db_rejected == 3
            assert res.duplicate == 0 and res.db_error == 0
            assert trips.commits == 0
            await db.commit()
            assert await _stored(db, sym) == 36


# ── duplicate accounting is EXACT on both paths ──────────────────────────────
@pytest.mark.asyncio
async def test_a_page_of_pure_duplicates_persists_nothing_and_costs_three(dsn):
    """`persisted` comes from the rowcount ON CONFLICT DO NOTHING reports;
    `duplicate` is the remainder. A duplicate is a no-op, never an error."""
    async with disposable(dsn) as (Session, trips):
        sym = "ALLDUP"
        page = [bar(sym, i) for i in range(39)]
        async with Session() as db:
            await persist_bars(db, page)
            await db.commit()
            trips.reset()
            res = await persist_bars(db, page)
            assert trips.count == 3, "a duplicate page is still one batch"
            assert res.persisted == 0 and res.duplicate == 39
            assert res.db_rejected == 0 and res.db_error == 0
            await db.commit()
            assert await _stored(db, sym) == 39


@pytest.mark.asyncio
async def test_valid_and_duplicate_and_invalid_in_one_page(dsn):
    """The mixed case. The batch cannot report which rows conflicted, so the
    fallback re-derives all three counts row by row — and must land on exactly
    the numbers the per-row writer always produced."""
    async with disposable(dsn) as (Session, trips):
        sym = "MIXED"
        async with Session() as db:
            await persist_bars(db, [bar(sym, i) for i in range(10)])
            await db.commit()
            page = [bar(sym, i) for i in range(30)]      # 10 duplicates, 20 new
            page[15] = bar(sym, 15, bad="window")        # one new one is bad
            trips.reset()
            res = await persist_bars(db, page)
            assert res.persisted == 19
            assert res.duplicate == 10
            assert res.db_rejected == 1
            assert res.db_error == 0
            assert trips.commits == 0
            await db.commit()
            assert await _stored(db, sym) == 29


@pytest.mark.asyncio
async def test_the_same_key_twice_inside_one_batch_is_a_duplicate_not_an_error(dsn):
    """ON CONFLICT DO NOTHING tolerates an intra-statement collision; DO UPDATE
    would raise a cardinality violation. Pinned because the writer's de-dup lives
    upstream in eligible_bars, so this is the safety net under it."""
    async with disposable(dsn) as (Session, trips):
        sym = "SELFDUP"
        c = bar(sym, 0)
        async with Session() as db:
            trips.reset()
            res = await persist_bars(db, [c, c])
            assert trips.count == 3, "no fallback: this is not a rejection"
            assert res.persisted == 1 and res.duplicate == 1
            assert res.db_rejected == 0 and res.db_error == 0
            await db.commit()
            assert await _stored(db, sym) == 1


# ── transaction ownership ────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_nothing_is_durable_until_the_CALLER_commits(dsn):
    """`bars_persisted` is folded by `_collect_item` only after ITS commit
    succeeds. This proves the rows really are still uncommitted when the writer
    returns them, on the batch path as much as the per-row one."""
    async with disposable(dsn) as (Session, trips):
        sym = "NOTDURABLE"
        async with Session() as db:
            res = await persist_bars(db, [bar(sym, i) for i in range(9)])
            assert res.persisted == 9
            assert trips.commits == 0
        # The session above closed WITHOUT committing, so the rows are gone.
        async with Session() as db:
            assert await _stored(db, sym) == 0


@pytest.mark.asyncio
async def test_the_session_survives_a_page_that_is_entirely_invalid(dsn):
    """Every row rejected is the worst the fallback can be asked to do: it must
    still leave the caller a transaction it can commit."""
    async with disposable(dsn) as (Session, trips):
        sym = "ALLBAD"
        page = [bar(sym, i, bad="bounds") for i in range(9)]
        async with Session() as db:
            trips.reset()
            res = await persist_bars(db, page)
            assert res.persisted == 0 and res.db_rejected == 9
            assert res.duplicate == 0 and res.db_error == 0
            assert (await db.execute(text("SELECT 1"))).scalar() == 1
            await db.commit()
            assert await _stored(db, sym) == 0
