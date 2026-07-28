"""Bounded execution and liveness accounting for scheduled jobs.

Every individual HTTP request in this codebase is ALREADY bounded: all ten
httpx clients are constructed with an explicit timeout (5-15s), and the one
synchronous caller (yfinance) is dispatched through asyncio.to_thread. The DB
side is bounded too — pool_timeout=20, command_timeout=90, TCP keepalive.

What was never bounded is the JOB. A 15m sweep walks 57 assets sequentially and
each asset makes 13 upstream requests across 6 hosts (Binance klines x4, FRED
x4, alternative.me, blockchain.info, mempool.space x2, CoinGecko). When upstream
degrades those per-request timeouts multiply rather than cancel out:

    13 requests x 10s x 57 assets = 124 minutes, on a 15-minute cadence.

APScheduler's max_instances=1 then refuses every subsequent trigger and
coalesce=True drops it silently, so one slow sweep suppresses all later ones for
as long as upstream stays degraded. That is what happened on 2026-07-28: the
sweep last succeeded at 10:36:49, the 10:47 run never returned, and the 11:02
and 11:17 runs were skipped. `/health` answered 200 in 4ms throughout, because
it reports process liveness and has never known the scheduler exists.

So the bound belongs at the job boundary, not on the request — the requests were
never the unbounded part. Budgets below are set from measured production
durations, not guessed.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class JobDeadlineExceeded(Exception):
    """A job ran past its whole-job budget and was cancelled."""

    def __init__(self, job_id: str, budget: float) -> None:
        super().__init__(f"job '{job_id}' exceeded its {budget:.0f}s budget")
        self.job_id = job_id
        self.budget = budget


@dataclass(frozen=True)
class JobSpec:
    """Budget and cadence for one scheduled job.

    `budget` must stay comfortably BELOW `cadence`: a job that outlives its own
    cadence blocks its successor under max_instances=1, which is the failure
    this module exists to prevent. Values are derived from the healthy-window
    distribution measured in production on 2026-07-28 (n = 68 runs over 3.3h):

        job                     p50      p90      max     cadence   budget
        price_alerts            0.9s     2.1s     3.3s        60s      30s
        perf_tracking          12.3s    17.8s    23.4s       120s      90s
        signals_15m           259.7s   320.3s   320.3s       900s     600s
        signals_1h            259.1s        -   259.1s      3600s     900s
        signals_4h            262.0s        -   262.0s     14400s     900s

    Each budget is at least 1.9x the observed maximum and at most 75% of the
    cadence, so a legitimately slow-but-working run still finishes while a
    degraded one is cut before it can suppress the next trigger.
    """

    budget_seconds: float
    cadence_seconds: Optional[float]
    critical: bool


# The per-asset bound inside a sweep. Measured cost is ~4.6-5.6s per asset
# (259-320s / 57); 45s is ~9x that and well under the 130s an all-timeouts asset
# would otherwise burn. It limits blast radius — the whole-job budget is what
# actually guarantees the cadence.
PER_ASSET_BUDGET_SECONDS = 45.0

# How long a cancelled job may spend releasing its resources before the guard
# stops waiting for it.
#
# CP-HTTP-RESILIENCE-1's deadline was SOFT: asyncio.timeout starts the
# cancellation on time, but `async with` does not return until the coroutine has
# finished unwinding, so an unbounded `finally` made the deadline unbounded too.
# Measured on 2026-07-28: a 30s budget released its slot after 127.1s, and a
# later run was still holding the slot 1363s in. Reproduced exactly — a body
# with no cleanup returns at 0.50s against a 0.5s budget (hard), one with a 2s
# cleanup returns at 2.52s (soft), one whose cleanup never finishes never
# returns at all.
#
# So the guard now waits for cleanup only this long. Measured healthy cleanup
# cost, which is what this has to cover:
#
#   httpx aclose(), unused client        p50 0.03ms  p90 0.04ms  max 6.05ms
#   httpx aclose(), 2 live keepalives    p50 0.10ms  p90 0.11ms  max 0.11ms
#   httpx aclose(), cancelled request    p50 0.01ms  p90 0.02ms  max 0.02ms
#
# 5s is ~800x the slowest measured step, so no healthy cleanup can trip it,
# while budget + grace stays below every job's cadence (price_alerts 35s < 60s,
# perf_tracking 95s < 120s, signals_15m 605s < 900s).
CLEANUP_GRACE_SECONDS = 5.0

# How far past its cadence a critical job may go before liveness calls it stale.
# 2.5x means price_alerts (60s) is flagged after 150s and signals_15m (900s)
# after ~37 min — both well inside the 45-minute outage that went unnoticed.
STALE_CADENCE_MULTIPLIER = 2.5

JOB_SPECS: Dict[str, JobSpec] = {
    "signals_15m":   JobSpec(600.0, 900.0, critical=True),
    "signals_1h":    JobSpec(900.0, 3600.0, critical=True),
    "signals_4h":    JobSpec(900.0, 14400.0, critical=False),
    "signals_1d":    JobSpec(900.0, 86400.0, critical=False),
    "perf_tracking": JobSpec(90.0, 120.0, critical=True),
    "price_alerts":  JobSpec(30.0, 60.0, critical=True),
    "startup_check": JobSpec(900.0, None, critical=False),
}

# Fallback for a job id with no spec — bounded rather than unbounded, which is
# the whole point. Deliberately not "infinity if unknown".
DEFAULT_BUDGET_SECONDS = 300.0


def budget_for(job_id: str) -> float:
    spec = JOB_SPECS.get(job_id)
    return spec.budget_seconds if spec else DEFAULT_BUDGET_SECONDS


# --------------------------------------------------------------------------- #
# upstream error classification
# --------------------------------------------------------------------------- #

TIMEOUT = "timeout"
DNS = "dns"
CONNECT = "connect"
HTTP_STATUS = "http_status"
DEADLINE = "deadline"
OTHER = "other"


def classify_upstream_error(exc: BaseException) -> str:
    """Bucket an exception so the counters mean something.

    Order matters: httpx.ConnectTimeout subclasses both TimeoutException and
    TransportError, and a DNS failure surfaces as ConnectError wrapping
    socket.gaierror — so gaierror is checked before the broader ConnectError.
    """
    if isinstance(exc, JobDeadlineExceeded):
        return DEADLINE
    if isinstance(exc, socket.gaierror):
        return DNS
    if isinstance(exc, httpx.TimeoutException):
        return TIMEOUT
    if isinstance(exc, httpx.ConnectError):
        cause = exc.__cause__ or exc.__context__
        if isinstance(cause, socket.gaierror) or "name resolution" in str(exc).lower():
            return DNS
        return CONNECT
    if isinstance(exc, httpx.HTTPStatusError):
        return HTTP_STATUS
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return TIMEOUT
    # asyncpg/anyio wrap the resolver error rather than raising gaierror itself.
    if "name resolution" in str(exc).lower() or "temporary failure in name" in str(exc).lower():
        return DNS
    return OTHER


# --------------------------------------------------------------------------- #
# liveness registry (in-process; no table, no migration)
# --------------------------------------------------------------------------- #

@dataclass
class _Liveness:
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    success_at: Optional[str] = None
    running: bool = False
    running_since_monotonic: Optional[float] = None
    consecutive_failures: int = 0
    missed_or_skipped: int = 0
    deadline_exceeded: int = 0
    upstream_timeouts: int = 0
    upstream_dns_errors: int = 0
    assets_skipped: int = 0
    last_error_kind: Optional[str] = None
    # CP-HTTP-RESILIENCE-2 — cancellation and cleanup are separate phases, and
    # conflating them is what hid the 30s -> 127s gap. These say which one ran long.
    cancellation_requested_at: Optional[str] = None
    cleanup_started_at: Optional[str] = None
    cleanup_completed_at: Optional[str] = None
    cleanup_duration_seconds: Optional[float] = None
    cleanup_overrun: int = 0
    forced_cleanup: int = 0
    orphan_tasks: int = 0
    deadline_overrun_seconds: Optional[float] = None
    slot_release_seconds: Optional[float] = None
    last_cleanup_error: Optional[str] = None


_STATE: Dict[str, _Liveness] = {}
_PROCESS_START = time.monotonic()

# Strong references to tasks the guard stopped waiting for. A task with no live
# reference can be garbage-collected mid-flight and vanish silently, so an
# abandoned cleanup is HELD here until it finishes — abandoned by the scheduler,
# not by the process. Counted and logged rather than forgotten.
_ORPHANS: "set[asyncio.Task[Any]]" = set()


def _abandon(job_id: str, task: "asyncio.Task[Any]") -> None:
    """Stop waiting for `task`, but keep it observable until it really ends."""
    _ORPHANS.add(task)
    e = _entry(job_id)
    e.orphan_tasks += 1
    e.forced_cleanup += 1

    def _done(t: "asyncio.Task[Any]") -> None:
        _ORPHANS.discard(t)
        ent = _entry(job_id)
        ent.orphan_tasks = max(0, ent.orphan_tasks - 1)
        if t.cancelled():
            logger.warning("[JobGuard] job=%s terk edilen cleanup sonunda iptal edildi", job_id)
            return
        exc = t.exception()
        if exc is not None:
            ent.last_cleanup_error = type(exc).__name__
            logger.warning("[JobGuard] job=%s terk edilen cleanup %s ile bitti",
                           job_id, type(exc).__name__)
        else:
            logger.info("[JobGuard] job=%s terk edilen cleanup sonunda tamamlandi", job_id)

    task.add_done_callback(_done)


def orphan_count() -> int:
    """Tasks the guard has stopped waiting for and that have not ended yet."""
    return len(_ORPHANS)


def _entry(job_id: str) -> _Liveness:
    return _STATE.setdefault(job_id, _Liveness())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def reset_for_tests() -> None:
    """Clear accumulated liveness. Test-only; production never calls this."""
    _STATE.clear()
    for t in list(_ORPHANS):
        t.cancel()
    _ORPHANS.clear()


def record_start(job_id: str) -> None:
    e = _entry(job_id)
    e.started_at = _now_iso()
    e.running = True
    e.running_since_monotonic = time.monotonic()


def record_success(job_id: str) -> None:
    e = _entry(job_id)
    e.finished_at = e.success_at = _now_iso()
    e.running = False
    e.running_since_monotonic = None
    e.consecutive_failures = 0
    e.last_error_kind = None


def record_failure(job_id: str, exc: BaseException) -> str:
    kind = classify_upstream_error(exc)
    e = _entry(job_id)
    e.finished_at = _now_iso()
    e.running = False
    e.running_since_monotonic = None
    e.consecutive_failures += 1
    e.last_error_kind = kind
    if kind == DEADLINE:
        e.deadline_exceeded += 1
    elif kind == TIMEOUT:
        e.upstream_timeouts += 1
    elif kind == DNS:
        e.upstream_dns_errors += 1
    return kind


def record_missed(job_id: str) -> None:
    """A trigger APScheduler refused — max_instances or a missed fire time."""
    _entry(job_id).missed_or_skipped += 1


def record_asset_skipped(job_id: str, exc: BaseException) -> str:
    """One asset gave up inside a sweep; the sweep itself carries on."""
    kind = classify_upstream_error(exc)
    e = _entry(job_id)
    e.assets_skipped += 1
    if kind == TIMEOUT or kind == DEADLINE:
        e.upstream_timeouts += 1
    elif kind == DNS:
        e.upstream_dns_errors += 1
    return kind


def _running_seconds(e: _Liveness) -> Optional[float]:
    if not e.running or e.running_since_monotonic is None:
        return None
    return round(time.monotonic() - e.running_since_monotonic, 1)


def _is_stale(job_id: str, e: _Liveness) -> bool:
    """Has a critical job gone too long without succeeding?

    Before the first success the process uptime stands in for "time since last
    success", so a fresh boot is not instantly stale but a job that has NEVER
    succeeded still surfaces once it is overdue.
    """
    spec = JOB_SPECS.get(job_id)
    if spec is None or not spec.critical or spec.cadence_seconds is None:
        return False
    limit = spec.cadence_seconds * STALE_CADENCE_MULTIPLIER
    if e.success_at is None:
        return (time.monotonic() - _PROCESS_START) > limit
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(e.success_at)).total_seconds()
    except ValueError:
        return False
    return age > limit


def snapshot() -> Dict[str, Any]:
    """JSON-safe scheduler liveness for /health. Never raises."""
    jobs: Dict[str, Any] = {}
    stale_jobs = []
    overrunning = []
    for job_id, spec in JOB_SPECS.items():
        e = _STATE.get(job_id, _Liveness())
        running_s = _running_seconds(e)
        stale = _is_stale(job_id, e)
        over = running_s is not None and running_s > spec.budget_seconds
        if stale:
            stale_jobs.append(job_id)
        if over:
            overrunning.append(job_id)
        jobs[job_id] = {
            "critical": spec.critical,
            "budget_seconds": spec.budget_seconds,
            "cadence_seconds": spec.cadence_seconds,
            "cleanup_grace_seconds": CLEANUP_GRACE_SECONDS,
            "wall_clock_limit_seconds": spec.budget_seconds + CLEANUP_GRACE_SECONDS,
            "last_started_at": e.started_at,
            "last_finished_at": e.finished_at,
            "last_success_at": e.success_at,
            "currently_running": e.running,
            "running_duration_seconds": running_s,
            "consecutive_failures": e.consecutive_failures,
            "missed_or_skipped_count": e.missed_or_skipped,
            "deadline_exceeded_count": e.deadline_exceeded,
            "upstream_timeout_count": e.upstream_timeouts,
            "upstream_dns_error_count": e.upstream_dns_errors,
            "assets_skipped_count": e.assets_skipped,
            "last_error_kind": e.last_error_kind,
            "stale": stale,
            # Cancellation vs cleanup, kept apart: a job that overran its budget
            # and one whose cleanup would not finish need different answers, and
            # the previous single "deadline exceeded" counter could not tell them
            # apart.
            "cancellation_requested_at": e.cancellation_requested_at,
            "cleanup_started_at": e.cleanup_started_at,
            "cleanup_completed_at": e.cleanup_completed_at,
            "cleanup_duration_seconds": e.cleanup_duration_seconds,
            "cleanup_overrun_count": e.cleanup_overrun,
            "forced_cleanup_count": e.forced_cleanup,
            "orphan_task_count": e.orphan_tasks,
            "deadline_overrun_seconds": e.deadline_overrun_seconds,
            "slot_release_seconds": e.slot_release_seconds,
            "last_cleanup_error": e.last_cleanup_error,
        }
    return {
        "degraded": bool(stale_jobs or overrunning or _ORPHANS),
        "critical_job_stale": bool(stale_jobs),
        "stale_jobs": stale_jobs,
        "overrunning_jobs": overrunning,
        "cleanup_grace_seconds": CLEANUP_GRACE_SECONDS,
        "orphan_task_count": len(_ORPHANS),
        "jobs": jobs,
    }


# --------------------------------------------------------------------------- #
# the bound itself
# --------------------------------------------------------------------------- #

async def run_with_deadline(job_id: str, coro: Awaitable[Any],
                            budget: Optional[float] = None,
                            cleanup_grace: Optional[float] = None) -> Any:
    """Run `coro`, and return within `budget + cleanup_grace` no matter what.

    Two separate phases, because conflating them is what made the previous
    deadline soft:

      business  — up to `budget`. Overrunning here cancels the work.
      cleanup   — up to `cleanup_grace`, and ONLY resource release. If the
                  coroutine has not finished unwinding by then the guard stops
                  waiting, releases the scheduler slot, and hands the task to
                  the orphan registry.

    The earlier version awaited the body inside `async with asyncio.timeout(...)`.
    That block does not return until the coroutine has finished unwinding, so a
    `finally` that blocked forever held the slot forever — measured in
    production at 127.1s against a 30s budget, and once at 1363s and counting.
    Here the wait is on a Task, so declining to wait any longer is possible.

    An abandoned task is NOT forgotten: a strong reference is kept (an unheld
    task can be garbage-collected mid-flight and disappear), it is counted in
    telemetry, and its eventual outcome is logged.

    A CancelledError from outside — process shutdown, an outer cancel — still
    propagates unchanged; the body is cancelled first so shutdown does not leave
    work running, but the error is never relabelled as a deadline.
    """
    limit = budget_for(job_id) if budget is None else budget
    grace = CLEANUP_GRACE_SECONDS if cleanup_grace is None else cleanup_grace
    started = time.monotonic()
    entry = _entry(job_id)
    task: "asyncio.Task[Any]" = asyncio.ensure_future(coro)

    try:
        done, _ = await asyncio.wait({task}, timeout=limit)
    except asyncio.CancelledError:
        task.cancel()
        _, pending = await asyncio.wait({task}, timeout=grace)
        if pending:
            _abandon(job_id, task)
        raise

    if done:
        entry.slot_release_seconds = round(time.monotonic() - started, 3)
        entry.deadline_overrun_seconds = None
        return task.result()          # re-raises whatever the body raised

    # --- budget spent: cancel the work, then bound the unwinding ---
    cancel_at = time.monotonic()
    entry.cancellation_requested_at = _now_iso()
    entry.cleanup_started_at = entry.cancellation_requested_at
    task.cancel()

    _, pending = await asyncio.wait({task}, timeout=grace)
    cleanup_seconds = time.monotonic() - cancel_at
    entry.cleanup_duration_seconds = round(cleanup_seconds, 3)

    if pending:
        entry.cleanup_overrun += 1
        entry.cleanup_completed_at = None
        _abandon(job_id, task)
        logger.error(
            "[JobGuard] job=%s deadline=%.0fs cleanup_grace=%.0fs — cleanup asildi, "
            "slot zorla serbest birakildi, gorev orphan kaydina alindi",
            job_id, limit, grace,
        )
    else:
        entry.cleanup_completed_at = _now_iso()
        if task.cancelled() is False and task.exception() is not None:
            entry.last_cleanup_error = type(task.exception()).__name__

    total = time.monotonic() - started
    entry.slot_release_seconds = round(total, 3)
    entry.deadline_overrun_seconds = round(total - limit, 3)
    logger.error(
        "[JobGuard] job=%s deadline=%.0fs toplam=%.1fs cleanup=%.2fs%s — slot serbest",
        job_id, limit, total, cleanup_seconds, " (CLEANUP ASIMI)" if pending else "",
    )
    raise JobDeadlineExceeded(job_id, limit)


async def run_asset_with_deadline(job_id: str, symbol: str, timeframe: str,
                                  coro: Awaitable[Any],
                                  budget: Optional[float] = None,
                                  cleanup_grace: Optional[float] = None) -> bool:
    """Run one asset's work under its own bound.

    Returns True if it finished, False if it was given up on. A False here is
    the same outcome the sweep already had for an asset whose generation raised:
    no candidate is written and nothing is fabricated. Explicitly NOT a fallback
    to stale or invented data — a timed-out asset produces no signal at all.

    `budget` resolves at call time rather than in the signature default, so the
    module constant is the single source of truth and a test can move it.
    """
    budget = PER_ASSET_BUDGET_SECONDS if budget is None else budget
    grace = CLEANUP_GRACE_SECONDS if cleanup_grace is None else cleanup_grace
    task: "asyncio.Task[Any]" = asyncio.ensure_future(coro)

    try:
        done, _ = await asyncio.wait({task}, timeout=budget)
    except asyncio.CancelledError:
        task.cancel()
        _, pending = await asyncio.wait({task}, timeout=grace)
        if pending:
            _abandon(job_id, task)
        raise

    if done:
        try:
            task.result()
            return True
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — one asset must not end the sweep
            kind = record_asset_skipped(job_id, exc)
            logger.warning(
                "[JobGuard] job=%s symbol=%s timeframe=%s kind=%s error=%s — asset skipped",
                job_id, symbol, timeframe, kind, type(exc).__name__,
            )
            return False

    # The asset outlived its budget. Same two-phase shape as the whole-job
    # guard: cancel, then bound the unwinding so one asset cannot hold the
    # sweep — which is what it would do if its cleanup never finished.
    task.cancel()
    _, pending = await asyncio.wait({task}, timeout=grace)
    kind = record_asset_skipped(job_id, asyncio.TimeoutError())
    if pending:
        _entry(job_id).cleanup_overrun += 1
        _abandon(job_id, task)
    logger.warning(
        "[JobGuard] job=%s symbol=%s timeframe=%s budget=%.0fs kind=%s — asset skipped%s",
        job_id, symbol, timeframe, budget, kind,
        " (cleanup asimi, orphan)" if pending else "",
    )
    return False
