"""CP-OHLCV-A2 — the closed-bar writer. Dormant, isolated, per-row safe.

Two things this file is careful about.

FIRST, the writer must be provably ASLEEP. It ships with no scheduler job, no
startup hook and no flag; importing it does nothing. T33-T35 pin that.

SECOND, several of the properties that matter can only be proven against a real
PostgreSQL — savepoint rollback, ON CONFLICT, CHECK rejection, session
usability after a rejected row. Those are NOT faked here. The fake-session tests
below cover call shape and counter semantics; the database behaviour was proven
separately against the exact production DDL in an isolated PostgreSQL 16, and
the numbers are quoted where they matter. A fake that asserts its own conclusion
would be worse than no test, so this file does not pretend otherwise.
"""

from __future__ import annotations

import ast
import asyncio
import math
import pathlib
import re
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from app.services import ohlcv_writer as W
from app.services.ohlcv_writer import (BarCandidate, WriteResult, eligible_bars,
                                       fetch_bars_bounded, normalise_symbol,
                                       normalise_timeframe, persist_bars,
                                       validate_bar)

BACKEND = pathlib.Path(__file__).resolve().parent.parent
UTC = timezone.utc
T0 = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
STEP = timedelta(minutes=15)


def frame(n=5, *, tf="15m", start=T0, high=110.0, low=90.0, open_=100.0,
          close=100.0, volume=10.0, close_time=True, dur=None):
    dur = dur if dur is not None else STEP
    idx = pd.DatetimeIndex([start + i * STEP for i in range(n)], tz=UTC)
    data = {
        "open": np.full(n, open_), "high": np.full(n, high),
        "low": np.full(n, low), "close": np.full(n, close),
        "volume": np.full(n, volume),
    }
    df = pd.DataFrame(data, index=idx)
    if close_time:
        df["close_time"] = [t + dur for t in idx]
    return df


def cand(**kw):
    base = dict(source="binance", symbol="BTCUSDT", timeframe="15m",
                open_time=T0, close_time=T0 + STEP, open=100.0, high=110.0,
                low=90.0, close=100.0, volume=10.0)
    base.update(kw)
    return BarCandidate(**base)


def insert_sources(stmt):
    """The `source` value of every row an INSERT carries, in row order.

    The writer produces TWO statement shapes and this must read both: the batch
    path builds `.values([row, row, ...])`, which compiles one bind per row
    (`source_m0`, `source_m1`, ...), while the per-row fallback builds
    `.values(**row)`, which compiles the column name bare. Returning the list —
    rather than one value — is what lets a caller assert both HOW MANY rows a
    statement carried and WHAT source each was stamped with.
    """
    try:
        params = stmt.compile().params
    except Exception:                      # noqa: BLE001 — non-Core stmt
        return []
    if "source" in params:
        return [params["source"]]
    # Sort by the numeric suffix, never lexicographically: `source_m10` must not
    # sort before `source_m2`.
    keys = [k for k in params if k.startswith("source_m")]
    keys.sort(key=lambda k: int(k[len("source_m"):]))
    return [params[k] for k in keys]


def insert_row_count(stmt):
    """How many rows this INSERT would write into an empty table."""
    return len(insert_sources(stmt))


# A session that records calls and can reject chosen rows, WITHOUT claiming to
# reproduce PostgreSQL semantics.
class FakeSession:
    def __init__(self, reject_when=None, rowcounts=None):
        self.calls, self.savepoints, self.commits, self.rollbacks = [], 0, 0, 0
        self.open_savepoints = 0
        self._reject = reject_when or (lambda stmt: False)
        self._rowcounts = list(rowcounts or [])

    def begin_nested(self):
        outer = self

        class _SP:
            async def __aenter__(self_):
                outer.savepoints += 1
                outer.open_savepoints += 1
                return self_

            async def __aexit__(self_, et, e, tb):
                outer.open_savepoints -= 1
                return False           # never swallow
        return _SP()

    async def execute(self, stmt, *a, **k):
        assert self.open_savepoints > 0, "every INSERT must sit inside a savepoint"
        self.calls.append(stmt)
        if self._reject(stmt):
            raise _IntegrityError("CheckViolation")

        # DEFAULT ROWCOUNT IS DERIVED FROM THE STATEMENT, never hardcoded to 1.
        # A fixed 1 would report `persisted=1` for a 500-row batch, which makes
        # every persisted/duplicate assertion in this file vacuous — the exact
        # accounting the batch path has to get right. An explicit `rowcounts`
        # script still wins, so a test can still stage a partial conflict.
        n = insert_row_count(stmt)

        class _R:
            rowcount = self._rowcounts.pop(0) if self._rowcounts else n
        return _R()

    async def commit(self):      # pragma: no cover — must never be reached
        self.commits += 1

    async def rollback(self):    # pragma: no cover
        self.rollbacks += 1


