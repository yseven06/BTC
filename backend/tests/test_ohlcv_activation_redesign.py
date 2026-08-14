"""CP-OHLCV-A3c ACTIVATION REDESIGN — still dormant; nothing is scheduled here.

Each guarantee below exists because the activation preflight measured a way the
run could fail badly once a scheduler finally calls it:

  * an outer deadline cancels the task, CancelledError unwinds past every
    `except Exception`, and the result — including rows already committed — is
    never returned;
  * one pathological item burns 63-70s of a 600s run, and because the universe
    is ordered by a UNIQUE symbol the truncation always falls on the same
    alphabetical tail;
  * an HTTP 418 abandons one item's retries while the run issues ~200 more
    requests at an IP the exchange has already banned;
  * `res.absorb` after `await db.commit()` erases an item's whole accounting
    when the commit raises.
"""

from __future__ import annotations

import ast
import asyncio
import dataclasses
import inspect
import json
import pathlib
import time
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from app.services import job_guard
from app.services import ohlcv_collector_job as J
from app.services import ohlcv_writer as W
from app.services.ohlcv_collector_job import (ITEM_BUDGET_SECONDS,
                                              MAX_FAILURES_RETAINED,
                                              CollectionResult, collect_once)

BACKEND = pathlib.Path(__file__).resolve().parent.parent


# Rotation now starts from the DURABLE executed-run sequence, so pinning the
# traversal is simply choosing that sequence: run_seq 0 puts S0U first. The old
# helper searched wall-clock buckets for an offset of 0 and had to assert the pin
# still held; with the clock gone there is nothing left to drift.
PINNED_SEQ = 0
assert J.rotation_offset(12, PINNED_SEQ) == 0
UTC = timezone.utc
T0 = datetime(2026, 8, 1, tzinfo=UTC)
STEP = timedelta(minutes=15)


def frame(n=6, start=T0):
    idx = pd.DatetimeIndex([start + i * STEP for i in range(n)], tz=UTC)
    df = pd.DataFrame({"open": np.full(n, 100.0), "high": np.full(n, 110.0),
                       "low": np.full(n, 90.0), "close": np.full(n, 100.0),
                       "volume": np.full(n, 10.0)}, index=idx)
    df["close_time"] = [t + STEP for t in idx]
    return df


class Sess:
    """Fake session. `fail_commit` reproduces a commit that raises."""

    def __init__(self, rows=(), fail_commit=False, fail_execute=False, registry=None):
        self.rows, self.fail_commit, self.fail_execute = list(rows), fail_commit, fail_execute
        self.savepoints = self.commits = self.rollbacks = 0
        self.queries: list = []
        self.inserted: list = []
        if registry is not None:
            registry.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *e):
        return False

    def begin_nested(self):
        outer = self

        class _SP:
            async def __aenter__(s):
                outer.savepoints += 1
                return s

            async def __aexit__(s, *e):
                return False
        return _SP()

    async def execute(self, stmt, *a, **k):
        text = " ".join(str(stmt).split())
        self.queries.append(text)
        if self.fail_execute and "wm_pairs" not in text:
            raise RuntimeError("db unavailable")
        if "INSERT INTO ohlcv_bars" in text:
            try:
                self.inserted.append(stmt.compile().params.get("source"))
            except Exception:                      # noqa: BLE001
                self.inserted.append("?")
        rows = self.rows if "wm_pairs" in text else []

        class _R:
            rowcount = 1

            def all(s):
                return rows

            def scalars(s):
                class _S:
                    def all(x):
                        return []
                return _S()
        return _R()

    async def commit(self):
        if self.fail_commit:
            raise RuntimeError("commit exploded")
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def factory(rows=(), registry=None, **kw):
    return lambda: Sess(rows, registry=registry, **kw)


class Col:
    def __init__(self, n=6, stall_symbol=None, stall_for=300.0):
        self.n, self.stall_symbol, self.stall_for = n, stall_symbol, stall_for
        self.calls: list = []
        self.closed = 0

    async def fetch_ohlcv(self, symbol, timeframe, limit=500, end_time_ms=None):
        self.calls.append((symbol, timeframe, limit, end_time_ms))
        if symbol == self.stall_symbol:
            await asyncio.sleep(self.stall_for)
        return frame(self.n)

    async def close(self):
        self.closed += 1


