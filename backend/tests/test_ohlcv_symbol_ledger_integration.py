"""Real-PostgreSQL gate for the per-symbol fairness ledger (A3F). OPT-IN.

WHY THIS FILE EXISTS
--------------------
The unit and behavioural tests next door drive the real `select_partition`, but
against a recording fake session: they prove the statements it emits and the
order it asks for. What they cannot prove is what PostgreSQL itself does —
that `FOR UPDATE SKIP LOCKED` genuinely makes two overlapping claims disjoint,
that both construction paths produce the same catalogue object, and that the
CHECKs reject at the database rather than only in a model declaration.

Those properties were previously evidenced only by throwaway operator scripts
run by hand. That is the exact shape of gap this repository has already been
bitten by twice: evidence that lives outside the repository cannot fail a
future refactor. This file moves that evidence into the normal suite.

RUNNING IT
----------
    OHLCV_TEST_DSN=postgresql+asyncpg://user:pw@127.0.0.1:5432/throwaway \\
        pytest -m integration

Without OHLCV_TEST_DSN every test here skips, so the ordinary unit suite never
needs a database.

SAFETY
------
It reads ONE variable and never falls back to DATABASE_URL, because a fallback
is exactly how a "test" ends up pointed at production. If both are set and
equal it FAILS CLOSED rather than skipping — a silent skip would read as a pass.
It creates and drops only `ohlcv_symbol_progress`, and it never prints a DSN.
"""

from __future__ import annotations

import asyncio
import os
import pathlib

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.ohlcv_symbol_progress import OhlcvSymbolProgress as M
from app.services.ohlcv_progression import select_partition

pytestmark = pytest.mark.integration

TABLE = "ohlcv_symbol_progress"
MIGRATION = (pathlib.Path(__file__).resolve().parent.parent
             / "migrations" / "0013_ohlcv_symbol_progress.sql")


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


async def _fresh(dsn, use_migration=False):
    """A disposable ledger table, built by whichever path is under test."""
    engine = create_async_engine(dsn, pool_size=20, max_overflow=20)
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
        if use_migration:
            for stmt in _split(MIGRATION.read_text(encoding="utf-8")):
                await conn.exec_driver_sql(stmt)
        else:
            await conn.run_sync(Base.metadata.create_all, tables=[M.__table__])
    return engine


def _split(sql: str):
    """0013 carries a CREATE TABLE and a CREATE INDEX; asyncpg wants them apart."""
    out, cur = [], []
    for line in sql.splitlines():
        if line.strip().startswith("--"):
            continue
        cur.append(line)
        if line.rstrip().endswith(";"):
            s = "\n".join(cur).strip()
            if s:
                out.append(s)
            cur = []
    return out


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


# ══ CATALOGUE EQUIVALENCE — the 0012 defect class, guarded for 0013 ═════════
@pytest.mark.asyncio
async def test_both_construction_paths_yield_the_same_catalog_object(dsn):
    """`create_all` runs BEFORE the migration, so on a fresh database the MODEL
    builds this table and 0013 is a no-op. 0012 measured what a disagreement
    costs: `character varying` vs `text`, with the CHECK rendering differently in
    each. Comparing names alone would not show it."""
    engine = await _fresh(dsn, use_migration=False)
    async with engine.connect() as conn:
        from_model = await _catalog(conn)
    await engine.dispose()

    engine = await _fresh(dsn, use_migration=True)
    async with engine.connect() as conn:
        from_migration = await _catalog(conn)
    try:
        assert from_model[0] == from_migration[0], (
            f"columns diverge\n model    : {from_model[0]}\n"
            f" migration: {from_migration[0]}")
        assert from_model[1] == from_migration[1], (
            f"constraints diverge\n model    : {from_model[1]}\n"
            f" migration: {from_migration[1]}")
        assert from_model[2] == from_migration[2], (
            f"indexes diverge\n model    : {from_model[2]}\n"
            f" migration: {from_migration[2]}")
    finally:
        await _drop(engine)


@pytest.mark.asyncio
async def test_reapplying_the_migration_is_idempotent(dsn):
    engine = await _fresh(dsn, use_migration=True)
    try:
        async with engine.connect() as conn:
            before = await _catalog(conn)
        async with engine.begin() as conn:
            for stmt in _split(MIGRATION.read_text(encoding="utf-8")):
                await conn.exec_driver_sql(stmt)
        async with engine.connect() as conn:
            assert (await _catalog(conn)) == before, "re-applying 0013 changed the catalogue"
    finally:
        await _drop(engine)


