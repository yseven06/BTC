"""CP-SIGNALCENTER-PUBLIC-ACTIVE-ONLY — waiting_entry must not reach the public feed.

`waiting_entry` means the entry zone price has NOT been observed: no position
exists. `list_signals` filtered only on `Signal.is_active`, so those rows were
served to the public Signal Center beside genuinely open trades — with entry, TP
and SL levels attached. Measured on production at the time of the fix: 10 of the
36 rows in the public cohort were `waiting_entry`.

WHERE THE ASSERTIONS POINT, AND WHY
-----------------------------------
The defect lives in the QUERY and in two id-lookup guards, not in serialization,
so these tests instrument exactly that: the list route is driven with a fake
session that captures the COMPILED SQL (proving the predicate reaches the
database rather than being applied in Python after the fact, and that the count
query carries it too, so pagination totals cannot disagree with the page), and
the id routes are called directly to observe the guard. That is the opposite
trade-off from tests/test_backtest_http_metadata.py, where the bug WAS in
serialization and only the real ASGI stack could see it.

This is a VISIBILITY change. Nothing here asserts anything about how a signal is
generated, activated or resolved, and the scope guards at the bottom prove those
paths were not touched.
"""

from __future__ import annotations

import ast
import pathlib
import re
import types

import pytest

from app.backtesting import lifecycle
from app.services.publication import (PUBLIC_LIVE_STATUSES, is_public_live_status,
                                      is_publishable)

BACKEND = pathlib.Path(__file__).resolve().parent.parent
ALL_STATES = [lifecycle.WAITING_ENTRY, lifecycle.ACTIVE, lifecycle.APPROACHING_TP,
              lifecycle.WEAKENING, lifecycle.INVALIDATING]


# ── the contract itself ──────────────────────────────────────────────────────
def test_the_allow_list_is_exactly_the_post_activation_states():
    assert set(PUBLIC_LIVE_STATUSES) == {
        lifecycle.ACTIVE, lifecycle.APPROACHING_TP,
        lifecycle.WEAKENING, lifecycle.INVALIDATING}
    # The one state that means "no position exists yet".
    assert lifecycle.WAITING_ENTRY not in PUBLIC_LIVE_STATUSES


def test_it_is_an_allow_list_so_unknown_states_fail_closed():
    """A deny-list would publish anything added later. This must not."""
    for unknown in ("pending_fill", "paused", "", None, "ACTIVE", "Active"):
        assert is_public_live_status(unknown) is False, unknown


# T1/T2 · waiting_entry is never public, with or without prior activation history
@pytest.mark.parametrize("live_status", ALL_STATES)
def test_T1_T2_live_visibility_is_decided_by_state_alone(live_status):
    expected = live_status != lifecycle.WAITING_ENTRY
    assert is_publishable(is_active=True, live_status=live_status) is expected


# T3/T4/T5/T6 · every post-activation state stays public
@pytest.mark.parametrize("live_status", [lifecycle.ACTIVE, lifecycle.APPROACHING_TP,
                                         lifecycle.WEAKENING, lifecycle.INVALIDATING])
def test_T3_T6_post_activation_states_remain_public(live_status):
    assert is_publishable(is_active=True, live_status=live_status) is True


# T7 · closed signals belong to the history contract and are untouched
@pytest.mark.parametrize("live_status", ALL_STATES + [None])
def test_T7_closed_signals_are_always_serveable(live_status):
    """Including one that closed WITHOUT ever filling — that record is exactly
    what the no-fill research needs to stay visible."""
    assert is_publishable(is_active=False, live_status=live_status) is True


def test_a_demoted_signal_is_hidden_even_though_it_was_once_active():
    """Production holds 3 rows that are waiting_entry now and were active before.

    A rule keyed on 'has a waiting_entry -> active history row' would publish
    them; the state rule does not. This is why the boundary is not history-based.
    """
    assert is_publishable(is_active=True, live_status=lifecycle.WAITING_ENTRY) is False


