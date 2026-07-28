"""CP-HTTP-RESILIENCE-2 — the deadline is a hard wall-clock bound.

CP-HTTP-RESILIENCE-1 bounded the business work but not the unwinding: the guard
awaited the body inside `async with asyncio.timeout(...)`, and that block does
not return until the coroutine has finished unwinding. Measured in production on
2026-07-28 — a 30s budget released its slot after 127.1s, and a later run was
still holding it 1363s in with the event loop completely idle.

Reproduced exactly before the fix: a body with no cleanup returned at 0.50s
against a 0.5s budget, one with a 2s cleanup at 2.52s, and one whose cleanup
never finished never returned at all.

Every test here asserts elapsed wall-clock, not just "an exception was raised".
A guard that eventually gives up is not the same as one that gives up on time,
and only the second one keeps a scheduler slot free.
"""

from __future__ import annotations

import asyncio
import inspect
import textwrap
import threading
import time

import pytest

from app.services import job_guard
from app.services.job_guard import (
    CLEANUP_GRACE_SECONDS,
    JOB_SPECS,
    JobDeadlineExceeded,
    orphan_count,
    run_asset_with_deadline,
    run_with_deadline,
)

pytestmark = pytest.mark.asyncio

BUDGET = 0.4
GRACE = 0.4
LIMIT = BUDGET + GRACE
SLACK = 0.35          # test-runner jitter, not a semantic allowance


@pytest.fixture(autouse=True)
def _clean():
    job_guard.reset_for_tests()
    yield
    job_guard.reset_for_tests()


async def _elapsed(body, **kw):
    """Run `body()` under the guard and report (outcome, wall-clock seconds).

    `body` is an async function; calling it here is what produces the coroutine
    the guard drives.
    """
    t0 = time.perf_counter()
    outcome = "ok"
    try:
        await run_with_deadline("price_alerts", body(),
                                budget=BUDGET, cleanup_grace=GRACE, **kw)
    except JobDeadlineExceeded:
        outcome = "deadline"
    except Exception as exc:  # noqa: BLE001
        outcome = type(exc).__name__
    return outcome, time.perf_counter() - t0


# --- bodies -----------------------------------------------------------------

async def _no_cleanup():
    await asyncio.Event().wait()


def _cleanup(seconds):
    async def body():
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(seconds)
    return body


async def _cleanup_never():
    try:
        await asyncio.Event().wait()
    finally:
        await asyncio.Event().wait()


# --- 1. the hard bound ------------------------------------------------------

@pytest.mark.parametrize("name,body", [
    ("cleanup yok", _no_cleanup),
    ("cleanup grace icinde", _cleanup(0.15)),
    ("cleanup grace'i asar", _cleanup(30)),
    ("cleanup asla bitmez", _cleanup_never),
])
async def test_total_wall_clock_never_exceeds_budget_plus_grace(name, body):
    outcome, dt = await _elapsed(body)
    assert outcome == "deadline", name
    assert dt <= LIMIT + SLACK, f"{name}: {dt:.2f}s > sinir {LIMIT:.2f}s"


async def test_a_job_that_finishes_in_time_is_untouched():
    async def body():
        await asyncio.sleep(0.05)
        return {"ok": True}

    t0 = time.perf_counter()
    assert await run_with_deadline("price_alerts", body(),
                                   budget=BUDGET, cleanup_grace=GRACE) == {"ok": True}
    assert time.perf_counter() - t0 < BUDGET


async def test_a_business_exception_still_reaches_the_caller():
    """The guard must not turn a real failure into a deadline."""
    class Boom(Exception):
        pass

    async def body():
        raise Boom("upstream down")

    with pytest.raises(Boom):
        await run_with_deadline("price_alerts", body(), budget=BUDGET, cleanup_grace=GRACE)


# --- 2. cancellation and cleanup are separate phases -------------------------

async def test_cancellation_starts_at_the_budget_not_at_the_limit():
    """The business work must stop at `budget`; only release may use the grace."""
    cancelled_at = []

    async def body():
        t0 = time.perf_counter()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled_at.append(time.perf_counter() - t0)
            raise
        finally:
            await asyncio.sleep(0.15)

    await _elapsed(body)
    assert cancelled_at, "is govdesi hic iptal edilmedi"
    assert cancelled_at[0] <= BUDGET + SLACK, \
        f"iptal butcede degil {cancelled_at[0]:.2f}s'de basladi"


