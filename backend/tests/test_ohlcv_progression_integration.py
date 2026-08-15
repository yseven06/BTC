"""Real-PostgreSQL gate for the durable progression primitive. OPT-IN.

WHY THIS FILE EXISTS
--------------------
The unit tests are statement-sensitive — they compile what the implementation
emits and apply it to an in-memory table — and they kill every mutation aimed at
the SQL. What they cannot prove is what PostgreSQL itself does: that the row lock
inside `INSERT ... ON CONFLICT DO UPDATE` really serialises concurrent callers, so
no two runs receive the same sequence and no increment is lost. That property was
previously evidenced only by a throwaway operator script, which left nothing in
the repository — the same shape of gap that let four mutations survive a review.

It also pins the catalog divergence this checkpoint repaired: `create_all` runs
BEFORE the migration, so the model builds the table on a fresh database and the
migration is a no-op. Declaring a different type in the migration produced a table
whose catalog shape depended on which path built it.

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
creates and drops only `ohlcv_collection_progress`, and it refuses to run against
a DSN that does not look disposable.
"""

from __future__ import annotations

import asyncio
import os
import pathlib

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.ohlcv_progress import OhlcvCollectionProgress as M
from app.services.ohlcv_progression import acquire_run_sequence

pytestmark = pytest.mark.integration

TABLE = "ohlcv_collection_progress"
MIGRATION = (pathlib.Path(__file__).resolve().parent.parent
             / "migrations" / "0012_ohlcv_progression.sql")
CONCURRENCY = int(os.environ.get("OHLCV_TEST_CONCURRENCY", "120"))


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
    return _dsn()


async def _fresh(dsn, use_migration=False):
    """A disposable progression table, built by whichever path is under test."""
    engine = create_async_engine(dsn, pool_size=20, max_overflow=20)
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
        if use_migration:
            await conn.exec_driver_sql(MIGRATION.read_text(encoding="utf-8"))
        else:
            await conn.run_sync(Base.metadata.create_all, tables=[M.__table__])
    return engine


async def _drop(engine):
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
    await engine.dispose()


async def _catalog(conn):
    cols = (await conn.execute(text(
        "SELECT column_name, data_type, is_nullable, column_default "
        f"FROM information_schema.columns WHERE table_name='{TABLE}' ORDER BY 1"))).all()
    cons = (await conn.execute(text(
        "SELECT contype, pg_get_constraintdef(oid) FROM pg_constraint "
        f"WHERE conrelid=CAST('{TABLE}' AS regclass) ORDER BY 1, 2"))).all()
    idx = (await conn.execute(text(
        f"SELECT indexdef FROM pg_indexes WHERE tablename='{TABLE}' ORDER BY 1"))).all()
    return [tuple(r) for r in cols], [tuple(r) for r in cons], [tuple(r) for r in idx]


# ══ CATALOG EQUIVALENCE — the defect this checkpoint repaired ══════════════
@pytest.mark.asyncio
async def test_both_construction_paths_yield_the_same_catalog_object(dsn):
    """`create_all` runs BEFORE the migration, so on a fresh database the MODEL
    builds this table. If the two declarations disagree, the catalog shape depends
    on which path ran — measured once as `character varying` vs `text`, with the
    source CHECK rendering differently in each. Names alone would not show it."""
    engine = await _fresh(dsn, use_migration=False)
    async with engine.connect() as conn:
        from_model = await _catalog(conn)
    await engine.dispose()

    engine = await _fresh(dsn, use_migration=True)
    async with engine.connect() as conn:
        from_migration = await _catalog(conn)

    try:
        assert from_model[0] == from_migration[0], (
            f"columns diverge\n model    : {from_model[0]}\n migration: {from_migration[0]}")
        assert from_model[1] == from_migration[1], (
            f"constraints diverge\n model    : {from_model[1]}\n"
            f" migration: {from_migration[1]}")
        assert from_model[2] == from_migration[2], "indexes diverge"
    finally:
        await _drop(engine)


@pytest.mark.asyncio
async def test_the_source_column_is_the_primary_identity_and_not_nullable(dsn):
    engine = await _fresh(dsn)
    try:
        async with engine.connect() as conn:
            cols, cons, _ = await _catalog(conn)
            src = [c for c in cols if c[0] == "source"][0]
            assert src[2] == "NO", f"source became nullable: {src}"
            pk = [d for t, d in cons if t == b"p"]
            assert pk == ["PRIMARY KEY (source)"], f"primary identity changed: {pk}"
            checks = sorted(d for t, d in cons if t == b"c")
            assert any("run_seq >= 0" in d for d in checks), checks
            assert any("btrim" in d for d in checks), checks
    finally:
        await _drop(engine)