class _IntegrityError(Exception):
    pass


# ── T1/T15 · validation contract ─────────────────────────────────────────────
def test_T1_a_valid_closed_candle_validates():
    assert validate_bar(cand()) is None


@pytest.mark.parametrize("kw,reason", [
    ({"high": 90.0, "low": 100.0}, "low_above_high"),                    # T7
    ({"open": 50.0}, "open_outside_bounds"),                             # T8
    ({"open": 500.0}, "open_outside_bounds"),                            # T9
    ({"close": 50.0}, "close_outside_bounds"),                           # T10
    ({"close": 500.0}, "close_outside_bounds"),                          # T11
    ({"volume": -1.0}, "negative_volume"),                               # T12
    ({"close_time": T0}, "close_time_not_after_open_time"),              # T13
    ({"close_time": T0 - STEP}, "close_time_not_after_open_time"),       # T14
    ({"symbol": ""}, "missing_symbol"),
    ({"volume": float("nan")}, "non_finite_volume"),
    ({"high": float("inf")}, "non_finite_high"),
])
def test_T7_T14_every_db_check_is_mirrored(kw, reason):
    assert validate_bar(cand(**kw)) == reason


def test_T15_zero_volume_is_valid():
    """A quiet minute is real market data and the schema permits it."""
    assert validate_bar(cand(volume=0.0)) is None


def test_the_validator_covers_every_check_the_schema_declares():
    """If a future migration adds a CHECK, this fails until it is mirrored."""
    from app.models.ohlcv_bar import OhlcvBar
    from sqlalchemy import CheckConstraint
    names = {c.name for c in OhlcvBar.__table__.constraints
             if isinstance(c, CheckConstraint)}
    assert names == {"ck_ohlcv_bars_bounds", "ck_ohlcv_bars_volume",
                     "ck_ohlcv_bars_window", "ck_ohlcv_bars_closed"}, names
    # bounds/volume/window are mirrored above; `closed` is enforced structurally
    # by eligible_bars, which is the only producer of BarCandidate.
    src = (BACKEND / "app" / "services" / "ohlcv_writer.py").read_text(encoding="utf-8")
    for needle in ("low_above_high", "open_outside_bounds", "close_outside_bounds",
                   "negative_volume", "close_time_not_after_open_time"):
        assert needle in src


# ── T3/T4/T5/T6 · closure ────────────────────────────────────────────────────
def test_T3_the_newest_bar_is_never_eligible():
    """The structural gate. Binance returns the forming bar last, so dropping
    the newest excludes it WITHOUT consulting any clock."""
    df = frame(5)
    got, res = eligible_bars(df, "BTCUSDT", "15m", now=T0 + 100 * STEP)
    assert len(got) == 4
    assert res.forming_or_not_closed == 1
    assert max(c.open_time for c in got) == T0 + 3 * STEP


def test_T4_a_future_close_time_is_not_eligible():
    df = frame(5)
    # `now` sits inside bar 2, so bars 2..4 have not closed
    got, res = eligible_bars(df, "BTCUSDT", "15m", now=T0 + 2 * STEP + timedelta(minutes=1))
    assert [c.open_time for c in got] == [T0, T0 + STEP]
    assert res.forming_or_not_closed == 3


def test_T5_the_threshold_boundary_is_documented_and_inclusive():
    """close_time == threshold is ADMITTED: Binance's close_time is the bar's
    last millisecond, so equality means the bar has ended."""
    df = frame(3)
    exact = T0 + 2 * STEP                      # == close_time of bar index 1
    got, _ = eligible_bars(df, "BTCUSDT", "15m", now=exact)
    assert [c.open_time for c in got] == [T0, T0 + STEP]


def test_T5b_a_margin_shifts_the_boundary_and_never_admits_more():
    df = frame(5)
    now = T0 + 100 * STEP
    wide, _ = eligible_bars(df, "BTCUSDT", "15m", now=now)
    tight, _ = eligible_bars(df, "BTCUSDT", "15m", now=now, margin=timedelta(days=365))
    assert len(tight) == 0 and len(wide) == 4


