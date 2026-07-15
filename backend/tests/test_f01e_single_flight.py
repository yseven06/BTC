"""CP-F0-1E: at most one tracking pass runs at a time.

Three callers reach the tracker (cron, admin trigger_job_now, and the manual
endpoint) and only cron-vs-cron was protected. These lock the guard's contract:
the second concurrent caller SKIPS rather than waits, the successful path's
return value is untouched, and a raising pass still releases the flag.
"""
import asyncio
from unittest.mock import AsyncMock

import pytest

from app.backtesting import tracker


@pytest.fixture(autouse=True)
def _clean_flag():
    """Never let one test's flag leak into the next."""
    tracker._tracking_in_flight = False
    yield
    tracker._tracking_in_flight = False


def _slow_impl(gate: asyncio.Event, calls: list):
    async def impl(db):
        calls.append(db)
        await gate.wait()                      # hold the pass open
        return {"processed": 7, "resolved": 2, "details": ["x"]}
    return impl


# ── 1/2 · Concurrency: one runs, the other skips without touching the DB ─────
@pytest.mark.asyncio
async def test_second_concurrent_call_skips_and_never_reaches_the_body(monkeypatch):
    gate, calls = asyncio.Event(), []
    monkeypatch.setattr(tracker, "_track_and_resolve_active_signals_impl", _slow_impl(gate, calls))
    db_a, db_b = AsyncMock(), AsyncMock()

    first = asyncio.create_task(tracker.track_and_resolve_active_signals(db_a))
    await asyncio.sleep(0)                     # let `first` reach the gate
    second = await tracker.track_and_resolve_active_signals(db_b)

    assert second == {"processed": 0, "resolved": 0, "details": [], "skipped": True}
    assert calls == [db_a]                     # the body ran exactly once…
    assert db_b.execute.await_count == 0       # …and the skipped call did no DB work

    gate.set()
    assert (await first)["resolved"] == 2      # the winner still returns its real result


@pytest.mark.asyncio
async def test_many_concurrent_callers_yield_exactly_one_pass(monkeypatch):
    """cron + admin trigger + endpoint can all land in the same tick."""
    gate, calls = asyncio.Event(), []
    monkeypatch.setattr(tracker, "_track_and_resolve_active_signals_impl", _slow_impl(gate, calls))

    winner = asyncio.create_task(tracker.track_and_resolve_active_signals(AsyncMock()))
    await asyncio.sleep(0)
    others = await asyncio.gather(*(tracker.track_and_resolve_active_signals(AsyncMock())
                                    for _ in range(5)))

    assert len(calls) == 1
    assert all(r["skipped"] is True for r in others)
    gate.set()
    await winner


# ── 3 · The successful path's contract is untouched ──────────────────────────
@pytest.mark.asyncio
async def test_normal_call_returns_the_pre_cp_dict_verbatim(monkeypatch):
    """No `skipped` key on the happy path — callers read this dict as-is."""
    payload = {"processed": 3, "resolved": 1, "details": [{"symbol": "BTCUSDT"}]}

    async def impl(db):
        return payload

    monkeypatch.setattr(tracker, "_track_and_resolve_active_signals_impl", impl)
    out = await tracker.track_and_resolve_active_signals(AsyncMock())

    assert out == payload and out is payload   # passed through, not rebuilt
    assert "skipped" not in out


@pytest.mark.asyncio
async def test_sequential_calls_both_run(monkeypatch):
    """The guard must not latch — back-to-back calls are not concurrent."""
    calls = []

    async def impl(db):
        calls.append(db)
        return {"processed": 0, "resolved": 0, "details": []}

    monkeypatch.setattr(tracker, "_track_and_resolve_active_signals_impl", impl)
    for _ in range(3):
        out = await tracker.track_and_resolve_active_signals(AsyncMock())
        assert "skipped" not in out
    assert len(calls) == 3


# ── 4 · Failure must not wedge the tracker forever ───────────────────────────
@pytest.mark.asyncio
async def test_exception_releases_the_flag_and_propagates(monkeypatch):
    """A failed commit/collector must not leave the flag stuck True.

    _run_tracked relies on the exception surfacing to mark the job errored, so the
    guard has to re-raise, not swallow.
    """
    async def boom(db):
        raise RuntimeError("commit failed")

    monkeypatch.setattr(tracker, "_track_and_resolve_active_signals_impl", boom)
    with pytest.raises(RuntimeError, match="commit failed"):
        await tracker.track_and_resolve_active_signals(AsyncMock())

    assert tracker._tracking_in_flight is False        # released by `finally`

    # …and the tracker still works afterwards (the real regression this prevents).
    async def ok(db):
        return {"processed": 1, "resolved": 0, "details": []}

    monkeypatch.setattr(tracker, "_track_and_resolve_active_signals_impl", ok)
    assert (await tracker.track_and_resolve_active_signals(AsyncMock()))["processed"] == 1


@pytest.mark.asyncio
async def test_flag_is_false_after_a_normal_pass(monkeypatch):
    async def impl(db):
        assert tracker._tracking_in_flight is True     # held DURING the pass
        return {"processed": 0, "resolved": 0, "details": []}

    monkeypatch.setattr(tracker, "_track_and_resolve_active_signals_impl", impl)
    await tracker.track_and_resolve_active_signals(AsyncMock())
    assert tracker._tracking_in_flight is False


# ── 6 · The endpoint turns a skip into 200, not 500 ──────────────────────────
@pytest.mark.asyncio
async def test_endpoint_maps_skipped_to_a_200_message(monkeypatch):
    from app.api.routes import signals as signals_route

    async def skipped(db):
        return {"processed": 0, "resolved": 0, "details": [], "skipped": True}

    monkeypatch.setattr(signals_route, "track_and_resolve_active_signals", skipped)
    resp = await signals_route.manual_track_performance(db=AsyncMock(), current_user=object())

    assert resp["status"] == "skipped"          # no HTTPException → no 500
    assert "zaten çalışıyor" in resp["message"]
    assert resp["details"] == []


@pytest.mark.asyncio
async def test_endpoint_success_path_is_unchanged(monkeypatch):
    from app.api.routes import signals as signals_route

    async def ok(db):
        return {"processed": 5, "resolved": 2, "details": [{"symbol": "ETHUSDT"}]}

    monkeypatch.setattr(signals_route, "track_and_resolve_active_signals", ok)
    resp = await signals_route.manual_track_performance(db=AsyncMock(), current_user=object())

    assert resp["status"] == "success"
    assert resp["message"] == "Processed 5 active signals. Resolved 2."
    assert resp["details"] == [{"symbol": "ETHUSDT"}]