# ── the list route: does the predicate reach SQL? ────────────────────────────
class _CapturingSession:
    """Fake AsyncSession that records the compiled SQL of every query."""

    def __init__(self, rows=()):
        self.sql: list[str] = []
        self._rows = list(rows)
        self._n = 0

    async def execute(self, query, *a, **k):
        try:
            self.sql.append(str(query.compile(compile_kwargs={"literal_binds": True})))
        except Exception:
            self.sql.append(str(query))
        self._n += 1
        rows = self._rows
        outer = self

        class _R:
            def scalar_one(self):
                return len(outer._rows)

            def unique(self):
                return self

            def scalars(self):
                return self

            def all(self):
                return rows

        return _R()


async def _run_list(**kwargs):
    from app.api.routes.signals import list_signals
    from app.subscriptions.gating import SubscriptionTier
    db = _CapturingSession()
    params = dict(asset_id=None, direction=None, signal_type=None, timeframe=None,
                  only_actionable=True, page=1, page_size=20,
                  tier=SubscriptionTier.PRO, db=db)
    params.update(kwargs)
    await list_signals(**params)
    return db


# The predicate as it appears in the WHERE clause. Asserting merely that the
# string "live_status" occurs SOMEWHERE in the SQL is vacuous — the count query
# wraps `select(Signal)` in a subquery whose SELECT list already names every
# column, `signals.live_status` included. Deleting the filter outright left that
# weaker assertion green; this one has to see the IN predicate itself.
_IN_PREDICATE = re.compile(r"live_status\s+IN\s*\(([^)]*)\)", re.I)


def _publication_predicate(sql: str):
    m = _IN_PREDICATE.search(sql)
    return m.group(1) if m else None


@pytest.mark.asyncio
async def test_the_list_query_filters_live_status_in_SQL_not_in_python():
    db = await _run_list()
    assert db.sql, "no query was compiled"
    for s in db.sql:
        allowed = _publication_predicate(s)
        assert allowed is not None, f"no live_status IN predicate in: {s[:200]}"
        for state in PUBLIC_LIVE_STATUSES:
            assert state in allowed, state
        assert lifecycle.WAITING_ENTRY not in allowed, (
            "waiting_entry must never be an allowed value")


# T8 · pagination totals must be computed over the SAME filtered set
@pytest.mark.asyncio
async def test_T8_the_count_query_carries_the_same_filter():
    db = await _run_list()
    count_sql = [s for s in db.sql if "count(" in s.lower()]
    assert count_sql, "no count query issued"
    for s in count_sql:
        allowed = _publication_predicate(s)
        assert allowed is not None, (
            "total would count hidden rows and disagree with the page")
        assert lifecycle.WAITING_ENTRY not in allowed


# T9/T10 · every optional filter path inherits the boundary
@pytest.mark.asyncio
@pytest.mark.parametrize("extra", [
    {"direction": "bullish"},
    {"signal_type": "BUY"},
    {"timeframe": "15m"},
    {"only_actionable": False},
    {"page": 2, "page_size": 50},
])
async def test_T9_T10_filters_and_pagination_cannot_reintroduce_waiting_entry(extra):
    db = await _run_list(**extra)
    assert db.sql
    for s in db.sql:
        allowed = _publication_predicate(s)
        assert allowed is not None, (extra, s[:200])
        assert lifecycle.WAITING_ENTRY not in allowed, extra


# ── T11 · id-addressable surfaces ────────────────────────────────────────────
def _fake_signal(*, is_active: bool, live_status: str):
    return types.SimpleNamespace(is_active=is_active, live_status=live_status,
                                 id="00000000-0000-0000-0000-000000000000")


class _OneRowSession:
    def __init__(self, obj):
        self._obj = obj

    async def execute(self, *a, **k):
        obj = self._obj

        class _R:
            def unique(self):
                return self

            def scalar_one_or_none(self):
                return obj

        return _R()