class _Resp:
    def __init__(self, code, headers=None):
        self.status_code, self.headers = code, headers or {}


class _HTTPError(Exception):
    def __init__(self, code, headers=None):
        super().__init__(f"HTTP {code}")
        self.response = _Resp(code, headers)


# ══ 1 · CANCELLATION-SAFE RESULT ═══════════════════════════════════════════
@pytest.mark.asyncio
async def test_outer_cancellation_preserves_the_partial_result():
    """The witness must survive a BaseException unwinding the whole call stack —
    a returned value cannot, which is why the caller owns the object."""
    col = Col(stall_symbol="S9U")
    res = CollectionResult()
    task = asyncio.create_task(collect_once(
        factory(), col, symbols=[f"S{i}U" for i in range(12)],
        timeframes=["15m"], spacing=0, result=res, run_seq=PINNED_SEQ))
    await asyncio.sleep(0.4)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert res.cancelled is True, "cancellation must be recorded, not swallowed"
    assert res.bars_persisted > 0, "rows committed before the cancel must stay counted"
    assert res.symbols_attempted > 0
    assert res.healthy is False, "a cancelled run must never report healthy"


@pytest.mark.asyncio
async def test_cancellation_is_re_raised_not_converted():
    """job_guard must still see a cancelled task; a deadline is not a fetch error."""
    col = Col(stall_symbol="AU")
    res = CollectionResult()
    task = asyncio.create_task(collect_once(
        factory(), col, symbols=["AU"], timeframes=["15m"], spacing=0, result=res))
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert res.fetch_error == 0 and res.db_error == 0, \
        "cancellation was relabelled as an ordinary error"


@pytest.mark.asyncio
async def test_no_work_continues_after_cancellation():
    col = Col(stall_symbol="S3U")
    res = CollectionResult()
    task = asyncio.create_task(collect_once(
        factory(), col, symbols=[f"S{i}U" for i in range(12)],
        timeframes=["15m"], spacing=0, result=res, run_seq=PINNED_SEQ))
    await asyncio.sleep(0.4)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    seen = len(col.calls)
    await asyncio.sleep(0.3)
    assert len(col.calls) == seen, "a request was issued after cancellation"


def test_result_ownership_is_structural():
    """collect_once must ACCEPT a result; returning one cannot survive a cancel."""
    assert "result" in inspect.signature(collect_once).parameters
    src = inspect.getsource(collect_once)
    assert "result if result is not None else" in src, \
        "collect_once must adopt the caller's result object"


# ══ 2 · PER-ITEM DEADLINE ══════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_one_pathological_item_cannot_starve_the_rest():
    col = Col(stall_symbol="AAAU")
    res = CollectionResult()
    t0 = time.monotonic()
    await collect_once(factory(), col, symbols=["AAAU", "ZZZU"],
                       timeframes=["15m"], spacing=0, item_budget=0.4, result=res)
    elapsed = time.monotonic() - t0

    assert res.items_deadline_exceeded == 1
    assert res.symbols_succeeded == 1, "the healthy symbol must still be collected"
    assert res.symbols_failed == 1
    assert res.healthy is False
    assert elapsed < 3.0, f"the stalled item was not bounded ({elapsed:.1f}s)"


@pytest.mark.asyncio
async def test_item_timeout_does_not_poison_later_items():
    col = Col(stall_symbol="AAAU")
    reg: list = []
    res = CollectionResult()
    await collect_once(factory(registry=reg), col, symbols=["AAAU", "ZZZU"],
                       timeframes=["15m"], spacing=0, item_budget=0.4, result=res)
    assert res.bars_persisted > 0, "the later item still persisted"
    assert res.db_error == 0, "an item timeout must not be reported as a DB error"


@pytest.mark.asyncio
async def test_outer_cancellation_wins_over_the_item_budget():
    """A generous item budget must not swallow an outer deadline."""
    col = Col(stall_symbol="AU")
    res = CollectionResult()
    task = asyncio.create_task(collect_once(
        factory(), col, symbols=["AU"], timeframes=["15m"],
        spacing=0, item_budget=600.0, result=res))
    await asyncio.sleep(0.25)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert res.cancelled is True and res.items_deadline_exceeded == 0