@pytest.mark.asyncio
async def test_the_checks_reject_invalid_rows_in_the_real_database(dsn):
    """Declared in BOTH model and migration; only the database can prove they
    actually reject."""
    engine = await _fresh(dsn, use_migration=True)
    try:
        for values, why in ((("binance", "   ", 0), "blank symbol"),
                            (("binance", "BTCUSDT", -1), "negative run_seq")):
            with pytest.raises(Exception):
                async with engine.begin() as conn:
                    await conn.execute(text(
                        f"INSERT INTO {TABLE}(source,symbol,last_attempt_run_seq) "
                        "VALUES (:s,:y,:n)"),
                        {"s": values[0], "y": values[1], "n": values[2]})
            assert why  # naming the case keeps a failure readable
    finally:
        await _drop(engine)


@pytest.mark.asyncio
async def test_dropping_the_ledger_leaves_neighbouring_ohlcv_state_intact(dsn):
    """Rollback of 0013 must remove ONLY this table. 0011/0012 objects and any
    collected bars are never at risk."""
    engine = await _fresh(dsn, use_migration=True)
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql(
                "CREATE TABLE IF NOT EXISTS a3h_neighbour (id int primary key)")
            await conn.exec_driver_sql("INSERT INTO a3h_neighbour VALUES (1),(2)")
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
            gone = (await conn.execute(text(
                f"SELECT to_regclass('public.{TABLE}') IS NULL"))).scalar()
            kept = (await conn.execute(text("SELECT count(*) FROM a3h_neighbour"))).scalar()
        assert gone is True, "the ledger table survived its own rollback"
        assert kept == 2, "rollback of 0013 removed neighbouring state"
    finally:
        async with engine.begin() as conn:
            await conn.exec_driver_sql("DROP TABLE IF EXISTS a3h_neighbour")
        await _drop(engine)


# ══ THE REAL SELECTOR AGAINST A REAL DATABASE ══════════════════════════════
@pytest.mark.asyncio
async def test_an_empty_ledger_covers_the_universe_in_ceil_n_over_k_runs(dsn):
    """The first-activation shape: no rows at all, run_seq continuing from 0012."""
    engine = await _fresh(dsn, use_migration=True)
    sess = async_sessionmaker(engine, expire_on_commit=False)
    try:
        uni = [f"S{i:03d}" for i in range(13)]
        seen = set()
        for run in range(5, 8):                       # run_seq deliberately not 1
            seen.update(await select_partition(sess, "binance", uni, 5, run))
        assert seen == set(uni), f"covered {len(seen)} of 13 in ceil(13/5)=3 runs"
    finally:
        await _drop(engine)


@pytest.mark.asyncio
async def test_progress_is_durable_across_a_fresh_engine(dsn):
    """A redeploy replaces every in-process object. The ledger must continue,
    not replay the prefix."""
    engine = await _fresh(dsn, use_migration=True)
    uni = [f"S{i:03d}" for i in range(13)]
    try:
        first = await select_partition(
            async_sessionmaker(engine, expire_on_commit=False), "binance", uni, 5, 2)
        await engine.dispose()

        engine = create_async_engine(dsn, pool_size=5, max_overflow=5)
        second = await select_partition(
            async_sessionmaker(engine, expire_on_commit=False), "binance", uni, 5, 3)
        assert not (set(first) & set(second)), (
            f"a fresh engine replayed the previous partition: {sorted(set(first) & set(second))}")
    finally:
        await _drop(engine)


@pytest.mark.asyncio
async def test_sources_keep_independent_queues(dsn):
    engine = await _fresh(dsn, use_migration=True)
    sess = async_sessionmaker(engine, expire_on_commit=False)
    try:
        uni = [f"S{i:03d}" for i in range(13)]
        a = await select_partition(sess, "binance", uni, 5, 2)
        b = await select_partition(sess, "kraken", uni, 5, 2)
        assert a == b, "a second venue inherited binance's position"
        async with engine.connect() as conn:
            for src, n in (("binance", 13), ("kraken", 13)):
                got = (await conn.execute(text(
                    f"SELECT count(*) FROM {TABLE} WHERE source=:s"), {"s": src})).scalar()
                assert got == n, f"{src} has {got} rows, expected {n}"
    finally:
        await _drop(engine)


@pytest.mark.asyncio
async def test_concurrent_claims_are_disjoint_under_skip_locked(dsn):
    """THE property the fake cannot prove. Three simultaneous claimants, each with
    its own run_seq and its own session, must partition the universe rather than
    all reading the same oldest K. Correctness here may not depend on
    APScheduler's max_instances=1 — this primitive stands alone."""
    engine = await _fresh(dsn, use_migration=True)
    sess = async_sessionmaker(engine, expire_on_commit=False)
    try:
        uni = [f"S{i:03d}" for i in range(30)]
        for round_ in range(3):
            async with engine.begin() as conn:
                await conn.exec_driver_sql(f"TRUNCATE {TABLE}")
            base = 10 + round_ * 10
            got = await asyncio.gather(*[
                select_partition(sess, "binance", uni, 5, base + i) for i in range(3)])
            flat = [s for part in got for s in part]
            assert len(flat) == len(set(flat)), (
                f"round {round_}: a symbol was claimed twice: "
                f"{sorted({s for s in flat if flat.count(s) > 1})}")
            # A claimant may legitimately return an EMPTY partition: under the
            # ordering contract a run whose run_seq is not above the rows'
            # tokens has nothing eligible, and returning nothing is correct -
            # far better than backdating the queue. The load-bearing property
            # is disjointness (asserted above), plus never exceeding K.
            assert all(len(p) <= 5 for p in got), f"round {round_}: over K"
            assert any(got), f"round {round_}: every claimant returned nothing"
    finally:
        await _drop(engine)


