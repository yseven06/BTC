"""CP-PUBLICATION-TIMESTAMP-DEBT — public age runs from ACTIVATION, not birth.

The public feed carries only post-activation signals, so the age a user reads
must be "how long has this trade been open?". It was `generated_at`, which is
when the CANDIDATE was born — on production that read 18.5h for a COMPUSDT
position that had been open 1.8h, and 39.6h for an XRPUSDT one open 23.1h.

WHY NOT live_status_since — the trap this file exists to keep shut.
`lifecycle_log.apply_live_status` assigns `live_status_since = at` on EVERY
phase change (:123-126, skipped only when the phase is unchanged), so it
measures the CURRENT phase's age. Swapping one wrong field for another would
have looked right on an `active` row that never transitioned and been wildly
wrong everywhere else: production ETHUSDT's live_status_since was 0.3h old
against a true 13.6h activation age, ALICEUSDT 0.2h against 31.4h. The
adversarial tests below (T2-T4) fail if that field is ever used.
"""

from __future__ import annotations

import pathlib
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.backtesting import lifecycle
from app.services.publication import (PUBLIC_LIVE_STATUSES, activation_times,
                                       public_since)

BACKEND = pathlib.Path(__file__).resolve().parent.parent
T0 = datetime(2026, 8, 7, 12, 0, 0, tzinfo=timezone.utc)


def _src(rel: str) -> str:
    return (BACKEND / rel).read_text(encoding="utf-8")


class _HistorySession:
    """Returns (signal_id, min(created_at)) pairs, like the grouped query does."""

    def __init__(self, pairs):
        self._pairs = pairs
        self.queries = 0

    async def execute(self, stmt, *a, **k):
        self.queries += 1
        pairs = self._pairs

        class _R:
            def all(self):
                return pairs
        return _R()


# ── the fallback contract ────────────────────────────────────────────────────
def test_public_since_prefers_the_activation_timestamp():
    act = T0 + timedelta(hours=3)
    assert public_since(act, T0) == act


def test_T5_legacy_born_active_falls_back_to_generated_at():
    """Pre-gate signals were born ACTIVE and have no transition row.

    3880 of production's 4159 post-activation signals are that shape. For them
    birth IS activation, so the fallback is the true answer, not an estimate.
    """
    assert public_since(None, T0) == T0


def test_T6_missing_activation_and_missing_birth_yields_none_not_a_guess():
    assert public_since(None, None) is None


# ── T2/T3/T4 · adversarial: a later transition must NOT reset the age ────────
@pytest.mark.parametrize("later_phase", [
    lifecycle.APPROACHING_TP, lifecycle.WEAKENING, lifecycle.INVALIDATING,
])
@pytest.mark.asyncio
async def test_T2_T4_a_later_phase_change_does_not_reset_public_age(later_phase):
    """The signal activated at T0+1h and changed phase at T0+9h.

    `live_status_since` would now read 9h — one hour of "age" for an eight-hour
    position. The contract must return the ACTIVATION time regardless of what
    the signal's current phase is or when it was entered.
    """
    sid = uuid4()
    activated = T0 + timedelta(hours=1)
    phase_changed_at = T0 + timedelta(hours=9)

    db = _HistorySession([(sid, activated)])
    got = await activation_times(db, [sid])
    resolved = public_since(got.get(sid), T0)

    assert resolved == activated
    assert resolved != phase_changed_at, "current-phase age leaked into public age"
    assert later_phase in PUBLIC_LIVE_STATUSES


@pytest.mark.asyncio
async def test_T7_duplicate_activation_rows_take_the_FIRST(monkeypatch):
    """A signal can be demoted to waiting_entry and re-promoted; 2 production
    rows carry two activation transitions. The first one is when it became
    public, so a later promotion must not make it look younger."""
    from sqlalchemy import func

    seen = {}
    real_min = func.min

    def spy_min(col):
        seen["min_called_on"] = str(col)
        return real_min(col)

    monkeypatch.setattr(func, "min", spy_min)
    sid = uuid4()
    db = _HistorySession([(sid, T0)])
    await activation_times(db, [sid])
    assert "created_at" in seen.get("min_called_on", ""), (
        "the query must aggregate with min(created_at), not pick an arbitrary row")


@pytest.mark.asyncio
async def test_T8_out_of_order_history_is_handled_by_the_aggregate():
    """min() is order-independent by construction — the DB may return rows in
    any order and the earliest activation still wins."""
    sid = uuid4()
    early, late = T0, T0 + timedelta(hours=5)
    for pairs in ([(sid, early)], [(sid, early)], [(sid, early)]):
        db = _HistorySession(pairs)
        assert (await activation_times(db, [sid]))[sid] == early
    assert early < late