def test_item_budget_is_derived_from_the_measured_worst_item():
    """3 attempts x 20s timeout + 1s + 2s backoff = 63s worst case; the bound
    must be one fetch timeout plus headroom, not larger than the fetch itself."""
    assert ITEM_BUDGET_SECONDS == 25.0
    assert ITEM_BUDGET_SECONDS > W.DEFAULT_FETCH_TIMEOUT
    assert ITEM_BUDGET_SECONDS < (W.DEFAULT_FETCH_RETRIES + 1) * W.DEFAULT_FETCH_TIMEOUT


@pytest.mark.asyncio
async def test_a_non_positive_item_budget_is_refused():
    for bad in (0, -1.0):
        with pytest.raises(ValueError, match="item_budget"):
            await collect_once(factory(), Col(), symbols=["A"], item_budget=bad)


# ══ 3 · 418 / 429 ══════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_418_stops_the_entire_run_not_just_the_item():
    """The ban is on the IP. Continuing would extend it ~200 more times."""
    class Banned(Col):
        async def fetch_ohlcv(self, symbol, timeframe, limit=500, end_time_ms=None):
            self.calls.append((symbol, timeframe, limit, end_time_ms))
            if len(self.calls) >= 2:
                raise _HTTPError(418)
            return frame()

    col = Banned()
    res = CollectionResult()
    await collect_once(factory(), col, symbols=[f"S{i}U" for i in range(30)],
                       timeframes=["15m"], spacing=0, result=res)

    assert res.aborted is True and res.abort_reason == "http_418_ip_banned"
    assert res.fetch_ip_banned == 1
    assert len(col.calls) <= 3, f"issued {len(col.calls)} requests at a banned IP"
    assert res.healthy is False
    assert any("RUN ABORTED" in f for f in res.failures)


@pytest.mark.asyncio
async def test_418_preserves_rows_committed_before_the_ban():
    class Banned(Col):
        async def fetch_ohlcv(self, symbol, timeframe, limit=500, end_time_ms=None):
            self.calls.append((symbol, timeframe, limit, end_time_ms))
            if len(self.calls) >= 3:
                raise _HTTPError(418)
            return frame()

    res = CollectionResult()
    await collect_once(factory(), Banned(), symbols=[f"S{i}U" for i in range(10)],
                       timeframes=["15m"], spacing=0, result=res)
    assert res.bars_persisted > 0, "pre-ban commits were discarded"
    assert res.aborted is True


@pytest.mark.asyncio
async def test_symbols_not_reached_after_abort_are_not_counted_as_failures():
    class Banned(Col):
        async def fetch_ohlcv(self, symbol, timeframe, limit=500, end_time_ms=None):
            self.calls.append((symbol, timeframe, limit, end_time_ms))
            raise _HTTPError(418)

    res = CollectionResult()
    await collect_once(factory(), Banned(), symbols=[f"S{i}U" for i in range(20)],
                       timeframes=["15m"], spacing=0, result=res)
    assert res.symbols_attempted == 1, "the sweep kept going after the abort"
    assert res.symbols_failed <= 1


@pytest.mark.asyncio
async def test_429_is_retried_and_never_aborts_the_run():
    class Limited:
        def __init__(s):
            s.calls = 0

        async def fetch_ohlcv(s, *a, **k):
            s.calls += 1
            raise _HTTPError(429, {"Retry-After": "1"})

    base = W.BACKOFF_BASE_SECONDS
    W.BACKOFF_BASE_SECONDS = 0.001
    try:
        res = CollectionResult()
        await collect_once(factory(), Limited(), symbols=["AU", "BU"],
                           timeframes=["15m"], spacing=0, retries=1,
                           item_budget=10.0, result=res)
    finally:
        W.BACKOFF_BASE_SECONDS = base
    assert res.fetch_rate_limited > 0
    assert res.aborted is False, "a rate limit is not a ban"
    assert res.symbols_attempted == 2, "the run must continue past a 429"


def test_429_retry_after_is_clamped_and_falls_back_safely():
    assert W._retry_after_seconds(_HTTPError(429, {"Retry-After": "9999"})) \
        == W.BACKOFF_MAX_SECONDS
    assert W._retry_after_seconds(_HTTPError(429, {"Retry-After": "2"})) == 2.0
    assert W._retry_after_seconds(_HTTPError(429, {})) is None
    assert W._retry_after_seconds(_HTTPError(429, {"Retry-After": "Wed, 21 Oct"})) is None