def test_T6_an_unknown_timeframe_fails_safely_before_any_work():
    with pytest.raises(ValueError):
        eligible_bars(frame(3), "BTCUSDT", "30m", now=T0 + 100 * STEP)
    with pytest.raises(ValueError):
        normalise_timeframe("30m")


def test_the_exchange_close_time_is_preferred_over_a_derived_one():
    df = frame(4)
    df["close_time"] = [t + timedelta(hours=99) for t in df.index]   # far future
    got, res = eligible_bars(df, "BTCUSDT", "15m", now=T0 + 10 * STEP)
    assert got == [] and res.forming_or_not_closed == 4, (
        "a derived close_time would have admitted these; the exchange value must win")


def test_a_frame_without_close_time_falls_back_to_open_plus_duration():
    df = frame(4, close_time=False)
    got, _ = eligible_bars(df, "BTCUSDT", "15m", now=T0 + 100 * STEP)
    assert len(got) == 3
    assert all(c.close_time == c.open_time + STEP for c in got)


def test_out_of_order_and_duplicate_rows_are_normalised_before_the_cut():
    df = frame(5).iloc[::-1]
    df = pd.concat([df, df.iloc[:1]])
    got, _ = eligible_bars(df, "BTCUSDT", "15m", now=T0 + 100 * STEP)
    times = [c.open_time for c in got]
    assert times == sorted(times) and len(set(times)) == len(times)


def test_T23b_normalisation_is_deterministic():
    assert normalise_symbol("btc/usdt") == "BTCUSDT" == normalise_symbol("BTCUSDT")
    assert normalise_timeframe(" 15M ") == "15m"
    got, _ = eligible_bars(frame(3), "btc/usdt", "15M", now=T0 + 100 * STEP)
    assert all(c.symbol == "BTCUSDT" and c.timeframe == "15m" for c in got)


def test_invalid_bars_are_classified_not_silently_dropped():
    df = frame(4, high=90.0, low=100.0)
    got, res = eligible_bars(df, "BTCUSDT", "15m", now=T0 + 100 * STEP)
    assert got == []
    assert res.invalid == 3 and res.invalid_reasons == {"low_above_high": 3}


# ── T24-T27 · bounded fetch ──────────────────────────────────────────────────
class Collector:
    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.calls = 0

    async def fetch_ohlcv(self, symbol, timeframe, limit=100, end_time_ms=None):
        self.calls += 1
        b = self.behaviour(self.calls) if callable(self.behaviour) else self.behaviour
        if b == "ok":
            return frame(3)
        if b == "hang":
            await asyncio.sleep(3600)
        raise ConnectionError("boom")


@pytest.mark.asyncio
async def test_T24_a_hard_timeout_bites():
    res = WriteResult()
    df, kind = await asyncio.wait_for(
        fetch_bars_bounded(Collector("hang"), "BTCUSDT", "15m",
                           timeout=0.05, retries=0, result=res), timeout=5.0)
    assert df is None and kind == "fetch_timeout"
    assert res.fetch_timeout == 1 and res.retry_exhausted == 1
    assert res.fetch_error == 0, "a stall must not be filed as a generic error"


@pytest.mark.asyncio
async def test_T25_a_retry_that_succeeds_is_classified_as_recovered():
    res = WriteResult()
    col = Collector(lambda n: "err" if n == 1 else "ok")
    df, kind = await fetch_bars_bounded(col, "BTCUSDT", "15m", retries=2, result=res)
    assert kind == "fetch_success" and df is not None and col.calls == 2
    assert res.retry_recovered == 1 and res.fetch_error == 1
    assert res.retry_exhausted == 0


@pytest.mark.asyncio
async def test_T26_retry_exhaustion_is_classified():
    res = WriteResult()
    col = Collector("err")
    df, kind = await fetch_bars_bounded(col, "BTCUSDT", "15m", retries=2, result=res)
    assert df is None and kind == "fetch_error" and col.calls == 3
    assert res.fetch_error == 3 and res.retry_exhausted == 1


@pytest.mark.asyncio
async def test_T27_a_malformed_response_is_classified_not_persisted():
    df = frame(4).drop(columns=["high"])
    got, res = eligible_bars(df, "BTCUSDT", "15m", now=T0 + 100 * STEP)
    assert got == [] and res.malformed_response == 3


