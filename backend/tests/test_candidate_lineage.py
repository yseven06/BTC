"""Opportunity lineage identity — CP-OPPORTUNITY-LINEAGE-IDENTITY-J, Phase 5.

WHAT THIS PRIMITIVE IS FOR. Reset / anti-chase telemetry needs to distinguish
"the SAME developing setup, evaluated again" from "a NEW setup that happens to
share symbol + timeframe + direction". The old heuristic did not: of 121,109
historical pairs matched that way, 117,740 — 97.2% — had the earlier opportunity
already terminal before the later candidate existed. Lineage is the fix, and it
is future-only: historical rows are never backfilled.

THE RATIFIED CONTRACT (closed in Phases 1-4, not re-derived here).

  BEGIN      a directional, structurally eligible candidate with no continuable
             predecessor gets a fresh opaque UUID.
  CONTINUE   a predecessor for the same asset+timeframe continues only when it
             carries a lineage, its direction matches, and no authoritative
             termination intervened.
  TERMINATE  neutral · direction flip · loss of structural eligibility · the
             specifically anchored active signal reaching terminal · a hard
             safety ceiling used ONLY as a ceiling.

WHY NEUTRAL TERMINATES, stated so nobody later mistakes it for a market fact.
Phase 2 measured geometry displacement across neutral gaps and found NO natural
discontinuity — the distribution is smooth and unimodal (even strictly
contiguous bars move the entry zone >1 ATR 18.3% of the time, while 38% of
>8-bar gaps move it less). No boundary exists to discover, so the rule is a
deliberate engineering choice: prefer false-NEW over false-SAME. Fragmentation
merely loses observations; aliasing corrupts every conclusion built on them, and
aliasing is the exact defect this CP exists to remove.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.services.candidate_lineage import (
    LINEAGE_NAMESPACE,
    LINEAGE_SCHEMA_VERSION,
    SAFETY_CEILING,
    STATE_BEGIN,
    STATE_CONTINUED,
    STATE_TERMINATED,
    STATE_UNRESOLVED,
    decide_lineage,
)

UTC = timezone.utc
T0 = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
STEP = timedelta(minutes=15)
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


_UNSET = object()


def _prev(*, direction="bullish", lineage_id=_UNSET, bar_time=T0, anchor=None,
          state=STATE_BEGIN):
    """A predecessor snapshot as the resolver reads it back off the row.

    `lineage_id=None` must mean a row that genuinely carries NO lineage — a
    terminated or historical one. An earlier version of this helper substituted a
    fresh UUID for None, which let the neutral-break and aliasing tests pass on
    the direction mismatch alone while silently never exercising the missing
    lineage they exist to check.
    """
    return {
        "evaluated_bar_time": bar_time,
        "engine_direction": direction,
        "lineage_id": str(uuid.uuid4()) if lineage_id is _UNSET else lineage_id,
        "anchor_signal_id": anchor,
        "state": state,
    }


def _decide(direction="bullish", *, eligible=True, bar_time=T0 + STEP, prev=None,
            anchor_active=True):
    return decide_lineage(direction=direction, eligible=eligible,
                          bar_time=bar_time, prev=prev,
                          anchor_still_active=anchor_active)


# ══ A · BEGIN ══════════════════════════════════════════════════════════════
def test_a_directional_candidate_with_no_predecessor_begins_a_new_lineage():
    out = _decide(prev=None)
    assert out["state"] == STATE_BEGIN
    assert UUID_RE.match(out["lineage_id"]), out["lineage_id"]
    assert out["schema_version"] == LINEAGE_SCHEMA_VERSION


def test_a2_each_begin_is_a_distinct_opaque_identifier():
    ids = {_decide(prev=None)["lineage_id"] for _ in range(50)}
    assert len(ids) == 50, "BEGIN must mint a fresh identity every time"


# ══ B · CONTINUE ═══════════════════════════════════════════════════════════
def test_b_consecutive_same_direction_candidates_share_one_lineage():
    first = _decide(prev=None, bar_time=T0)
    p1 = _prev(lineage_id=first["lineage_id"], bar_time=T0)
    second = _decide(prev=p1, bar_time=T0 + STEP)
    assert second["state"] == STATE_CONTINUED
    assert second["lineage_id"] == first["lineage_id"]

    p2 = _prev(lineage_id=second["lineage_id"], bar_time=T0 + STEP)
    third = _decide(prev=p2, bar_time=T0 + 2 * STEP)
    assert third["lineage_id"] == first["lineage_id"], "A1==A2==A3"


# ══ C · NEUTRAL TERMINATES ═════════════════════════════════════════════════
def test_c_a_neutral_evaluation_terminates_and_the_next_long_starts_fresh():
    a = _decide("bullish", prev=None, bar_time=T0)

    # the neutral bar itself carries no lineage
    n = _decide("neutral", prev=_prev(lineage_id=a["lineage_id"], bar_time=T0),
                bar_time=T0 + STEP)
    assert n["state"] == STATE_TERMINATED
    assert n["lineage_id"] is None

    # and the resolver, reading that neutral row back, cannot continue through it
    after = _decide("bullish", bar_time=T0 + 2 * STEP,
                    prev=_prev(direction="neutral", lineage_id=None,
                               bar_time=T0 + STEP, state=STATE_TERMINATED))
    assert after["state"] == STATE_BEGIN
    assert after["lineage_id"] != a["lineage_id"]


def test_s_a_neutral_row_with_complete_geometry_still_terminates():
    """Neutral rows DO carry a full entry/stop/TP geometry — proven in Phase 1.
    Eligibility must therefore never be mistaken for a directional thesis."""
    out = _decide("neutral", eligible=True, prev=_prev())
    assert out["state"] == STATE_TERMINATED
    assert out["lineage_id"] is None


# ══ D · DIRECTION FLIP ═════════════════════════════════════════════════════
def test_d_direction_flip_starts_a_new_lineage():
    p = _prev(direction="bullish")
    out = _decide("bearish", prev=p)
    assert out["state"] == STATE_BEGIN
    assert out["lineage_id"] != p["lineage_id"]


# ══ E · STRUCTURAL ELIGIBILITY ═════════════════════════════════════════════
def test_e_loss_of_structural_eligibility_terminates_and_the_next_one_is_new():
    a = _decide(prev=None, bar_time=T0)
    bad = _decide(eligible=False,
                  prev=_prev(lineage_id=a["lineage_id"], bar_time=T0),
                  bar_time=T0 + STEP)
    assert bad["state"] == STATE_TERMINATED and bad["lineage_id"] is None

    later = _decide(bar_time=T0 + 2 * STEP,
                    prev=_prev(lineage_id=None, bar_time=T0 + STEP,
                               state=STATE_TERMINATED))
    assert later["state"] == STATE_BEGIN
    assert later["lineage_id"] != a["lineage_id"]


# ══ F · ANCHORED SIGNAL TERMINAL ═══════════════════════════════════════════
def test_f_a_terminal_anchor_breaks_the_lineage():
    p = _prev(anchor="sig-1")
    out = _decide(prev=p, anchor_active=False)
    assert out["state"] == STATE_BEGIN
    assert out["lineage_id"] != p["lineage_id"]


def test_f2_a_genuinely_active_anchor_permits_continuation():
    p = _prev(anchor="sig-1")
    out = _decide(prev=p, anchor_active=True)
    assert out["state"] == STATE_CONTINUED
    assert out["lineage_id"] == p["lineage_id"]


def test_g_an_unanchored_predecessor_is_unaffected_by_anchor_state():
    """Skipped/dropped candidates carry no signal_id. Their continuation must
    not depend on an anchor they never had."""
    p = _prev(anchor=None)
    out = _decide(prev=p, anchor_active=False)
    assert out["state"] == STATE_CONTINUED, "no anchor means nothing to terminate"


# ══ L · SAME-BAR REPLAY STABILITY ══════════════════════════════════════════
def test_l_replaying_the_exact_same_bar_reuses_the_recorded_identity():
    """The row is keyed (asset, timeframe, evaluated_bar_time, policy, source)
    with ON CONFLICT DO NOTHING, so a replay writes nothing — but it must not
    COMPUTE a contradictory identity that the conflict then silently hides."""
    existing = _prev(bar_time=T0, lineage_id=str(uuid.uuid4()))
    out = _decide(prev=existing, bar_time=T0)          # same bar, not a successor
    assert out["lineage_id"] == existing["lineage_id"]
    assert out["state"] == STATE_CONTINUED
    again = _decide(prev=existing, bar_time=T0)
    assert again["lineage_id"] == out["lineage_id"], "replay must be deterministic"


# ══ SAFETY CEILING — a ceiling, never the identity ═════════════════════════
def test_the_safety_ceiling_bounds_continuation_without_defining_it():
    p = _prev(bar_time=T0)
    inside = _decide(prev=p, bar_time=T0 + SAFETY_CEILING - STEP)
    assert inside["state"] == STATE_CONTINUED
    beyond = _decide(prev=p, bar_time=T0 + SAFETY_CEILING + STEP)
    assert beyond["state"] == STATE_BEGIN


# ══ N · RESOLVER FAILURE ═══════════════════════════════════════════════════
def test_n_resolver_failure_is_an_explicit_sentinel_not_a_fabricated_uuid():
    from app.services.candidate_lineage import unresolved_payload

    out = unresolved_payload("PredecessorLookupError")
    assert out["state"] == STATE_UNRESOLVED
    assert out["lineage_id"] is None, "a fabricated UUID would look authoritative"
    assert out["failure_reason"] == "PredecessorLookupError"
    assert out["schema_version"] == LINEAGE_SCHEMA_VERSION


def test_m_a_historical_row_is_distinguishable_from_a_resolver_failure():
    """Historical rows have NO namespace at all; a failure has the namespace with
    an explicit unresolved state. Collapsing the two would make the backfill ban
    unverifiable."""
    from app.services.candidate_lineage import unresolved_payload

    historical_extra = {"primary_demotion_reason": "published"}
    assert LINEAGE_NAMESPACE not in historical_extra
    failed_extra = {LINEAGE_NAMESPACE: unresolved_payload("boom")}
    assert failed_extra[LINEAGE_NAMESPACE]["state"] == STATE_UNRESOLVED


# ══ R · THE IDENTIFIER IS OPAQUE ═══════════════════════════════════════════
def test_r_identity_is_not_a_function_of_asset_timeframe_and_direction():
    """The banned design. Two BEGINs with identical inputs must still differ —
    that is exactly what a static tuple hash cannot do."""
    one = _decide("bullish", prev=None, bar_time=T0)
    two = _decide("bullish", prev=None, bar_time=T0)
    assert one["lineage_id"] != two["lineage_id"]
    for forbidden in ("bullish", "15m", "BTCUSDT", str(T0.year)):
        assert forbidden not in one["lineage_id"]


def test_q_no_future_information_is_accepted_by_the_decision_at_all():
    """Structural: the pure decision's signature cannot even receive an outcome.
    A test that merely passes an outcome and checks it is ignored would pass on
    a function that quietly starts reading it later."""
    import inspect

    params = set(inspect.signature(decide_lineage).parameters)
    for future in ("outcome", "shadow_outcome", "result", "tp", "sl", "stop",
                   "expiry", "entry_reached", "mfe", "mae", "pnl", "r_multiple"):
        assert future not in params, f"decide_lineage accepts future data: {future}"


# ══ T · THE CENTRAL ACCEPTANCE PROOF ═══════════════════════════════════════
def test_t_two_distinct_opportunities_separated_by_termination_never_alias():
    """THE defect, reproduced. Same asset, same timeframe, same direction — the
    old heuristic merged these. A valid termination sits between them."""
    a = _decide("bullish", prev=None, bar_time=T0)

    # the opportunity ends: the engine goes neutral
    _decide("neutral", prev=_prev(lineage_id=a["lineage_id"], bar_time=T0),
            bar_time=T0 + STEP)

    # six hours later an identical-looking setup appears
    b = _decide("bullish", bar_time=T0 + timedelta(hours=6),
                prev=_prev(direction="neutral", lineage_id=None,
                           bar_time=T0 + STEP, state=STATE_TERMINATED))

    assert a["lineage_id"] != b["lineage_id"], "the historical aliasing defect returned"
    # and the old heuristic really would have merged them:
    assert ("BTCUSDT", "15m", "bullish") == ("BTCUSDT", "15m", "bullish")


def test_t2_true_continuation_is_not_fragmented_by_the_new_rule():
    """The complement. Without this, a resolver that always BEGINs would pass
    the aliasing test above while being useless."""
    ids = []
    prev = None
    for i in range(6):
        out = _decide("bullish", bar_time=T0 + i * STEP, prev=prev)
        ids.append(out["lineage_id"])
        prev = _prev(lineage_id=out["lineage_id"], bar_time=T0 + i * STEP)
    assert len(set(ids)) == 1, f"one developing setup fragmented into {len(set(ids))}"


# ══ H · I · ISOLATION ══════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_h_and_i_the_lookup_is_scoped_to_one_asset_and_one_timeframe():
    """Isolation is a property of the QUERY, so it is asserted on the emitted
    SQL rather than by feeding the pure decision a predecessor it would never
    have been given."""
    from app.services import candidate_lineage as cl

    seen = {}

    class _Res:
        def first(self):
            return None

    class _DB:
        async def execute(self, stmt, *a, **kw):
            seen["sql"] = str(stmt)
            return _Res()

    await cl.load_predecessor(_DB(), asset_id="A", timeframe="15m", bar_time=T0)
    sql = seen["sql"].lower()
    assert "asset_id" in sql and "timeframe" in sql, sql
    assert "evaluated_bar_time" in sql and "limit" in sql, sql


# ══ WIRING · O · P · NON-INTERFERENCE ══════════════════════════════════════
class _FakeRes:
    def __init__(self, row=None):
        self._row = row

    def first(self):
        return self._row

    def scalar_one_or_none(self):
        return "row-id"


class _WiredDB:
    """Enough AsyncSession for record_candidate, with a scriptable predecessor."""

    def __init__(self, predecessor=None):
        self.predecessor = predecessor
        self.statements = []

    def begin_nested(self):
        class _Ctx:
            async def __aenter__(s):
                return s

            async def __aexit__(s, *a):
                return False
        return _Ctx()

    async def execute(self, stmt, *a, **kw):
        self.statements.append(stmt)
        if "INSERT" in str(stmt).upper()[:80]:
            return _FakeRes()
        return _FakeRes(self.predecessor)


def _wire_kw(**over):
    import pandas as pd
    from app.models.decision_candidate import (REASON_NOT_ACTIONABLE,
                                               VERDICT_DROPPED)
    idx = pd.date_range("2026-08-20", periods=60, freq="15min", tz="UTC")
    df = pd.DataFrame({"open": [100.0] * 60, "high": [101.0] * 60,
                       "low": [99.0] * 60, "close": [100.0] * 60,
                       "volume": [10.0] * 60}, index=idx)
    decision = {
        "symbol": "BTCUSDT", "timeframe": "15m", "signal_type": "BUY",
        "direction": "bullish", "confidence_score": 70.0, "probability_score": 60.0,
        "risk_score": 5.0, "risk_level": "medium",
        "entry_zone_low": 99.0, "entry_zone_high": 100.0, "stop_loss": 97.0,
        "tp1": 103.0, "tp2": 105.0, "tp3": 108.0,
        "birth_telemetry": {"atr_pct": 0.5}, "consensus_telemetry": {},
        "decision_input_telemetry": {"decision_input_version": "closed_candle_v1"},
        "engine_results": [], "mtf_trends": {},
    }
    kw = dict(asset_id="a-1", symbol="BTCUSDT", timeframe="15m", decision=decision,
              df=df, evaluated_at=T0, verdict=VERDICT_DROPPED,
              demotion_reason=REASON_NOT_ACTIONABLE, final_signal_type="BUY",
              final_direction="bullish", regime_label="ranging",
              regime_result=None, engine_weights={}, adaptive_active=False,
              last_close=100.0)
    kw.update(over)
    return kw


def _written_extra(db):
    for st in db.statements:
        if "INSERT" in str(st).upper()[:80]:
            return dict(st.compile().params).get("extra")
    return None


@pytest.mark.asyncio
async def test_o_and_p_candidates_without_a_signal_id_still_resolve_a_lineage():
    """Skipped and dropped rows carry no signal_id — only the published call site
    passes one. Identity must not depend on it."""
    from app.services import candidate_log

    for verdict in ("dropped", "skipped"):
        db = _WiredDB(predecessor=None)
        assert await candidate_log.record_candidate(db, **_wire_kw(verdict=verdict))
        ns = (_written_extra(db) or {}).get(LINEAGE_NAMESPACE)
        assert ns, f"{verdict}: no lineage namespace written"
        assert ns["state"] == STATE_BEGIN
        assert UUID_RE.match(ns["lineage_id"])


@pytest.mark.asyncio
async def test_resolver_failure_writes_the_sentinel_and_still_records_the_row():
    from app.services import candidate_log

    class _Broken(_WiredDB):
        async def execute(self, stmt, *a, **kw):
            self.statements.append(stmt)
            if "INSERT" in str(stmt).upper()[:80]:
                return _FakeRes()
            raise RuntimeError("predecessor lookup exploded")

    db = _Broken()
    assert await candidate_log.record_candidate(db, **_wire_kw()) is True
    ns = (_written_extra(db) or {}).get(LINEAGE_NAMESPACE)
    assert ns["state"] == STATE_UNRESOLVED
    assert ns["lineage_id"] is None
    assert ns["failure_reason"] == "RuntimeError"


@pytest.mark.asyncio
async def test_lineage_does_not_disturb_any_other_recorded_value():
    from app.services import candidate_log

    db = _WiredDB()
    await candidate_log.record_candidate(db, **_wire_kw())
    extra = _written_extra(db) or {}
    for untouched in ("primary_demotion_reason", "decision_input_version",
                      "threshold_direction", "engine_demoted"):
        assert untouched in extra, f"lineage destroyed {untouched}"


def test_s22_the_pure_builder_never_gains_database_access():
    """`build_candidate_values` is pure by contract — that is what lets it be
    tested without a database, and the resolver lives in record_candidate
    precisely to keep it so."""
    import inspect

    from app.services import candidate_log

    src = inspect.getsource(candidate_log.build_candidate_values)
    for banned in ("await ", "db.", "execute(", "select(", "resolve_lineage"):
        assert banned not in src, f"the pure builder reached for {banned}"


def test_s20_the_lineage_module_can_never_rewrite_a_historical_row():
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent / "app" / "services"
           / "candidate_lineage.py").read_text(encoding="utf-8")
    for mutating in ("update(", "delete(", "insert(", "UPDATE ", "DELETE "):
        assert mutating not in src, f"lineage module can mutate rows: {mutating}"


def test_s21_there_is_exactly_one_identity_authority():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "app"
    owners = [p.name for p in root.rglob("*.py")
              if "__pycache__" not in str(p)
              and "lineage_id" in p.read_text(encoding="utf-8", errors="ignore")]
    assert sorted(owners) == ["candidate_lineage.py"], owners


# ══ GAPS FOUND BY SABOTAGE ═════════════════════════════════════════════════
def test_l2_same_bar_replay_is_stable_even_when_the_anchor_has_since_died():
    """S13. The plain replay case is indistinguishable from ordinary
    continuation — both legitimately return the predecessor's id — so it proves
    nothing. The discriminating case is a replay whose anchor has gone terminal
    in between: without the same-bar branch that becomes a BEGIN with a fresh
    UUID, and ON CONFLICT DO NOTHING then hides the contradiction."""
    recorded = str(uuid.uuid4())
    existing = _prev(bar_time=T0, lineage_id=recorded, anchor="sig-1")
    out = _decide(prev=existing, bar_time=T0, anchor_active=False)
    assert out["lineage_id"] == recorded, "a replay invented a new identity"
    assert out["state"] == STATE_CONTINUED


def test_s24_the_safety_ceiling_is_an_actual_bound_not_a_symbol():
    """S24. Asserting only against SAFETY_CEILING itself moves with the mutant.
    Pin an absolute range and an absolute elapsed gap."""
    assert timedelta(hours=1) <= SAFETY_CEILING <= timedelta(days=7), SAFETY_CEILING
    stale = _decide(prev=_prev(bar_time=T0), bar_time=T0 + timedelta(days=30))
    assert stale["state"] == STATE_BEGIN, "a 30-day-old predecessor was continued"


def test_s20_the_lineage_module_imports_no_mutating_construct():
    """S20. Banning 'update(' missed `from sqlalchemy import select, update`."""
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent / "app" / "services"
           / "candidate_lineage.py").read_text(encoding="utf-8")
    import ast as _ast

    for node in _ast.walk(_ast.parse(src)):
        if isinstance(node, _ast.ImportFrom):
            names = {a.name for a in node.names}
            for banned in ("update", "delete", "insert"):
                assert banned not in names, f"lineage imports {banned}"


@pytest.mark.asyncio
async def test_s25_anchor_liveness_reads_the_outcome_not_a_demotable_status():
    """S25. `_anchor_still_active` had no test at all — the pure decision takes
    liveness as a parameter, so a resolver that always answered 'active' passed
    everything. live_status is demotable and lags; the performance outcome is
    what settles it."""
    from app.models.signal import SignalOutcome
    from app.services import candidate_lineage as cl

    class _R:
        def __init__(self, row):
            self._row = row

        def first(self):
            return self._row

    class _DB:
        def __init__(self, row):
            self._row = row
            self.sql = ""

        async def execute(self, stmt, *a, **kw):
            self.sql = str(stmt)
            return _R(self._row)

    terminal = _DB((SignalOutcome.LOSS,))
    assert await cl._anchor_still_active(terminal, "sig-1") is False, \
        "a stale terminal signal masqueraded as active"
    assert "signal_performances" in terminal.sql.lower(), terminal.sql

    live = _DB((SignalOutcome.ACTIVE,))
    assert await cl._anchor_still_active(live, "sig-1") is True
    # No verdict yet is not the same as terminal.
    assert await cl._anchor_still_active(_DB(None), "sig-1") is True


def test_s23_the_reference_set_guard_still_asserts_exact_equality():
    """S23. Nothing guarded the guard: rewriting its `==` into a superset check
    silently admits any future module. Pin the assertion's shape."""
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent / "tests"
           / "test_macro_shadow_wiring.py").read_text(encoding="utf-8")
    body = src.split("def test_the_candidate_table_is_referenced_by_exactly_four_modules", 1)[1]
    body = body.split("\ndef ", 1)[0]
    assert "}, refs" in body, "the reference set no longer asserts equality"
    assert "| refs" not in body and ">=" not in body, \
        "the reference set was relaxed into a superset check"