async def test_cleanup_that_finishes_in_time_is_waited_for():
    marks = []

    async def body():
        try:
            await asyncio.Event().wait()
        finally:
            marks.append("start")
            await asyncio.sleep(0.15)
            marks.append("done")

    await _elapsed(body)
    assert marks == ["start", "done"], "grace icindeki cleanup yarida kesildi"
    snap = job_guard.snapshot()["jobs"]["price_alerts"]
    assert snap["cleanup_overrun_count"] == 0
    assert snap["cleanup_completed_at"] is not None
    assert 0.1 <= snap["cleanup_duration_seconds"] <= GRACE + SLACK
    assert orphan_count() == 0


async def test_cleanup_overrun_is_visible_and_not_silent():
    await _elapsed(_cleanup_never)
    snap = job_guard.snapshot()["jobs"]["price_alerts"]
    assert snap["cleanup_overrun_count"] == 1
    assert snap["forced_cleanup_count"] == 1
    assert snap["cleanup_completed_at"] is None
    assert snap["deadline_overrun_seconds"] is not None
    assert snap["slot_release_seconds"] <= LIMIT + SLACK


async def test_telemetry_separates_cancellation_from_cleanup():
    await _elapsed(_cleanup(0.15))
    snap = job_guard.snapshot()["jobs"]["price_alerts"]
    for field in ("cancellation_requested_at", "cleanup_started_at",
                  "cleanup_completed_at", "cleanup_duration_seconds",
                  "cleanup_grace_seconds", "wall_clock_limit_seconds"):
        assert snap[field] is not None, f"{field} raporlanmiyor"


# --- 3. orphan handling ------------------------------------------------------

async def test_an_abandoned_cleanup_is_tracked_not_forgotten():
    """A task with no strong reference can be garbage-collected mid-flight and
    disappear. The guard must keep it observable until it really ends."""
    await _elapsed(_cleanup_never)
    assert orphan_count() == 1
    assert job_guard.snapshot()["orphan_task_count"] == 1
    assert job_guard.snapshot()["degraded"] is True


async def test_an_orphan_leaves_the_registry_when_it_finally_ends():
    await _elapsed(_cleanup(0.8))          # grace 0.4 -> terk edilir, sonra biter
    assert orphan_count() == 1
    for _ in range(40):
        if orphan_count() == 0:
            break
        await asyncio.sleep(0.05)
    assert orphan_count() == 0, "orphan kayitta takili kaldi"
    assert job_guard.snapshot()["jobs"]["price_alerts"]["orphan_task_count"] == 0


async def test_a_normal_run_leaves_no_orphan():
    async def body():
        await asyncio.sleep(0.02)

    await run_with_deadline("price_alerts", body(), budget=BUDGET, cleanup_grace=GRACE)
    assert orphan_count() == 0


async def test_an_orphans_exception_is_not_lost():
    async def body():
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0.6)
            raise RuntimeError("cleanup patladi")

    await _elapsed(body)
    for _ in range(40):
        if job_guard.snapshot()["jobs"]["price_alerts"]["last_cleanup_error"]:
            break
        await asyncio.sleep(0.05)
    assert job_guard.snapshot()["jobs"]["price_alerts"]["last_cleanup_error"] == "RuntimeError"


# --- 4. slot recovery --------------------------------------------------------

async def test_the_slot_is_free_for_the_next_run_immediately():
    """The whole point: after the limit, the same job runs again normally."""
    await _elapsed(_cleanup_never)

    async def quick():
        await asyncio.sleep(0.02)
        return "ikinci kosu"

    t0 = time.perf_counter()
    assert await run_with_deadline("price_alerts", quick(),
                                   budget=BUDGET, cleanup_grace=GRACE) == "ikinci kosu"
    assert time.perf_counter() - t0 < BUDGET


async def test_repeated_deadline_hits_do_not_accumulate_delay():
    """Three stuck runs back to back must each release on time — otherwise a
    persistent upstream fault re-creates the original wedge."""
    for i in range(3):
        _, dt = await _elapsed(_cleanup_never)
        assert dt <= LIMIT + SLACK, f"{i+1}. kosu {dt:.2f}s"
    assert job_guard.snapshot()["jobs"]["price_alerts"]["cleanup_overrun_count"] == 3


# --- 5. child tasks and threads ---------------------------------------------

async def test_a_child_task_is_cancelled_with_its_parent():
    child_cancelled = asyncio.Event()

    async def child():
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            child_cancelled.set()
            raise

    async def body():
        async with asyncio.TaskGroup() as tg:
            tg.create_task(child())

    await _elapsed(body)
    assert child_cancelled.is_set(), "child task parent ile iptal edilmedi"