# ── T2/T16-T22/T28-T32 · persistence shape ───────────────────────────────────
@pytest.mark.asyncio
async def test_T18_a_healthy_page_is_ONE_batch_inside_ONE_savepoint():
    """The healthy path must not scale with the number of bars.

    Per-row savepoints cost three round trips per bar, which is free locally and
    ruinous against a remote pooler: 159 bars measured 477 round trips / 120 s at
    a real 129 ms RTT, against 3 round trips / 0.94 s for this shape. The
    savepoint is still here — one, around the whole page, so a rejection cannot
    reach the caller's transaction.
    """
    db = FakeSession()
    res = await persist_bars(db, [cand(open_time=T0 + i * STEP) for i in range(4)])
    assert db.savepoints == 1, "one savepoint per PAGE on the healthy path"
    assert len(db.calls) == 1, "one INSERT, not one per row"
    assert insert_row_count(db.calls[0]) == 4, "all four rows in that INSERT"
    assert res.persisted == 4 and db.open_savepoints == 0


@pytest.mark.asyncio
async def test_the_batch_is_never_chunked_however_large_the_page():
    """500 is the largest page `limit=500` can produce and was measured safe as
    one statement. Splitting it would add round trips to buy nothing."""
    db = FakeSession()
    res = await persist_bars(db, [cand(open_time=T0 + i * STEP) for i in range(500)])
    assert len(db.calls) == 1 and db.savepoints == 1
    assert insert_row_count(db.calls[0]) == 500
    assert res.persisted == 500 and res.duplicate == 0


@pytest.mark.asyncio
async def test_T2_a_duplicate_is_an_explicit_no_op_not_an_insert():
    """ON CONFLICT DO NOTHING reports only what it WROTE, so the duplicates are
    the difference. Scripted here as 2 of 3 rows written."""
    db = FakeSession(rowcounts=[2])
    res = await persist_bars(db, [cand(open_time=T0 + i * STEP) for i in range(3)])
    assert res.persisted == 2 and res.duplicate == 1 and res.db_rejected == 0


@pytest.mark.asyncio
async def test_a_page_that_is_entirely_duplicates_persists_nothing():
    db = FakeSession(rowcounts=[0])
    res = await persist_bars(db, [cand(open_time=T0 + i * STEP) for i in range(9)])
    assert res.persisted == 0 and res.duplicate == 9
    assert res.db_rejected == 0 and res.db_error == 0


@pytest.mark.asyncio
async def test_T16_T17_a_rejected_row_does_not_take_its_siblings():
    """Fake-session shape check. The REAL isolation was measured on PostgreSQL:
    per-row savepoints kept 7/7 where the single-batch INSERT kept 1/7 and
    poisoned the transaction. That is why the batch FALLS BACK here rather than
    replacing the loop — the batch is rejected first, then rows 2 and 4 are.
    """
    seen = []

    def reject(stmt):
        seen.append(stmt)
        if insert_row_count(stmt) > 1:
            return True                         # the batch attempt itself
        per_row = [s for s in seen if insert_row_count(s) == 1]
        return len(per_row) in (2, 4)           # two bad rows in one page
    db = FakeSession(reject_when=reject)
    res = await persist_bars(db, [cand(open_time=T0 + i * STEP) for i in range(5)])
    assert res.persisted == 3 and res.db_rejected == 2
    assert db.savepoints == 6, "one for the batch attempt, then one per row"
    assert db.open_savepoints == 0


@pytest.mark.asyncio
async def test_an_unexpected_db_failure_does_NOT_fall_back_to_per_row():
    """The fallback is for a row the database JUDGED, never for a database that
    failed. Re-issuing 500 statements at a database that just dropped a
    connection turns one fault into 500, and would report `db_rejected` for rows
    nothing ever judged."""
    class Dropped(FakeSession):
        async def execute(self, stmt, *a, **k):
            self.calls.append(stmt)
            raise RuntimeError("connection reset by peer")

    db = Dropped()
    res = await persist_bars(db, [cand(open_time=T0 + i * STEP) for i in range(9)])
    assert len(db.calls) == 1, "the page was attempted once and NOT retried per row"
    assert db.savepoints == 1
    assert res.db_error == 1 and res.db_rejected == 0
    assert res.persisted == 0 and res.duplicate == 0