@pytest.mark.asyncio
async def test_a_claim_advances_only_the_selected_rows(dsn):
    engine = await _fresh(dsn, use_migration=True)
    sess = async_sessionmaker(engine, expire_on_commit=False)
    try:
        uni = [f"S{i:03d}" for i in range(10)]
        picked = await select_partition(sess, "binance", uni, 3, 7)
        async with engine.connect() as conn:
            rows = dict((await conn.execute(text(
                f"SELECT symbol, last_attempt_run_seq FROM {TABLE} "
                "WHERE source='binance'"))).all())
        assert len(rows) == 10, "materialisation did not cover the active universe"
        for s in uni:
            expected = 7 if s in picked else 6      # seed = run_seq - 1
            assert rows[s] == expected, f"{s}: token {rows[s]}, expected {expected}"
    finally:
        await _drop(engine)


# ══ ORDERING: A STALE RUN MUST NOT MAKE ROWS LOOK NEVER-CLAIMED ════════════
@pytest.mark.asyncio
async def test_out_of_order_runs_never_hand_the_same_rows_to_two_claims(dsn):
    """THE A3H5/A3H6 regression, built from a CLEAN ledger by the real code.

    Runs complete out of run_seq order (r+1, then the stale r, then r+2) — the
    reachable case when two runs overlap. On the pristine implementation the
    stale run wrote its own run_seq onto rows already sitting at that exact
    value (the seed left by r+1 is r+1-1 = r), so its claim made NO ordering
    progress: the rows stayed tied with never-claimed rows and r+2 selected them
    again. Measured: stale r -> S005..S009, then r+2 -> S005..S009.

    A claim must never leave a row looking as unclaimed as it was before.
    """
    engine = await _fresh(dsn, use_migration=True)
    sess = async_sessionmaker(engine, expire_on_commit=False)
    try:
        uni = [f"S{i:03d}" for i in range(20)]
        r = 10000
        first = await select_partition(sess, "binance", uni, 5, r + 1)
        stale = await select_partition(sess, "binance", uni, 5, r)
        nxt = await select_partition(sess, "binance", uni, 5, r + 2)
        assert not (set(stale) & set(nxt)), (
            f"a stale run's partition was handed out again: "
            f"stale={sorted(stale)} next={sorted(nxt)}")
        assert not (set(first) & set(nxt)), (
            f"r+1 and r+2 overlap: {sorted(set(first) & set(nxt))}")
    finally:
        await _drop(engine)


@pytest.mark.asyncio
async def test_a_claim_never_decreases_a_stored_token(dsn):
    """Token monotonicity as a first-class invariant, over every regime."""
    engine = await _fresh(dsn, use_migration=True)
    sess = async_sessionmaker(engine, expire_on_commit=False)
    try:
        uni = [f"S{i:03d}" for i in range(12)]
        for initial, seqs in ((None, [5, 6, 7]),        # empty ledger
                              (9000, [10000, 10001]),   # below existing
                              (40000, [10000, 10001]),  # above existing
                              (15000, [10000, 20000])): # straddling
            async with engine.begin() as c:
                await c.execute(text(f"TRUNCATE {TABLE}"))
                if initial is not None:
                    for s in uni:
                        await c.execute(text(
                            f"INSERT INTO {TABLE}(source,symbol,last_attempt_run_seq)"
                            " VALUES ('binance',:s,:t)"), {"s": s, "t": initial})
            before = {}
            async with engine.connect() as c:
                before = dict((await c.execute(text(
                    f"SELECT symbol,last_attempt_run_seq FROM {TABLE}"
                    " WHERE source='binance'"))).all())
            for q in seqs:
                await select_partition(sess, "binance", uni, 5, q)
                async with engine.connect() as c:
                    after = dict((await c.execute(text(
                        f"SELECT symbol,last_attempt_run_seq FROM {TABLE}"
                        " WHERE source='binance'"))).all())
                for s, v in after.items():
                    if s in before:
                        assert v >= before[s], (
                            f"initial={initial} run_seq={q}: {s} went "
                            f"{before[s]} -> {v}")
                before = after
    finally:
        await _drop(engine)