async def test_a_blocking_thread_does_not_hold_the_slot_but_is_not_killed():
    """Honest about the limit of the fix.

    A thread inside a blocking syscall cannot be killed from Python. The guard
    stops WAITING for it, so the scheduler slot is released on time — but the
    thread keeps running. Asserting both halves so the report cannot claim the
    thread was stopped.
    """
    release = threading.Event()
    thread_finished = threading.Event()

    def blocking():
        release.wait(10)
        thread_finished.set()

    async def body():
        await asyncio.to_thread(blocking)

    try:
        outcome, dt = await _elapsed(body)
        assert outcome == "deadline"
        assert dt <= LIMIT + SLACK, f"slot {dt:.2f}s'de birakildi"
        assert not thread_finished.is_set(), "thread beklenmedik sekilde bitmis"
    finally:
        release.set()


# --- 6. external cancellation ------------------------------------------------

async def test_shutdown_cancellation_is_not_reported_as_a_deadline():
    started = asyncio.Event()

    async def body():
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(run_with_deadline("signals_1h", body(),
                                                 budget=30.0, cleanup_grace=GRACE))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_shutdown_also_cancels_the_body():
    """A shutdown that leaves the body running would keep working against a
    closing process."""
    started = asyncio.Event()
    body_cancelled = asyncio.Event()

    async def body():
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            body_cancelled.set()
            raise

    task = asyncio.create_task(run_with_deadline("signals_1h", body(),
                                                 budget=30.0, cleanup_grace=GRACE))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert body_cancelled.is_set(), "shutdown is govdesini iptal etmedi"


# --- 7. per-asset guard has the same bound -----------------------------------

async def test_the_per_asset_guard_is_hard_bounded_too():
    async def body():
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.Event().wait()

    t0 = time.perf_counter()
    ok = await run_asset_with_deadline("signals_15m", "STUCK", "15m", body(),
                                       budget=BUDGET, cleanup_grace=GRACE)
    dt = time.perf_counter() - t0
    assert ok is False
    assert dt <= LIMIT + SLACK, f"varlik {dt:.2f}s tuttu"
    assert job_guard.snapshot()["jobs"]["signals_15m"]["cleanup_overrun_count"] == 1


async def test_a_stuck_asset_does_not_delay_the_next_asset():
    async def stuck():
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.Event().wait()

    async def fine():
        await asyncio.sleep(0.02)

    await run_asset_with_deadline("signals_15m", "A", "15m", stuck(),
                                  budget=BUDGET, cleanup_grace=GRACE)
    t0 = time.perf_counter()
    assert await run_asset_with_deadline("signals_15m", "B", "15m", fine(),
                                         budget=BUDGET, cleanup_grace=GRACE) is True
    assert time.perf_counter() - t0 < BUDGET


# --- 8. configuration invariants --------------------------------------------

async def test_budget_plus_grace_still_fits_inside_every_cadence():
    """Budget alone fitting the cadence is no longer enough — the wall-clock
    limit is budget + grace, and that is what must clear the next trigger."""
    for job_id, spec in JOB_SPECS.items():
        if spec.cadence_seconds is None:
            continue
        limit = spec.budget_seconds + CLEANUP_GRACE_SECONDS
        assert limit < spec.cadence_seconds, (
            f"{job_id}: butce+grace {limit}s >= cadence {spec.cadence_seconds}s"
        )


async def test_cleanup_grace_is_far_above_measured_cleanup_cost():
    """Measured 2026-07-28: the slowest healthy cleanup step (httpx aclose on an
    unused client) was 6.05ms. The grace must not be so tight that a healthy
    release trips it."""
    slowest_measured_seconds = 0.00605
    assert CLEANUP_GRACE_SECONDS >= slowest_measured_seconds * 100
    assert CLEANUP_GRACE_SECONDS <= 30, "grace cadence butcesini yiyecek kadar buyuk"


async def test_the_guard_no_longer_awaits_the_body_inline():
    """Structural, on the AST: the body must be driven as a Task, because you
    cannot stop waiting for a bare `await`. This is the whole fix."""
    src = textwrap.dedent(inspect.getsource(run_with_deadline))
    tree = __import__("ast").parse(src)
    calls = {getattr(n.func, "attr", None) for n in __import__("ast").walk(tree)
             if isinstance(n, __import__("ast").Call)}
    assert "ensure_future" in calls or "create_task" in calls, \
        "govde Task olarak calistirilmiyor — beklemeyi birakmak imkansiz"
    assert "wait" in calls, "asyncio.wait ile sinirli bekleme yok"


async def test_health_exposes_the_cleanup_contract():
    from app.main import health_check

    body = await health_check()
    assert body["status"] == "healthy"
    assert body["service"] == "zatetrade-backend"
    s = body["scheduler"]
    assert s["cleanup_grace_seconds"] == CLEANUP_GRACE_SECONDS
    assert "orphan_task_count" in s
    for job in s["jobs"].values():
        assert job["wall_clock_limit_seconds"] == job["budget_seconds"] + CLEANUP_GRACE_SECONDS