@pytest.mark.asyncio
async def test_the_fallback_runs_only_for_a_row_level_rejection():
    """Every exception family the module treats as a rejection must reach the
    per-row loop, and nothing else may."""
    for name, falls_back in (("IntegrityError", True), ("CheckViolation", True),
                             ("DataError", True), ("OperationalError", False),
                             ("InterfaceError", False), ("TimeoutError", False)):
        exc = type(name, (Exception,), {})

        class _S(FakeSession):
            async def execute(self_, stmt, *a, **k):
                self_.calls.append(stmt)
                if insert_row_count(stmt) > 1:
                    raise exc("boom")
                class _R:
                    rowcount = 1
                return _R()

        db = _S()
        res = await persist_bars(db, [cand(open_time=T0 + i * STEP) for i in range(3)])
        if falls_back:
            assert len(db.calls) == 4, f"{name} must fall back to per-row"
            assert res.persisted == 3 and res.db_error == 0
        else:
            assert len(db.calls) == 1, f"{name} must NOT fall back"
            assert res.db_error == 1 and res.persisted == 0


@pytest.mark.asyncio
async def test_T22_the_writer_never_commits_or_rolls_back_the_caller():
    db = FakeSession(reject_when=lambda s: True)
    await persist_bars(db, [cand()])
    assert db.commits == 0 and db.rollbacks == 0


def test_T22b_no_commit_or_rollback_appears_in_the_module_at_all():
    """AST, so a comment mentioning commit cannot satisfy it."""
    tree = ast.parse((BACKEND / "app" / "services" / "ohlcv_writer.py").read_text(encoding="utf-8"))
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "commit" not in called and "rollback" not in called, sorted(called)


def test_T31_T32_the_conflict_target_is_the_column_list_never_the_name():
    assert W.CONFLICT_TARGET == ("source", "symbol", "timeframe", "open_time")
    src = (BACKEND / "app" / "services" / "ohlcv_writer.py").read_text(encoding="utf-8")
    code = re.sub(r"#[^\n]*", " ", src)
    code = re.sub(r'"""(?:.|\n)*?"""', " ", code)
    assert "index_elements" in code
    assert "uq_ohlcv_bars_natural" not in code, (
        "the constraint NAME is not portable across construction orders")
    assert "constraint=" not in code


@pytest.mark.asyncio
async def test_T28_the_same_key_twice_in_one_call_is_a_duplicate_not_an_error():
    db = FakeSession(rowcounts=[1, 0])
    c = cand()
    res = await persist_bars(db, [c, c])
    assert res.persisted == 1 and res.duplicate == 1 and res.db_error == 0


@pytest.mark.asyncio
async def test_a_db_outage_is_not_reported_as_an_invalid_candle():
    class Boom(FakeSession):
        async def execute(self, stmt, *a, **k):
            raise RuntimeError("connection reset")
    res = await persist_bars(Boom(), [cand()])
    assert res.db_error == 1 and res.db_rejected == 0 and res.invalid == 0


# ── T23 · the architectural boundary ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_T23_the_fetch_completes_before_the_session_is_touched():
    """Runtime proof, not a comment: the session raises if used while the
    collector has not returned."""
    order = []

    class SlowCollector:
        async def fetch_ohlcv(self, *a, **k):
            order.append("fetch_start")
            await asyncio.sleep(0.01)
            order.append("fetch_end")
            return frame(4)

    class StrictSession(FakeSession):
        async def execute(self, stmt, *a, **k):
            order.append("db")
            assert "fetch_end" in order, "DB touched before the fetch finished"
            return await super().execute(stmt, *a, **k)

    res = await W.collect_and_persist(StrictSession(), SlowCollector(),
                                      "BTCUSDT", "15m", now=T0 + 100 * STEP)
    assert order[0] == "fetch_start" and order[1] == "fetch_end"
    # ONE statement for the page, carrying all three bars.
    assert order.count("db") == 1 and res.persisted == 3


