"""CP-OHLCV-A3c — the durable progression primitive. Still dormant.

The counter means exactly one thing: "a collection run for this source has
STARTED". These tests pin that meaning, the point at which it becomes durable,
and the two structural traps around it — the `create_all` bypass and the
lost-update race.
"""

from __future__ import annotations

import ast
import asyncio
from contextlib import asynccontextmanager
import inspect
import pathlib
import re
from datetime import datetime, timezone

import pytest
from sqlalchemy import func
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.schema import CreateTable

from app.models.ohlcv_progress import OhlcvCollectionProgress as M
from app.services import ohlcv_collector_job as J
from app.services.ohlcv_collector_job import acquire_run_sequence

BACKEND = pathlib.Path(__file__).resolve().parent.parent
MIGRATION = BACKEND / "migrations" / "0012_ohlcv_progression.sql"


# ══ THE create_all TRAP ════════════════════════════════════════════════════
@asynccontextmanager
async def _granted():
    """Run-ownership stub. These are DB-free tests, and about something else.

    `run_collection_once` refuses to collect without source ownership, and real
    ownership needs a real connection. Injecting a granted stub keeps that
    refusal intact for production while letting these tests go on asserting
    exactly what they always asserted.
    """
    yield True


def test_model_ddl_and_migration_ddl_agree_on_every_correctness_constraint():
    """THE REPO-WIDE TRAP. `scripts/migrate.py` runs `Base.metadata.create_all`
    BEFORE the pending .sql files, so on a fresh database the MODEL creates this
    table and the migration's CREATE TABLE is a silent no-op. A constraint written
    only in SQL would never reach such a database while the ledger still recorded
    the migration as applied — which is exactly how 0011 lost four CHECKs."""
    ddl = str(CreateTable(M.__table__).compile(dialect=postgresql.dialect())).lower()
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    for constraint in ("primary key", "run_seq >= 0", "length(btrim(source)) > 0"):
        assert constraint in ddl, f"{constraint!r} missing from the MODEL"
        assert constraint in sql, f"{constraint!r} missing from the MIGRATION"


def test_the_migration_is_additive_and_touches_no_ohlcv_data():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    body = "\n".join(ln for ln in sql.splitlines() if not ln.strip().startswith("--"))
    for forbidden in ("drop table ohlcv_bars", "alter table ohlcv_bars",
                      "delete from", "update ohlcv_bars", "truncate"):
        assert forbidden not in body, f"migration is not additive: {forbidden}"
    assert "create table if not exists ohlcv_collection_progress" in body


def test_the_migration_number_is_next_and_0011_is_untouched():
    names = sorted(p.name for p in (BACKEND / "migrations").glob("*.sql"))
    # A3F adds 0013 (the per-symbol ledger). 0012 must still be present and
    # 0013 must be the newest — the guard pins ORDER and non-destruction, not a
    # frozen highest number, which is what made it expire the moment a
    # legitimate migration landed.
    assert names[-1].startswith("0013_"), names[-1]
    assert any(n.startswith("0012_") for n in names), "0012 must still exist"
    assert any(n.startswith("0011_") for n in names), "0011 must still exist"


# ══ THE STATEMENT: ATOMIC, NOT READ-MODIFY-WRITE ═══════════════════════════
@pytest.mark.asyncio
async def test_the_advance_emits_a_single_upsert_with_returning():
    """THE SQL THE IMPLEMENTATION ACTUALLY EMITS — not a look-alike.

    This test used to build its own statement and assert things about that, which
    proved only that SQLAlchemy works. It never called `acquire_run_sequence`, so
    the production statement could be anything. It is now captured from the real
    call, which is what makes the assertions below bite.
    """
    captured: list = []

    class _Capture:
        async def __aenter__(s):
            return s

        async def __aexit__(s, *e):
            return False

        async def execute(s, stmt, *a, **k):
            captured.append(stmt.compile(dialect=postgresql.dialect()))

            class _R:
                def scalar_one(x):
                    return 1
            return _R()

        async def commit(s):
            return None

        async def rollback(s):
            return None

    await acquire_run_sequence(lambda: _Capture(), "binance")
    assert len(captured) == 1, "the advance must be exactly ONE statement"
    sql = str(captured[0]).lower()
    assert "insert into ohlcv_collection_progress" in sql
    assert "on conflict (source) do update" in sql, "conflict target is not `source`"
    assert "run_seq = (ohlcv_collection_progress.run_seq +" in sql, \
        "the increment is not derived from the stored value — lost-update race"
    assert "returning ohlcv_collection_progress.run_seq" in sql, \
        "RETURNING must yield the durable run_seq, not another column"
    assert "select" not in sql.split("insert into", 1)[1], "read-modify-write"