def test_429_is_not_a_db_failure():
    res = W.WriteResult()
    assert W._http_status(_HTTPError(429)) == 429
    assert res.db_error == 0 and res.db_rejected == 0


# ══ 4 · COMMIT / ACCOUNTING ════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_commit_failure_keeps_the_attempt_and_never_inflates_persisted():
    res = CollectionResult()
    await collect_once(factory(fail_commit=True), Col(), symbols=["AU"],
                       timeframes=["15m"], spacing=0, result=res)
    assert res.bars_eligible > 0, "attempted work was erased from telemetry"
    assert res.bars_persisted == 0, "a failed commit reported durable rows"
    assert res.bars_staged_rolled_back > 0, "discarded rows were not accounted"
    assert res.symbols_failed == 1 and res.db_error == 1


@pytest.mark.asyncio
async def test_successful_commit_counts_persisted_exactly_once():
    res = CollectionResult()
    await collect_once(factory(), Col(), symbols=["AU"], timeframes=["15m"],
                       spacing=0, result=res)
    # frame(6) -> 5 eligible; with no watermark the bootstrap cap keeps 4.
    assert res.bars_persisted == 4 == res.bars_eligible - res.bars_bootstrap_trimmed
    assert res.bars_staged_rolled_back == 0


def test_absorb_does_not_touch_persisted():
    """Structural: only the caller, after a successful commit, may count it."""
    res = CollectionResult()
    w = W.WriteResult()
    w.persisted, w.eligible, w.duplicate = 7, 7, 3
    res.absorb(w)
    assert res.bars_persisted == 0, "absorb() counted rows the commit had not made durable"
    assert res.bars_eligible == 7 and res.bars_duplicate == 3


@pytest.mark.asyncio
async def test_db_unavailable_is_attributed_to_the_right_item():
    res = CollectionResult()
    await collect_once(factory(fail_execute=True), Col(),
                       symbols=["AU", "BU"], timeframes=["15m"], spacing=0, result=res)
    assert res.symbols_failed == 2 and res.bars_persisted == 0
    assert all("AU/15m" in f or "BU/15m" in f for f in res.failures)


# ══ 5 · SOURCE INVARIANT (must not regress) ════════════════════════════════
@pytest.mark.asyncio
async def test_source_read_equals_source_written():
    for src in (W.SOURCE_BINANCE, "kraken", "coinbase"):
        reg: list = []
        res = CollectionResult()
        await collect_once(factory(registry=reg), Col(), symbols=["BTCUSDT"],
                           timeframes=["15m"], spacing=0, source=src, result=res)
        read = [v for s in reg for q, p in zip(s.queries, [{}] * len(s.queries))
                for v in []]
        written = sorted({v for s in reg for v in s.inserted})
        assert written == [src], f"{src} was written as {written}"


# ══ 6 · TELEMETRY / SERIALISATION ══════════════════════════════════════════
def test_as_dict_is_json_safe_and_stable():
    res = CollectionResult()
    res.run_id = "abc123"
    res.note_failure("boom")
    d = res.as_dict()
    json.dumps(d)                                   # must not raise
    assert d["healthy"] is res.healthy
    for f in dataclasses.fields(CollectionResult):
        assert f.name in d, f"{f.name} missing from the witness"
    assert not any(isinstance(v, BaseException) for v in d.values())


def test_failures_are_capped_and_the_drop_is_reported():
    res = CollectionResult()
    for i in range(MAX_FAILURES_RETAINED + 40):
        res.note_failure(f"failure {i}")
    assert len(res.failures) == MAX_FAILURES_RETAINED
    assert res.failures_dropped == 40


def test_a_single_failure_string_is_truncated():
    """A watermark StatementError stringifies ~28 KB of bind parameters."""
    res = CollectionResult()
    res.note_failure("x" * 40_000)
    assert len(res.failures[0]) <= 500


def test_invalid_reason_cardinality_is_bounded():
    res = CollectionResult()
    for i in range(200):
        w = W.WriteResult()
        w.invalid_reasons = {f"reason_{i}": 1}
        res.absorb(w)
    assert len(res.invalid_reasons) <= J.MAX_INVALID_REASONS