def test_T23b_no_session_call_precedes_the_fetch_structurally():
    """AST: inside collect_and_persist the fetch await must appear before any
    `db.` usage, so the ordering cannot be reversed by a later edit."""
    src = (BACKEND / "app" / "services" / "ohlcv_writer.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "collect_and_persist")
    fetch_line = min(n.lineno for n in ast.walk(fn)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                     and n.func.id == "fetch_bars_bounded")
    db_lines = [n.lineno for n in ast.walk(fn)
                if isinstance(n, ast.Name) and n.id == "db"]
    assert db_lines, "expected the session to be used at all"
    assert min(db_lines) > fetch_line, (
        "the session must not be referenced before the bounded fetch")


# ── T33-T35 · dormancy ───────────────────────────────────────────────────────
def test_T33_importing_the_writer_has_no_side_effects():
    import importlib
    import sys
    for mod in ("app.services.ohlcv_writer",):
        sys.modules.pop(mod, None)
        m = importlib.import_module(mod)
        assert m is not None
    tree = ast.parse((BACKEND / "app" / "services" / "ohlcv_writer.py").read_text(encoding="utf-8"))
    for node in tree.body:
        assert not isinstance(node, (ast.Expr,)) or isinstance(node.value, ast.Constant), (
            "module level must not execute anything but the docstring")
        if isinstance(node, ast.Assign):
            assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                           and n.func.attr in ("create_task", "run", "add_job")
                           for n in ast.walk(node))


def test_T34_T35_the_scheduler_gained_no_ohlcv_job_and_no_startup_hook():
    sched = (BACKEND / "app" / "services" / "scheduler.py").read_text(encoding="utf-8")
    main = (BACKEND / "app" / "main.py").read_text(encoding="utf-8")
    for text, label in ((sched, "scheduler.py"), (main, "main.py")):
        code = re.sub(r"#[^\n]*", " ", text)
        code = re.sub(r'"""(?:.|\n)*?"""', " ", code)
        assert "ohlcv_writer" not in code, f"{label} must not reference the writer"
        assert "collect_and_persist" not in code, label


# ── T38-T42 · non-coupling ───────────────────────────────────────────────────
def test_T38_T42_no_decision_surface_imports_the_writer():
    for rel in ("app/backtesting/tracker.py", "app/backtesting/lifecycle.py",
                "app/backtesting/resolution_core.py", "app/services/scheduler.py",
                "app/services/entry_activation.py", "app/services/entry_flags.py",
                "app/services/publication.py", "app/services/lifecycle_log.py",
                "app/services/shadow_eval.py", "app/services/coin_memory.py",
                "app/engines/ai_decision/signal_generator.py",
                "app/api/routes/signals.py", "scripts/p22a_shadow_eval.py"):
        text = (BACKEND / rel).read_text(encoding="utf-8")
        assert "ohlcv_writer" not in text, rel
        assert "collect_and_persist" not in text, rel