@pytest.mark.asyncio
async def test_T11_detail_endpoint_hides_a_live_waiting_entry_signal():
    from fastapi import HTTPException

    from app.api.routes.signals import get_signal
    db = _OneRowSession(_fake_signal(is_active=True,
                                     live_status=lifecycle.WAITING_ENTRY))
    with pytest.raises(HTTPException) as exc:
        await get_signal(signal_id="x", db=db)          # type: ignore[arg-type]
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_T11b_intelligence_endpoint_hides_a_live_waiting_entry_signal():
    from fastapi import HTTPException

    from app.api.routes.signals import signal_intelligence
    db = _OneRowSession(_fake_signal(is_active=True,
                                     live_status=lifecycle.WAITING_ENTRY))
    with pytest.raises(HTTPException) as exc:
        await signal_intelligence(signal_id="x", db=db)  # type: ignore[arg-type]
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_T11c_detail_endpoint_still_serves_a_CLOSED_never_filled_signal():
    """The history contract is untouched: a signal that closed without filling
    must remain readable, or the no-fill record disappears from the product."""
    from fastapi import HTTPException

    from app.api.routes.signals import get_signal
    db = _OneRowSession(_fake_signal(is_active=False,
                                     live_status=lifecycle.WAITING_ENTRY))
    try:
        await get_signal(signal_id="x", db=db)          # type: ignore[arg-type]
    except HTTPException as exc:                         # pragma: no cover
        pytest.fail(f"closed signal was hidden: {exc.status_code}")
    except Exception:
        pass          # serialization of the stub is irrelevant; the guard passed


# ── T12 · no streaming surface can bypass the boundary ───────────────────────
def _identifiers(src: str) -> set:
    """Every name/attribute/decorator actually USED in the code.

    Parsed, not grepped: prices.py carries the words "WebSocket handles crypto
    directly" in a comment describing the FRONTEND's own Binance connection, and
    a text search reads that as a backend streaming surface.
    """
    tree = ast.parse(src)
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
    return out


def test_T12_there_is_no_websocket_or_streaming_signal_surface():
    """If one is ever added it must be added to this contract deliberately."""
    offenders = []
    for p in (BACKEND / "app" / "api").rglob("*.py"):
        used = _identifiers(p.read_text(encoding="utf-8"))
        hit = used & {"WebSocket", "websocket", "StreamingResponse",
                      "EventSourceResponse", "sse_starlette"}
        if hit:
            offenders.append((p.name, sorted(hit)))
    assert not offenders, offenders


# ── scope guards: this CP is visibility ONLY ─────────────────────────────────
def _src(rel: str) -> str:
    return (BACKEND / rel).read_text(encoding="utf-8")


def test_T13_T17_no_decision_path_file_mentions_the_publication_boundary():
    """The boundary must live at the API edge and nowhere near the decision path."""
    for rel in ("app/backtesting/tracker.py", "app/backtesting/lifecycle.py",
                "app/backtesting/resolution_core.py", "app/services/scheduler.py",
                "app/services/entry_activation.py", "app/services/entry_flags.py",
                "app/engines/ai_decision/signal_generator.py",
                "app/services/coin_memory.py", "app/services/shadow_eval.py"):
        src = _src(rel)
        # Assert on IMPORTS and USED NAMES, not on the English word: entry_flags
        # describes "the publication volume" in prose, which a text search reads
        # as a dependency that is not there.
        assert "app.services.publication" not in src, rel
        assert "PUBLIC_LIVE_STATUSES" not in _identifiers(src), rel
        assert "is_publishable" not in _identifiers(src), rel


def test_the_boundary_never_writes():
    """Visibility only — the module must not MUTATE anything.

    It reads: CP-PUBLICATION-TIMESTAMP-DEBT added a grouped SELECT for the
    activation timestamp. So the assertion is about mutation, not about the
    string "db." — the earlier form banned the substring and would have failed
    on a perfectly legitimate read. Parsed, not grepped, so the module's own
    prose cannot trip it either.
    """
    tree = ast.parse(_src("app/services/publication.py"))
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    for forbidden in ("commit", "rollback", "add", "add_all", "delete",
                      "merge", "flush", "execute_many"):
        assert forbidden not in called, forbidden
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    for forbidden in ("insert", "update", "delete"):
        assert forbidden not in names, forbidden


