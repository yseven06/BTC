"""Run-ownership contract (A3H8), without a database.

The PostgreSQL gate next door proves what the SERVER does. This file proves what
the CODE does: which statement is issued, on which connection, in which order,
and what happens on every exit path. Both are needed — a lock that behaves
perfectly in an integration test but is acquired after the fairness sequence, or
released onto a pooled connection, is still wrong.

The fake connection reads the SQL the implementation actually emitted rather
than trusting it, the same discipline `_Rec` uses for the progression upsert:
a fake that ignores the statement lets the statement be arbitrarily wrong.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys

import pytest

import app.services.ohlcv_collector_job as J
from app.services.ohlcv_progression import (CLAIM_LOCK_NAMESPACE,
                                            RUN_OWNERSHIP_LOCK_NAMESPACE,
                                            select_partition,
                                            source_lock_key,
                                            source_run_ownership)


class _Res:
    def __init__(self, v):
        self._v = v

    def scalar(self):
        return self._v


class _Conn:
    """A connection that answers by reading the SQL, and records every step."""

    def __init__(self, rec, granted=True, visible=True, unlock=True,
                 unlock_raises=None):
        self.rec, self.granted, self.visible = rec, granted, visible
        self.unlock, self.unlock_raises = unlock, unlock_raises

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        self.rec.sql.append((sql, dict(params or {})))
        if "pg_try_advisory_lock" in sql:
            return _Res(self.granted)
        if "pg_advisory_unlock" in sql:
            if self.unlock_raises is not None:
                raise self.unlock_raises
            return _Res(self.unlock)
        if "pg_locks" in sql:
            return _Res(1 if self.visible else 0)
        raise AssertionError(f"unexpected statement on the lock connection: {sql}")

    async def commit(self):
        self.rec.steps.append("commit")

    async def rollback(self):
        self.rec.steps.append("rollback")

    async def close(self):
        self.rec.steps.append("close")

    async def invalidate(self):
        self.rec.steps.append("invalidate")


class _Bind:
    def __init__(self, **kw):
        self.sql: list = []
        self.steps: list = []
        self.kw = kw

    async def connect(self):
        self.steps.append("connect")
        return _Conn(self, **self.kw)


# --- the lock itself ---------------------------------------------------------

@pytest.mark.asyncio
async def test_ownership_is_tried_never_queued():
    """A blocked run must decline. Queuing would stack runs behind a slow one
    and release them together against one cadence and one rate limit."""
    b = _Bind()
    async with source_run_ownership(b, "binance") as owned:
        assert owned is True
    acquires = [s for s, _ in b.sql if "advisory_lock" in s]
    assert acquires and all("pg_try_advisory_lock" in s for s in acquires), \
        f"ownership used a blocking acquire: {acquires}"


@pytest.mark.asyncio
async def test_the_acquire_does_not_leave_a_transaction_open():
    """A session advisory lock outlives its transaction, so the transaction must
    be ended — AFTER the last statement, not before. Ending it early and then
    running the ownership confirmation leaves that confirmation's transaction
    open for the whole run, which is the idle-in-transaction shape this
    codebase has already been bitten by, and it happened once here."""
    b = _Bind()
    async with source_run_ownership(b, "binance"):
        ends = [i for i, s in enumerate(b.steps) if s in ("commit", "rollback")]
        assert ends, "the acquire never ended its transaction"
        stmts = len([1 for s, _ in b.sql])
        assert stmts >= 2, "ownership was never confirmed"
        # every statement issued before yielding must be inside the ended tx
        assert b.steps.index("connect") < ends[-1]
        assert "close" not in b.steps[:ends[-1]], "closed before the tx ended"
    assert b.sql[-1][0].count("pg_advisory_unlock") == 1


@pytest.mark.asyncio
async def test_ownership_is_confirmed_on_the_same_connection():
    """Production reaches PostgreSQL through a pooler. Under a TRANSACTION-mode
    pooler the next statement can land on another backend and the lock would be
    invisible, so ownership is verified before any work is allowed."""
    b = _Bind(visible=False)
    with pytest.raises(RuntimeError, match="could not be confirmed"):
        async with source_run_ownership(b, "binance"):
            pass
    checks = [p for s, p in b.sql if "pg_backend_pid" in s]
    assert checks, "ownership was never confirmed after being taken"
    assert checks[0]["ns"] == RUN_OWNERSHIP_LOCK_NAMESPACE


@pytest.mark.asyncio
async def test_a_declined_acquire_yields_false_and_releases_nothing():
    b = _Bind(granted=False)
    async with source_run_ownership(b, "binance") as owned:
        assert owned is False
    assert not [s for s, _ in b.sql if "pg_advisory_unlock" in s], \
        "a run that never owned the source tried to release it"
    assert "invalidate" not in b.steps, "a declined run poisoned its connection"
    assert b.steps[-1] == "close"


@pytest.mark.asyncio
async def test_ownership_is_released_on_every_exit_path():
    for boom in (None, RuntimeError("collector exploded"), asyncio.CancelledError()):
        b = _Bind()
        try:
            async with source_run_ownership(b, "binance"):
                if boom is not None:
                    raise boom
        except (RuntimeError, asyncio.CancelledError):
            pass
        assert [s for s, _ in b.sql if "pg_advisory_unlock" in s], \
            f"ownership leaked on exit path {boom!r}"
        assert b.steps[-1] == "close"


@pytest.mark.asyncio
async def test_a_connection_that_could_not_be_unlocked_is_invalidated():
    """The decisive cancellation-safety property. A `finally` that merely awaits
    an unlock is not enough: that await can itself be interrupted. Whatever
    happens, the connection must not go back to the pool still owning a source.
    """
    for kw in ({"unlock": False},
               {"unlock_raises": RuntimeError("connection reset")},
               {"unlock_raises": asyncio.CancelledError()}):
        b = _Bind(**kw)
        try:
            async with source_run_ownership(b, "binance"):
                pass
        except BaseException:                       # noqa: BLE001
            pass
        assert "invalidate" in b.steps, \
            f"a still-locked connection was returned to the pool ({kw})"
        assert b.steps.index("invalidate") < b.steps.index("close")


@pytest.mark.asyncio
async def test_a_clean_release_does_not_throw_the_connection_away():
    b = _Bind()
    async with source_run_ownership(b, "binance"):
        pass
    assert "invalidate" not in b.steps, \
        "a cleanly released connection was discarded; that is one handshake per cadence"


# --- the key -----------------------------------------------------------------

def test_the_key_is_stable_across_processes_and_is_not_python_hash():
    """`hash()` is salted per process, so two backends would derive different
    keys and neither would exclude the other — the exact failure this lock
    exists to prevent. Proven by running in real subprocesses with different
    PYTHONHASHSEED values, not by reading the source."""
    import os
    import pathlib
    code = ("import sys; sys.path.insert(0, '.');"
            " from app.services.ohlcv_progression import source_lock_key;"
            " print(source_lock_key('binance'))")
    seen = set()
    for s in ("0", "1", "12345"):
        # Inherit the environment and override ONLY the seed. Handing the child
        # a bare env kills the interpreter outright on Windows, and an empty
        # stdout from three dead subprocesses is "identical" — a green that
        # measures nothing. So the exit status is asserted first.
        r = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True,
            env={**os.environ, "PYTHONHASHSEED": s},
            cwd=str(pathlib.Path(__file__).resolve().parent.parent))
        assert r.returncode == 0, f"seed {s}: child failed: {r.stderr[-300:]}"
        seen.add(r.stdout.strip())
    assert len(seen) == 1, f"the key moved between processes: {seen}"
    assert int(seen.pop()) == source_lock_key("binance")


def test_the_key_is_a_positive_int4_and_source_scoped():
    for s in ("binance", "kraken", "coinbase", "b", "x" * 64):
        k = source_lock_key(s)
        assert 0 <= k <= 0x7FFFFFFF, f"{s} produced {k}, not a positive int4"
    assert source_lock_key("binance") != source_lock_key("kraken"), \
        "two venues would share one run lock"
    assert source_lock_key(" binance ") == source_lock_key("binance")
    with pytest.raises(ValueError):
        source_lock_key("   ")


def test_the_two_lock_classes_live_in_different_namespaces():
    """Measured on PostgreSQL 17: sharing a key makes the CLAIM lock block
    against the run's own RUN lock, because they sit on different connections
    and advisory locks belong to a session. Separation must be explicit, never
    an accidental integer difference."""
    assert RUN_OWNERSHIP_LOCK_NAMESPACE != CLAIM_LOCK_NAMESPACE
    for ns in (RUN_OWNERSHIP_LOCK_NAMESPACE, CLAIM_LOCK_NAMESPACE):
        assert 0 < ns <= 0x7FFFFFFF


@pytest.mark.asyncio
async def test_the_run_lock_uses_the_run_namespace():
    b = _Bind()
    async with source_run_ownership(b, "binance"):
        pass
    for sql, params in b.sql:
        if "advisory" in sql:
            assert params["ns"] == RUN_OWNERSHIP_LOCK_NAMESPACE, sql
            assert params["key"] == source_lock_key("binance")


@pytest.mark.asyncio
async def test_the_claim_takes_its_lock_in_the_claim_namespace_and_first():
    """B1. It must precede the materialise, or the claim is only half serialised."""
    seen: list = []

    class _S:
        async def __aenter__(s):
            return s

        async def __aexit__(s, *e):
            return False

        async def execute(s, stmt, params=None):
            seen.append((" ".join(str(stmt).split()), dict(params or {})))

            class _R:
                def scalars(x):
                    class _T:
                        def all(y):
                            return []
                    return _T()
            return _R()

        async def commit(s):
            return None

    await select_partition(lambda: _S(), "binance", ["AAA", "BBB"], 2, 5)
    assert "pg_advisory_xact_lock" in seen[0][0], \
        f"the claim did not serialise first; it began with {seen[0][0][:60]}"
    assert seen[0][1]["ns"] == CLAIM_LOCK_NAMESPACE, "claim used the run namespace"
    assert seen[0][1]["key"] == source_lock_key("binance")


# --- the run wiring ----------------------------------------------------------

@pytest.mark.asyncio
async def test_a_declined_run_consumes_nothing_and_is_not_a_failure():
    """Phase 9 semantics. A decline is not a fetch failure, not a DB failure and
    not a partial collection — and above all it must not look like a healthy run
    that simply had nothing to do."""
    touched: list = []

    def factory():
        touched.append("session")
        raise AssertionError("a declined run opened a database session")

    class _NeverBuilt:
        def __init__(self, *a, **k):
            raise AssertionError("a declined run constructed a collector")

    real = J.BinanceCollector
    J.BinanceCollector = _NeverBuilt
    try:
        res = await J.run_collection_once(
            factory, ownership=_declined(), source="binance", symbols=["AAA"])
    finally:
        J.BinanceCollector = real

    assert res.ownership_declined is True
    assert res.run_seq == -1, "a declined run burned a durable fairness sequence"
    assert res.symbols_attempted == 0 and res.symbols_partitioned == 0
    assert res.fetch_attempts == 0, "a declined run touched the network"
    assert res.symbols_failed == 0 and res.db_error == 0
    assert res.healthy is True, "a decline was reported as an unhealthy run"
    assert res.as_dict()["ownership_declined"] is True, "the witness hides it"
    assert not touched


def test_the_engine_is_derivable_from_the_factory_production_actually_passes():
    """Production calls `run_collection_once(async_session_factory)` with no
    bind=, so the derivation is the ONLY path that runs live — and every
    integration test above passes bind= explicitly, which would leave exactly
    this path unexercised. `create_async_engine` opens no socket, so this stays
    a database-free test."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    eng = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/none")
    sf = async_sessionmaker(bind=eng, expire_on_commit=False)
    assert J._bind_of(sf) is eng, "the run lock cannot find production's engine"
    assert J._bind_of(sf, "explicit-wins") == "explicit-wins"

    from app.database import async_session_factory
    assert J._bind_of(async_session_factory) is not None, \
        "the real production session factory exposes no bind"


@pytest.mark.asyncio
async def test_a_run_refuses_to_collect_when_ownership_cannot_be_established():
    """No silent bypass. If the bind cannot be found the run does NOT fall
    through to collecting without protection."""
    with pytest.raises(RuntimeError, match="Refusing to collect without ownership"):
        await J.run_collection_once(lambda: None, source="binance")


def test_the_scheduler_entry_point_passes_no_ownership_override():
    """The injection seam exists for tests. Production must take the real lock."""
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent / "app" / "services"
           / "scheduler.py").read_text(encoding="utf-8")
    i = src.index("async def _job_ohlcv_collect")
    body = src[i:src.index("\nasync def ", i + 10) if "\nasync def " in src[i + 10:]
               else i + 1500]
    assert "run_collection_once" in body, "the scheduler stopped using the entry point"
    assert "ownership=" not in body, "the scheduler job overrode run ownership"
    assert "bind=" not in body, "the scheduler job overrode the lock's engine"


from contextlib import asynccontextmanager  # noqa: E402


@asynccontextmanager
async def _declined():
    yield False