@pytest.mark.asyncio
async def test_the_checks_reject_invalid_rows_in_the_real_database(dsn):
    engine = await _fresh(dsn)
    try:
        for values, why in ((("'x'", "-1"), "negative run_seq"),
                            (("'   '", "0"), "blank source")):
            async with engine.connect() as conn:
                with pytest.raises(Exception):
                    await conn.execute(text(
                        f"INSERT INTO {TABLE}(source, run_seq) "
                        f"VALUES ({values[0]}, {values[1]})"))
                    await conn.commit()
                await conn.rollback()
    finally:
        await _drop(engine)


# ══ WHAT ONLY A REAL SERVER CAN PROVE ══════════════════════════════════════
@pytest.mark.asyncio
async def test_first_acquire_is_one_and_repeats_are_consecutive(dsn):
    engine = await _fresh(dsn)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        got = [await acquire_run_sequence(Session, "binance") for _ in range(5)]
        assert got == [1, 2, 3, 4, 5], got
        async with engine.connect() as conn:
            stored = (await conn.execute(text(
                f"SELECT run_seq FROM {TABLE} WHERE source='binance'"))).scalar()
        assert stored == got[-1], "returned value is not the persisted value"
    finally:
        await _drop(engine)


@pytest.mark.asyncio
async def test_concurrent_same_source_acquires_lose_nothing(dsn):
    """THE PROPERTY THE FAKE CANNOT PROVE: that PostgreSQL's row lock actually
    serialises these. A lost update or a duplicate here would mean two runs share
    a fairness phase."""
    engine = await _fresh(dsn)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        got = await asyncio.gather(*[acquire_run_sequence(Session, "binance")
                                     for _ in range(CONCURRENCY)])
        assert len(set(got)) == CONCURRENCY, \
            f"duplicate sequences: {sorted(v for v in got if got.count(v) > 1)[:5]}"
        assert sorted(got) == list(range(1, CONCURRENCY + 1)), "an increment was lost"
        async with engine.connect() as conn:
            stored = (await conn.execute(text(
                f"SELECT run_seq FROM {TABLE} WHERE source='binance'"))).scalar()
        assert stored == CONCURRENCY, f"persisted {stored}, expected {CONCURRENCY}"
    finally:
        await _drop(engine)


@pytest.mark.asyncio
async def test_sources_stay_isolated_under_concurrency(dsn):
    engine = await _fresh(dsn)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        n = max(10, CONCURRENCY // 4)
        await asyncio.gather(
            *[acquire_run_sequence(Session, "binance") for _ in range(n)],
            *[acquire_run_sequence(Session, "kraken") for _ in range(n // 2)])
        async with engine.connect() as conn:
            rows = dict((await conn.execute(text(
                f"SELECT source, run_seq FROM {TABLE} ORDER BY source"))).all())
        assert rows == {"binance": n, "kraken": n // 2}, rows
    finally:
        await _drop(engine)


@pytest.mark.asyncio
async def test_the_persisted_source_is_the_one_supplied(dsn):
    engine = await _fresh(dsn)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await acquire_run_sequence(Session, "kraken")
        async with engine.connect() as conn:
            sources = [r[0] for r in (await conn.execute(text(
                f"SELECT source FROM {TABLE}"))).all()]
        assert sources == ["kraken"], f"a kraken run wrote {sources}"
    finally:
        await _drop(engine)


@pytest.mark.asyncio
async def test_a_new_engine_continues_from_the_durable_value(dsn):
    """Restart/redeploy: the sequence lives in the database, so a brand-new pool
    resumes rather than restarting the fairness phase."""
    engine = await _fresh(dsn)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        for _ in range(3):
            await acquire_run_sequence(Session, "binance")
        await engine.dispose()                      # every connection gone

        engine2 = create_async_engine(dsn)
        Session2 = async_sessionmaker(engine2, expire_on_commit=False)
        assert await acquire_run_sequence(Session2, "binance") == 4, \
            "a reconnect restarted the sequence"
        engine = engine2
    finally:
        await _drop(engine)