def test_the_implementation_does_not_read_then_write():
    """Static guard: a `select(...)` inside the advance would mean the increment
    was computed in Python, i.e. a race."""
    src = inspect.getsource(acquire_run_sequence)
    tree = ast.parse(src.lstrip())
    calls = {getattr(n.func, "id", None) or getattr(n.func, "attr", None)
             for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert "select" not in calls, "the advance performs a read-modify-write"
    assert "on_conflict_do_update" in calls
    assert "returning" in calls


def test_the_advance_holds_no_transaction_across_network_io():
    """The session is opened, the statement runs, it commits — and nothing in the
    body reaches the collector or the exchange. The pool ceiling is 10 and a
    transaction held across a Binance request is the idle-in-transaction shape
    this codebase has already been bitten by."""
    tree = ast.parse(inspect.getsource(acquire_run_sequence).lstrip())
    fn = tree.body[0]
    # The docstring explains WHY none of these may appear; matching prose instead
    # of code is how a guard becomes decorative, so strip it and read the body.
    body = fn.body[1:] if (fn.body and isinstance(fn.body[0], ast.Expr)
                           and isinstance(fn.body[0].value, ast.Constant)) else fn.body
    names = set()
    for node in body:
        for n in ast.walk(node):
            names |= {getattr(n, "id", None), getattr(n, "attr", None)}
    for forbidden in ("fetch_ohlcv", "collector", "sleep", "httpx",
                      "collect_once", "collect_and_persist"):
        assert forbidden not in names, f"{forbidden} inside the progression transaction"


# ══ THE ADVANCE POINT — LOAD-BEARING ═══════════════════════════════════════
class _Rec:
    """A STATEMENT-SENSITIVE fake PostgreSQL.

    WHY IT IS BUILT THIS WAY. The previous version ignored the statement entirely
    and returned its own counter, so the production SQL could be arbitrarily wrong
    while every test stayed green — a sabotage review proved exactly that by
    replacing `run_seq + 1` with the constant `1`, swapping the RETURNING column,
    and re-pointing the source bind, all three of which survived.

    So this fake does not guess. It compiles the statement the implementation
    actually emitted, reads the source bind, the ON CONFLICT increment and the
    RETURNING column out of that SQL, and applies them to a tiny in-memory table.
    Break any of those three and the values these tests observe change.
    """

    def __init__(self, fail=False, start=0):
        self.fail = fail
        self.events: list = []
        self.rows: dict = {}          # source -> run_seq, i.e. the "table"
        self.sources: list = []       # every source bind the implementation used
        self.returning: list = []     # every RETURNING column it asked for
        self.conflict_targets: list = []

    def factory(self):
        rec = self

        class _S:
            async def __aenter__(s):
                return s

            async def __aexit__(s, *e):
                return False

            async def execute(s, stmt, *a, **k):
                rec.events.append("progression_execute")
                if rec.fail:
                    raise RuntimeError("database unavailable")

                compiled = stmt.compile(dialect=postgresql.dialect())
                sql = str(compiled)
                params = compiled.params
                src = params.get("source")
                rec.sources.append(src)

                m = re.search(r"RETURNING ohlcv_collection_progress\.(\w+)", sql)
                col = m.group(1) if m else None
                rec.returning.append(col)
                ct = re.search(r"ON CONFLICT \((\w+)\) DO UPDATE", sql)
                rec.conflict_targets.append(ct.group(1) if ct else None)

                do_update = sql.split("DO UPDATE SET", 1)[1] if "DO UPDATE SET" in sql else ""
                inc = re.search(
                    r"run_seq\s*=\s*\(ohlcv_collection_progress\.run_seq \+ %\((\w+)\)s\)",
                    do_update)
                const = re.search(r"run_seq\s*=\s*%\((\w+)\)s", do_update)

                if src not in rec.rows:                       # the INSERT branch
                    rec.rows[src] = params.get("run_seq")
                elif inc:                                     # run_seq = run_seq + N
                    rec.rows[src] = rec.rows[src] + params[inc.group(1)]
                elif const:                                   # run_seq = <constant>
                    rec.rows[src] = params[const.group(1)]
                else:
                    rec.rows[src] = rec.rows[src]             # no update at all

                value = rec.rows[src] if col == "run_seq" else _SENTINEL_TS

                class _R:
                    def scalar_one(x):
                        return value
                return _R()

            async def commit(s):
                rec.events.append("progression_commit")

            async def rollback(s):
                return None
        return _S()


_SENTINEL_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_the_sequence_is_durable_before_it_is_returned():
    rec = _Rec()
    seq = await acquire_run_sequence(rec.factory, "binance")
    assert seq == 1
    assert rec.events == ["progression_execute", "progression_commit"], \
        "the value was returned without committing"


@pytest.mark.asyncio
async def test_consecutive_runs_receive_consecutive_values():
    """The values come from applying the EMITTED SQL to a table, so a constant
    increment or a swapped RETURNING column changes what this observes."""
    rec = _Rec()
    got = [await acquire_run_sequence(rec.factory, "binance") for _ in range(5)]
    assert got == [1, 2, 3, 4, 5], f"sequence is not monotonic by one: {got}"
    assert all(isinstance(v, int) for v in got), \
        "a non-integer came back — RETURNING is not run_seq"


@pytest.mark.asyncio
async def test_the_returned_value_is_the_persisted_value():
    rec = _Rec()
    got = [await acquire_run_sequence(rec.factory, "binance") for _ in range(4)]
    assert got[-1] == rec.rows["binance"], \
        "the caller received something other than the stored run_seq"
    assert rec.returning == ["run_seq"] * 4
    assert rec.conflict_targets == ["source"] * 4


@pytest.mark.asyncio
async def test_each_source_keeps_its_own_row():
    rec = _Rec()
    a = [await acquire_run_sequence(rec.factory, "binance") for _ in range(3)]
    b = [await acquire_run_sequence(rec.factory, "kraken") for _ in range(2)]
    assert a == [1, 2, 3] and b == [1, 2], "sources shared a sequence"
    assert rec.rows == {"binance": 3, "kraken": 2}


@pytest.mark.asyncio
async def test_the_run_acquires_under_ITS_OWN_source():
    """S11: a kraken run must not advance binance's progression. The source the
    run collects for and the source it claims progression under are the same
    value, and this asserts it end to end through `run_collection_once`."""
    rec = _Rec()

    class _Col:
        async def fetch_ohlcv(self, *a, **k):
            raise RuntimeError("no network in this test")

        async def close(self):
            return None

    import app.services.ohlcv_collector_job as mod
    real = mod.BinanceCollector
    mod.BinanceCollector = _Col
    try:
        await J.run_collection_once(rec.factory, ownership=_granted(), symbols=[], timeframes=["15m"],
                                    source="kraken")
    finally:
        mod.BinanceCollector = real
    assert rec.sources == ["kraken"], \
        f"progression was claimed under {rec.sources}, not the run's source"
    assert "binance" not in rec.rows


@pytest.mark.asyncio
async def test_a_database_failure_is_not_swallowed():
    """If progression cannot become durable the run must NOT pretend it did."""
    rec = _Rec(fail=True)
    with pytest.raises(RuntimeError):
        await acquire_run_sequence(rec.factory, "binance")
    assert "progression_commit" not in rec.events


@pytest.mark.asyncio
async def test_an_empty_source_is_refused():
    rec = _Rec()
    for bad in ("", "   ", None):
        with pytest.raises(ValueError, match="source"):
            await acquire_run_sequence(rec.factory, bad)
    assert rec.events == [], "a refused source must not touch the database"


@pytest.mark.asyncio
async def test_the_run_entry_point_claims_the_sequence_before_the_first_item():
    """THE POINT OF THE WHOLE CHECKPOINT. Advancing only on completion let a run
    that always died early replay the same prefix forever — measured 2 of 57
    symbols over 200 runs, against 57 of 57 when advancing at the start."""
    order: list = []

    class Col:
        async def fetch_ohlcv(self, symbol, timeframe, limit=500, end_time_ms=None):
            order.append(("item", symbol, timeframe))
            raise RuntimeError("stop after proving the ordering")

    class Sess:
        async def __aenter__(s):
            return s

        async def __aexit__(s, *e):
            return False

        def begin_nested(s):
            class _SP:
                async def __aenter__(x):
                    return x

                async def __aexit__(x, *e):
                    return False
            return _SP()

        async def execute(s, stmt, *a, **k):
            text = str(getattr(stmt, "compile", lambda **k: stmt)()).lower()
            if "ohlcv_collection_progress" in text:
                order.append(("progression",))

                class _R:
                    def scalar_one(x):
                        return 7
                return _R()

            class _R2:
                rowcount = 1

                def all(x):
                    return []

                def scalars(x):
                    class _S2:
                        def all(y):
                            return []
                    return _S2()
            return _R2()

        async def commit(s):
            return None

        async def rollback(s):
            return None

    import app.services.ohlcv_collector_job as mod
    real = mod.BinanceCollector
    mod.BinanceCollector = Col                     # own-and-close path, no socket
    try:
        res = await J.run_collection_once(lambda: Sess(), ownership=_granted(), symbols=["AAA", "BBB"],
                                          timeframes=["15m"], spacing=0,
                                          item_budget=0.05)
    finally:
        mod.BinanceCollector = real
    assert order, "nothing ran"
    assert order[0] == ("progression",), \
        f"the first database work was not the progression claim: {order[0]}"
    assert res.run_seq == 7
    # rotation_offset is SUPERSEDED by the symbol-space partition (A3F) and is no
    # longer the traversal selector, so it stays 0. The claim-before-first-item
    # ordering asserted above is what this test was actually written to protect,
    # and that is unchanged.
    assert res.rotation_offset == 0
    # An explicit `symbols=` list is an instruction, not a universe, so it is
    # never partitioned - the durable partition governs discovery only.
    assert res.symbols_partitioned == 0


@pytest.mark.asyncio
async def test_an_injected_sequence_is_used_verbatim_and_claims_nothing():
    """Tests inject a sequence; that path must not silently claim a new one."""
    touched: list = []

    class Sess:
        async def __aenter__(s):
            return s

        async def __aexit__(s, *e):
            return False

        async def execute(s, stmt, *a, **k):
            text = str(stmt).lower()
            if "ohlcv_collection_progress" in text:
                touched.append("claimed")

            class _R:
                rowcount = 1

                def all(x):
                    return []

                def scalars(x):
                    class _S2:
                        def all(y):
                            return []
                    return _S2()
            return _R()

        async def commit(s):
            return None

        async def rollback(s):
            return None

    res = J.CollectionResult()
    await J.collect_once(lambda: Sess(), object(), symbols=[], timeframes=["15m"],
                         spacing=0, run_seq=41, result=res)
    assert res.run_seq == 41
    assert touched == []


# ══ MEANING — WHAT IT MUST NOT CLAIM ═══════════════════════════════════════
def test_the_counter_carries_no_coverage_information():
    """A3/A4 boundary: this value must never be able to answer an A4 question."""
    cols = set(M.__table__.columns.keys())
    assert cols == {"source", "run_seq", "updated_at"}, cols
    for forbidden in ("open_time", "watermark", "coverage", "last_bar", "gap",
                      "backfill", "symbol", "timeframe"):
        assert not any(forbidden in c for c in cols), f"{forbidden} leaked in"


def test_progression_is_per_source_not_global():
    assert list(M.__table__.primary_key.columns.keys()) == ["source"]


def test_the_source_key_is_not_nullable_in_the_emitted_ddl():
    """S16: declaring the key column nullable changes the DDL create_all emits.
    Asserted against the compiled DDL rather than the attribute, because the DDL
    is what actually reaches the database."""
    col = M.__table__.c.source
    assert col.primary_key is True
    assert col.nullable is False, "the progression key became nullable"
    ddl = str(CreateTable(M.__table__).compile(dialect=postgresql.dialect()))
    src_line = [ln for ln in ddl.splitlines() if ln.strip().startswith("source ")]
    assert src_line, ddl
    assert "NOT NULL" in src_line[0], f"source is not NOT NULL in DDL: {src_line[0]}"


def test_the_migration_declares_the_same_key_shape():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    body = " ".join(l for l in sql.splitlines() if not l.strip().startswith("--"))
    assert "source" in body and "not null" in body
    assert "primary key (source)" in body, "migration lost the source primary key"


@pytest.mark.asyncio
async def test_two_sources_do_not_share_a_sequence():
    seqs = {}

    def factory_for(src):
        def make():
            class _S:
                async def __aenter__(s):
                    return s

                async def __aexit__(s, *e):
                    return False

                async def execute(s, stmt, *a, **k):
                    seqs[src] = seqs.get(src, 0) + 1

                    class _R:
                        def scalar_one(x):
                            return seqs[src]
                    return _R()

                async def commit(s):
                    return None

                async def rollback(s):
                    return None
            return _S()
        return make

    a1 = await acquire_run_sequence(factory_for("binance"), "binance")
    b1 = await acquire_run_sequence(factory_for("kraken"), "kraken")
    a2 = await acquire_run_sequence(factory_for("binance"), "binance")
    assert (a1, a2) == (1, 2) and b1 == 1, "sources shared a sequence"