def test_the_writer_depends_on_no_decision_module():
    """The dependency must not run the other way either."""
    src = (BACKEND / "app" / "services" / "ohlcv_writer.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            mods.add(n.module or "")
        elif isinstance(n, ast.Import):
            mods.update(a.name for a in n.names)
    forbidden = ("tracker", "lifecycle", "resolution", "entry_activation",
                 "entry_flags", "publication", "coin_memory", "signal_generator",
                 "shadow_eval", "scheduler")
    for m in mods:
        assert not any(f in m for f in forbidden), m


def test_this_checkpoint_adds_no_migration():
    names = sorted(p.name for p in (BACKEND / "migrations").glob("*.sql"))
    # Was `names[-1] == "0011_ohlcv_shadow.sql"`: a LOCAL claim ("this checkpoint
    # added no migration") proved by a GLOBAL fact ("nothing was added since"). The
    # first legitimate later migration breaks it — 0012 did. Pin the set this
    # checkpoint was written against, and assert no later migration reshapes its table.
    assert "0011_ohlcv_shadow.sql" in names
    for later in [n for n in names if n > "0011_ohlcv_shadow.sql"]:
        body = (BACKEND / "migrations" / later).read_text(encoding="utf-8").lower()
        body = " ".join(l for l in body.splitlines() if not l.strip().startswith("--"))
        assert "ohlcv_bars" not in body, f"{later} reshapes ohlcv_bars"
    sql = (BACKEND / "migrations" / "0011_ohlcv_shadow.sql").read_text(encoding="utf-8")
    assert "ohlcv_bars" in sql          # untouched by A2


def test_the_backfill_script_was_not_resurrected():
    assert not (BACKEND / "scripts" / "ohlcv_backfill.py").exists(), (
        "backfill is A3 scope and its --write path is known dead code")


# ══ DE-DUPLICATION: the duplicate must be where drop_newest CANNOT mask it ══
#
# The pre-existing guard above places its duplicate on the NEWEST bar, which the
# forming-candle rule removes anyway — so one of the pair disappears for an
# unrelated reason and the assertion still holds with de-duplication deleted.
# Measured against a de-dup-removed mutant:
#     duplicate at newest : n=5 unique=5  -> assertion PASSES (guard blind)
#     duplicate in middle : n=5 unique=4  -> assertion FAILS  (defect visible)
# These tests put the duplicate in the middle. The newest-bar tests above are
# untouched and still cover the forming-candle rule on their own.


def _mid_duplicate_frame():
    """5 bars T0..T0+4, with T0+2 (a CLOSED, non-newest bar) sent twice."""
    base = frame(5)
    return pd.concat([base, base.iloc[2:3]])


def test_a_duplicate_middle_closed_bar_is_collapsed_to_one_copy():
    got, res = eligible_bars(_mid_duplicate_frame(), "BTCUSDT", "15m",
                             now=T0 + 100 * STEP)
    times = [c.open_time for c in got]
    dup_time = T0 + 2 * STEP

    assert times.count(dup_time) == 1, \
        f"the duplicated middle bar was emitted {times.count(dup_time)} times"
    assert len(times) == len(set(times)), f"duplicates survived: {times}"
    # 6 rows in, one is a duplicate, one is the newest/forming bar -> 4 out.
    assert len(got) == 4, f"expected 4 candidates, got {len(got)}"
    assert times == sorted(times), "ordering must stay deterministic"


def test_the_middle_duplicate_survives_de_dup_removal_and_would_be_caught():
    """The guard's own falsification: with `duplicated(keep='last')` deleted the
    middle duplicate reaches the candidate list, so this fixture — unlike the
    newest-bar one — can actually observe the defect."""
    src = (BACKEND / "app" / "services" / "ohlcv_writer.py").read_text(encoding="utf-8")
    anchor = 'work = work[~work.index.duplicated(keep="last")].sort_index()'
    assert src.count(anchor) == 1, "de-dup anchor moved; this guard needs updating"

    import importlib.util
    import sys
    import tempfile
    mut_path = pathlib.Path(tempfile.mkdtemp()) / "ohlcv_writer_nodedup.py"
    mut_path.write_text(src.replace(anchor, "work = work.sort_index()"),
                        encoding="utf-8")
    spec = importlib.util.spec_from_file_location("ohlcv_writer_nodedup", mut_path)
    mut = importlib.util.module_from_spec(spec)
    sys.modules["ohlcv_writer_nodedup"] = mut
    try:
        spec.loader.exec_module(mut)
        got, _ = mut.eligible_bars(_mid_duplicate_frame(), "BTCUSDT", "15m",
                                   now=T0 + 100 * STEP)
        times = [c.open_time for c in got]
        assert len(times) != len(set(times)), \
            "de-dup removal was NOT observable — this fixture cannot guard it"
        assert times.count(T0 + 2 * STEP) == 2
    finally:
        sys.modules.pop("ohlcv_writer_nodedup", None)


def test_the_middle_duplicate_guard_does_not_depend_on_the_newest_bar_rule():
    """If drop_newest were what made the assertion hold, disabling it would not
    change the duplicate count. It must not: the duplicate is in the middle."""
    got, _ = eligible_bars(_mid_duplicate_frame(), "BTCUSDT", "15m",
                           now=T0 + 100 * STEP, drop_newest=False)
    times = [c.open_time for c in got]
    assert times.count(T0 + 2 * STEP) == 1, "de-dup, not drop_newest, must do this"
    assert len(times) == len(set(times))
    assert len(got) == 5, "with the newest bar admitted, 6 rows minus 1 dup = 5"


def test_repeated_and_out_of_order_middle_duplicates_still_collapse():
    base = frame(6)
    noisy = pd.concat([base, base.iloc[2:3], base.iloc[4:5], base.iloc[2:3]])
    got, _ = eligible_bars(noisy.iloc[::-1], "BTCUSDT", "15m", now=T0 + 100 * STEP)
    times = [c.open_time for c in got]
    assert len(times) == len(set(times)), f"duplicates survived: {times}"
    assert times == sorted(times), "reverse-order input must still come out sorted"
    assert len(got) == 5, "6 distinct bars minus the newest/forming one"