# The migration set the publication checkpoint was written against, by NAME.
CHECKPOINT_MIGRATIONS = frozenset({
    "0001_consent_log.sql", "0002_stripe_subscription.sql",
    "0003_per_user_notifications.sql", "0004_signal_snapshot_extra.sql",
    "0005_notify_lifecycle.sql", "0006_enable_rls.sql",
    "0007_rls_revoke_data_api.sql", "0008_signal_performance_times.sql",
    "0009_resolution_provenance.sql", "0010_candidate_log_rls.sql",
})

# The two tables publication actually reads: the signal row it serves and the
# transition history it derives `activated_at` from.
GUARDED_TABLES = frozenset({"signals", "signal_status_history"})

_SQL_COMMENT = re.compile(r"--[^\n]*|/\*.*?\*/", re.S)
_DDL_TABLE = re.compile(
    r"\b(?:create|alter|drop)\s+table\s+(?:if\s+(?:not\s+)?exists\s+)?"
    r'"?(?:public\.)?"?([a-z_][a-z0-9_]*)', re.I)


def _ddl_targets(sql: str) -> set:
    """Tables a migration CREATEs, ALTERs or DROPs, comments stripped first."""
    return {m.group(1).lower()
            for m in _DDL_TABLE.finditer(_SQL_COMMENT.sub(" ", sql))}


def test_no_migration_was_added_by_this_checkpoint():
    """This checkpoint added no migration — proven LOCALLY.

    The old form asserted `"0011_ohlcv_shadow.sql" not in names` with the
    message "the OHLCV branch must not be mixed into this one". That intent was
    right and is preserved below, but the ASSERTION was a permanent veto on
    another checkpoint's legitimate file: once CP-OHLCV-A1 lands 0011 through
    its own gates, publication is no more "mixed into" it than it is into 0009.
    A filename ban cannot tell entanglement from coexistence.

    What actually has to stay true is that publication does not DEPEND on OHLCV,
    and that is asserted directly in
    `test_publication_never_couples_to_the_ohlcv_store`.
    """
    mig = BACKEND / "migrations"
    present = {p.name for p in mig.glob("*.sql")}
    assert {n for n in present if n[:4] <= "0010"} == CHECKPOINT_MIGRATIONS, (
        f"the migration set this checkpoint pinned moved; found {sorted(present)}")
    for p in sorted(mig.glob("*.sql")):
        if p.name in CHECKPOINT_MIGRATIONS:
            continue
        hit = _ddl_targets(p.read_text(encoding="utf-8")) & GUARDED_TABLES
        assert not hit, (
            f"{p.name} moves {sorted(hit)} — publication's own tables. THIS is "
            f"what 'must not be mixed into this one' was protecting.")


def test_publication_never_couples_to_the_ohlcv_store():
    """The real content of the old 0011 prohibition, as a semantic assertion.

    Fails the moment publication imports, reads, writes or otherwise depends on
    the OHLCV shadow store — which is what "must not be mixed" meant — while
    staying silent about that store merely existing.
    """
    surfaces = ("app/services/publication.py", "app/api/routes/signals.py")
    for rel in surfaces:
        src = _src(rel)
        tree = ast.parse(src)

        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
                imported.update(a.name for a in node.names)
        assert not any("ohlcv" in n.lower() for n in imported), (
            f"{rel} imports the OHLCV store: {sorted(imported)}")

        # Names actually referenced in CODE — docstrings and comments stripped,
        # so a note explaining the decoupling cannot trip its own guard.
        code = re.sub(r"#[^\n]*", " ", src)
        code = re.sub(r'"""(?:.|\n)*?"""', " ", code)
        code = re.sub(r"'''(?:.|\n)*?'''", " ", code)
        for token in ("OhlcvBar", "ohlcv_bars", "ohlcv_shadow"):
            assert token not in code, f"{rel} references {token}"

    # And the dependency must not arrive through the back door either: nothing
    # publication imports may itself reach the store.
    from app.services import publication
    assert not any("ohlcv" in m.lower()
                   for m in getattr(publication, "__dict__", {})), (
        "an OHLCV symbol reached the publication module namespace")