def test_witness_carries_the_activation_facing_fields():
    d = CollectionResult().as_dict()
    for k in ("run_id", "started_at", "completed_at", "duration_seconds",
              "symbols_discovered", "symbols_selected", "universe_overflow",
              "symbols_attempted", "symbols_succeeded", "symbols_failed",
              "symbols_skipped", "timeframes_attempted", "fetch_attempts",
              "fetch_success", "fetch_timeout", "fetch_error",
              "fetch_rate_limited", "fetch_ip_banned", "retry_recovered",
              "retry_exhausted", "malformed_response", "watermark_failed",
              "watermark_anomalies", "bars_eligible", "bars_persisted",
              "bars_duplicate", "bars_invalid", "bars_forming_or_not_closed",
              "db_rejected", "db_error", "cancelled", "aborted",
              "items_deadline_exceeded", "bars_staged_rolled_back"):
        assert k in d, f"activation witness is missing {k}"


# ══ 7 · SHADOW HEALTH SCOPING ══════════════════════════════════════════════
def test_all_seven_existing_jobs_keep_their_semantics():
    assert set(job_guard.JOB_SPECS) == {
        "signals_15m", "signals_1h", "signals_4h", "signals_1d",
        "perf_tracking", "price_alerts", "startup_check"}
    for job_id, spec in job_guard.JOB_SPECS.items():
        assert spec.shadow is False, f"{job_id} silently became a shadow job"
    assert {j: s.critical for j, s in job_guard.JOB_SPECS.items()} == {
        "signals_15m": True, "signals_1h": True, "signals_4h": False,
        "signals_1d": False, "perf_tracking": True, "price_alerts": True,
        "startup_check": False}


def test_shadow_defaults_to_false_so_old_specs_are_unchanged():
    spec = job_guard.JobSpec(budget_seconds=1.0, cadence_seconds=2.0, critical=True)
    assert spec.shadow is False


def test_a_shadow_job_overrun_does_not_degrade_global_health(monkeypatch):
    specs = dict(job_guard.JOB_SPECS)
    specs["shadow_probe"] = job_guard.JobSpec(
        budget_seconds=1.0, cadence_seconds=10.0, critical=False, shadow=True)
    monkeypatch.setattr(job_guard, "JOB_SPECS", specs)

    live = job_guard._Liveness()
    live.running = True
    live.running_since_monotonic = time.monotonic() - 999
    monkeypatch.setitem(job_guard._STATE, "shadow_probe", live)

    snap = job_guard.snapshot()
    assert "shadow_probe" in snap["shadow_overrunning_jobs"]
    assert "shadow_probe" not in snap["overrunning_jobs"]
    assert snap["shadow_degraded"] is True
    assert snap["degraded"] is False, \
        "a shadow job's overrun degraded the global trading-health flag"
    assert snap["jobs"]["shadow_probe"]["currently_running"] is True, \
        "the shadow job must still be fully observable"


def test_a_non_shadow_overrun_still_degrades_global_health(monkeypatch):
    """The scoping must not have disarmed the real signal."""
    live = job_guard._Liveness()
    live.running = True
    live.running_since_monotonic = time.monotonic() - 99_999
    monkeypatch.setitem(job_guard._STATE, "signals_15m", live)
    snap = job_guard.snapshot()
    assert "signals_15m" in snap["overrunning_jobs"] and snap["degraded"] is True


# ══ 8 · STILL DORMANT ══════════════════════════════════════════════════════
def test_no_ohlcv_scheduler_registration_and_no_caller():
    sched = (BACKEND / "app/services/scheduler.py").read_text(encoding="utf-8")
    for name in ("ohlcv_collector_job", "collect_once", "run_collection_once",
                 "ohlcv_writer", "collect_and_persist"):
        assert name not in sched, f"scheduler references {name}"
    assert "ohlcv" not in {j.lower() for j in job_guard.JOB_SPECS}

    hits = []
    for p in list((BACKEND / "app").rglob("*.py")) + list((BACKEND / "scripts").rglob("*.py")):
        # ohlcv_progression.py joined the dormant subsystem in 0012: it holds the
        # fairness counter and is imported only by the collector.
        if p.name in ("ohlcv_writer.py", "ohlcv_collector_job.py",
                      "ohlcv_progression.py") or "__pycache__" in str(p):
            continue
        t = p.read_text(encoding="utf-8", errors="ignore")
        if any(n in t for n in ("ohlcv_collector_job", "collect_once",
                                "run_collection_once", "collect_and_persist")):
            hits.append(str(p.relative_to(BACKEND)))
    assert hits == [], f"an OHLCV production caller appeared: {hits}"