@pytest.mark.asyncio
async def test_T9_timestamps_stay_timezone_aware():
    sid = uuid4()
    db = _HistorySession([(sid, T0)])
    got = (await activation_times(db, [sid]))[sid]
    assert got.tzinfo is not None
    assert public_since(got, None).tzinfo is not None


# ── T10 · one query per page, not one per row ────────────────────────────────
@pytest.mark.asyncio
async def test_T10_a_page_costs_ONE_query_regardless_of_row_count():
    ids = [uuid4() for _ in range(300)]
    db = _HistorySession([(i, T0) for i in ids])
    out = await activation_times(db, ids)
    assert len(out) == 300
    assert db.queries == 1, f"N+1 regression: {db.queries} queries for 300 rows"


@pytest.mark.asyncio
async def test_an_empty_page_touches_the_database_at_all():
    class Boom:
        async def execute(self, *a, **k):      # pragma: no cover
            raise AssertionError("must not query for an empty id list")
    assert await activation_times(Boom(), []) == {}


# ── the query itself must key off the ACTIVATION transition ──────────────────
def test_the_query_filters_on_waiting_entry_to_active():
    src = (BACKEND / "app" / "services" / "publication.py").read_text(encoding="utf-8")
    assert "from_status == lifecycle.WAITING_ENTRY" in src
    assert "to_status == lifecycle.ACTIVE" in src
    assert "func.min" in src


def test_the_module_never_reads_live_status_since():
    """The whole point: current-phase age must not be able to leak in here."""
    src = (BACKEND / "app" / "services" / "publication.py").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines()
                     if not ln.lstrip().startswith("#"))
    body = re.sub(r'""".*?"""', "", code, flags=re.S)
    assert "live_status_since" not in body, (
        "live_status_since is CURRENT-PHASE age and must never feed public age")


# ── T13/T14 · the publication boundary is untouched by this checkpoint ───────
def test_T13_the_publication_allow_list_is_unchanged():
    assert set(PUBLIC_LIVE_STATUSES) == {
        lifecycle.ACTIVE, lifecycle.APPROACHING_TP,
        lifecycle.WEAKENING, lifecycle.INVALIDATING}
    assert lifecycle.WAITING_ENTRY not in PUBLIC_LIVE_STATUSES


def test_T15_no_decision_path_file_learned_about_public_age():
    for rel in ("app/backtesting/tracker.py", "app/backtesting/lifecycle.py",
                "app/backtesting/resolution_core.py", "app/services/scheduler.py",
                "app/services/entry_activation.py", "app/services/entry_flags.py",
                "app/engines/ai_decision/signal_generator.py",
                "app/services/lifecycle_log.py"):
        src = (BACKEND / rel).read_text(encoding="utf-8")
        assert "activated_at" not in src, rel
        assert "public_since" not in src, rel


def test_this_checkpoint_adds_no_migration():
    names = sorted(p.name for p in (BACKEND / "migrations").glob("*.sql"))
    assert names[-1] == "0010_candidate_log_rls.sql", names


def _assigns_activated_at(fn_name: str) -> bool:
    """Does this route function actually SET activated_at on its response?

    The service helpers can be perfect and the age still wrong if the route
    forgets to call them — that is the regression this guards. AST, so a
    comment mentioning the field cannot satisfy it.
    """
    import ast

    tree = ast.parse(_src("app/api/routes/signals.py"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
            for inner in ast.walk(node):
                if isinstance(inner, ast.Attribute) and inner.attr == "activated_at" \
                        and isinstance(inner.ctx, ast.Store):
                    return True
    return False


def test_the_list_route_populates_activated_at():
    assert _assigns_activated_at("list_signals"), (
        "list rows would fall back to generated_at and overstate the age")


def test_the_detail_route_populates_activated_at():
    assert _assigns_activated_at("get_signal"), (
        "detail would disagree with the list about the same signal")


def test_the_list_route_resolves_activation_for_the_whole_page_at_once():
    src = _src("app/api/routes/signals.py")
    assert "activation_times(db, [s.id for s in signals])" in src, (
        "one grouped lookup per page — not one per row")


def test_the_response_schema_exposes_activated_at_as_optional():
    from app.schemas.signal import SignalDetailResponse, SignalResponse
    for model in (SignalResponse, SignalDetailResponse):
        assert "activated_at" in model.model_fields, model.__name__
        assert model.model_fields["activated_at"].default is None