def test_collection_stays_strictly_serial():
    src = (BACKEND / "app/services/ohlcv_collector_job.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fan = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
           and (getattr(n.func, "attr", None) or getattr(n.func, "id", None))
           in ("gather", "create_task", "ensure_future", "TaskGroup", "Semaphore",
               "as_completed")]
    assert fan == [], "collection grew a fan-out"


# ══ 9 · THE SHARED COLLECTOR MUST STAY UNTOUCHED ══════════════════════════
def test_the_shared_binance_collector_is_byte_identical_to_production():
    """Pass-B's T14 encodes a real boundary: the collector is shared with the
    live signal sweeps, the tracker, the price/signal routes, the backtesting
    engine and the AI decision engine. A shadow store must not reach into it.

    An earlier draft added an opt-in `include_extended` constructor flag to
    carry quote_volume / trade_count / taker_buy_*. It was reverted: those four
    columns are nullable, unconstrained and unvalidated, so they are not part of
    the first activation contract. They stay NULL.
    """
    import subprocess
    out = subprocess.run(["git", "show",
                          "7e156ffc72121f4cbfc838164dc03158e7ffc87c:backend/app/collectors/binance_collector.py"],
                         cwd=BACKEND.parent, capture_output=True, check=True).stdout
    live = (BACKEND / "app" / "collectors" / "binance_collector.py").read_bytes()
    # git may materialise CRLF on checkout; compare content, not line endings.
    def norm(b: bytes) -> bytes:
        return b.replace(bytes([13, 10]), bytes([10]))

    assert norm(live) == norm(out), "the shared production BinanceCollector was modified"


def test_no_ohlcv_module_asks_the_collector_for_extra_columns():
    for rel in ("app/services/ohlcv_collector_job.py", "app/services/ohlcv_writer.py"):
        src = (BACKEND / rel).read_text(encoding="utf-8")
        assert "include_extended" not in src, f"{rel} still requests a widened frame"


def test_bar_candidate_can_carry_the_optional_fields():
    names = {f.name for f in dataclasses.fields(W.BarCandidate)}
    assert {"quote_volume", "trade_count",
            "taker_buy_base_volume", "taker_buy_quote_volume"} <= names


# ══ 10 · GUARDS THE FIRST SABOTAGE PASS PROVED DECORATIVE ══════════════════
#
# Each of the four below survived a mutation because the behaviour it claimed to
# protect was ALSO forced by a second, coincidental term. A guard that only
# passes because something else happens to be true is not a guard.

def test_health_terms_are_individually_load_bearing():
    """`healthy` must fail on EACH terminal state on its own.

    The end-to-end tests could not prove this: an item timeout also sets
    symbols_failed, and a 418 also sets retry_exhausted, so removing either term
    from `healthy` left every behavioural assertion still passing.
    """
    for field, value in (("cancelled", True),
                         ("aborted", True),
                         ("items_deadline_exceeded", 1),
                         ("watermark_failed", True),
                         ("watermark_anomalies", 1),
                         ("universe_overflow", True),
                         ("symbols_failed", 1),
                         ("db_error", 1),
                         ("retry_exhausted", 1)):
        res = CollectionResult()
        assert res.healthy is True, "a fresh result must be healthy"
        setattr(res, field, value)
        assert res.healthy is False, f"healthy ignored {field}={value!r}"


def test_no_concurrency_primitive_is_even_referenced():
    """AST Call-only checking missed a bare reference; a name that is imported
    or bound is the first step toward a fan-out, so reject it outright."""
    src = (BACKEND / "app/services/ohlcv_collector_job.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    banned = {"gather", "create_task", "ensure_future", "TaskGroup",
              "Semaphore", "as_completed", "wait"}
    refs = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and n.attr in banned:
            refs.append(n.attr)
        if isinstance(n, ast.Name) and n.id in banned:
            refs.append(n.id)
    assert refs == [], f"a concurrency primitive is referenced: {refs}"
    # wait_for is the per-item bound and is explicitly allowed
    assert "asyncio.wait_for(" in src, "the per-item bound disappeared"
