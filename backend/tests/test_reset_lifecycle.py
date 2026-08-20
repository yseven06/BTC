"""Reset lifecycle telemetry — CP-RESET-LIFECYCLE-TELEMETRY-K, Phase 2 RED.

WHAT THIS MEASURES. For one opportunity lineage: when it became extended, when it
genuinely reset, whether it then chased again, and how long each wait lasted — so
that the eventual shadow question ("do not take an extended candidate; reconsider
it when the CURRENT chase episode genuinely resets") can be answered from stored
evidence instead of guessed.

THE DEFECT THIS CONTRACT WAS REVISED TO AVOID. An earlier draft had
`not_extended -> extended -> reset -> settled` with `settled` absorbing. Walked
against a real path — extension, reset, re-extension, second reset — it reported
the lineage as "reset, therefore safe" while price was being chased again, and it
could not recover when the current episode began. Reconstructing that from the
row series does not rescue it either: rows genuinely go missing (the per-asset
job_guard deadline writes no candidate at all), and a reconstruction over a gap
concludes "one episode, no re-chase" — silently wrong in the direction that
matters. Hence two orthogonal axes:

  CURRENT STATE      recomputed every row, free to oscillate
  FIRST-RESET EVIDENCE   frozen once per lineage, never rewritten
  CURRENT EPISODE    updated per chase episode, never touching the above

THRESHOLD SEMANTICS, STATED EXACTLY. `extension_value` is raw and
threshold-INDEPENDENT. Everything else — state, crossings, first-reset and
episode timestamps — is evaluated against X_ref = 2.0, a member of the
pre-registered family {0.5, 1.0, 1.5, 2.0, 3.0}, frozen as a shadow reference. It
is NOT a production gate and NOT a claim of universal optimum: CP-G/H returned
EXTENSION_REGIME_CONDITIONAL, with 4h/1d and tight-SL cells failing. A reset at
X=2.0 is NOT automatically a reset at any other X.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services.reset_lifecycle import (
    RESET_NAMESPACE,
    RESET_REFERENCE_THRESHOLD,
    RESET_SCHEMA_VERSION,
    STATE_CLOSED,
    STATE_EXPIRED,
    STATE_EXTENDED,
    STATE_NOT_EXTENDED,
    STATE_UNRESOLVED,
    decide_reset_lifecycle,
    unresolved_reset_payload,
)

BACKEND = Path(__file__).resolve().parent.parent
UTC = timezone.utc
T = [datetime(2026, 8, 20, 12, 0, tzinfo=UTC) + i * timedelta(minutes=15)
     for i in range(8)]
ISO = "%Y-%m-%dT%H:%M:%S%z"

# Lineage verdicts this machine consumes. Reset never re-derives a boundary —
# CP-J's lineage resolver owns that, and one owner is the point.
LIN_BEGIN, LIN_CONT, LIN_TERM, LIN_UNRES = "begin", "continued", "terminated", "unresolved"


def _step(prev, *, ext, at, lineage_state=LIN_CONT, prev_bar_time=None,
          atr_source="regime", atr_fallback_used=False):
    return decide_reset_lifecycle(
        extension_value=ext, bar_time=at, prev=prev,
        prev_bar_time=prev_bar_time, lineage_state=lineage_state,
        atr_source=atr_source, atr_fallback_used=atr_fallback_used)


def _walk(steps):
    """Feed a sequence of (extension, bar_time, lineage_state) through the
    machine, threading each result in as the next predecessor."""
    out, prev, prev_at = [], None, None
    for ext, at, lin in steps:
        rec = _step(prev, ext=ext, at=at, lineage_state=lin, prev_bar_time=prev_at)
        out.append(rec)
        prev, prev_at = rec, at
    return out


# ══ 1 · EPISODE SEPARATION — THE CENTRAL ACCEPTANCE PROOF ══════════════════
def test_the_counterexample_extension_reset_reextension_second_reset():
    """T0 ext#1 · T1 reset#1 · T2 ext#2 · T3 still ext#2 · T4 reset#2.

    This exact walk is what invalidated the previous contract.
    """
    r = _walk([(2.4, T[0], LIN_BEGIN), (1.6, T[1], LIN_CONT), (2.2, T[2], LIN_CONT),
               (2.5, T[3], LIN_CONT), (1.4, T[4], LIN_CONT)])

    assert [x["state"] for x in r] == [
        STATE_EXTENDED, STATE_NOT_EXTENDED, STATE_EXTENDED,
        STATE_EXTENDED, STATE_NOT_EXTENDED]

    # first-extension evidence freezes at T0 and never moves
    assert all(x["extension_detected_at"] == T[0].isoformat() for x in r)

    # first-reset evidence freezes at T1 and never moves
    assert r[0]["first_reset_at"] is None
    assert all(x["first_reset_at"] == T[1].isoformat() for x in r[1:])

    # the CURRENT episode is what actually moves
    assert r[0]["current_extension_started_at"] == T[0].isoformat()
    assert r[1]["current_extension_started_at"] is None      # episode closed
    assert r[2]["current_extension_started_at"] == T[2].isoformat()   # NEW episode
    assert r[3]["current_extension_started_at"] == T[2].isoformat()   # same episode
    assert r[4]["current_extension_started_at"] is None      # closed again

    # the most recent reset tracks the latest one
    assert r[1]["last_reset_at"] == T[1].isoformat()
    assert r[3]["last_reset_at"] == T[1].isoformat()
    assert r[4]["last_reset_at"] == T[4].isoformat()


def test_at_the_second_reset_the_current_episode_is_exactly_recoverable():
    """The four questions the previous contract could not answer, at T4."""
    r = _walk([(2.4, T[0], LIN_BEGIN), (1.6, T[1], LIN_CONT), (2.2, T[2], LIN_CONT),
               (2.5, T[3], LIN_CONT), (1.4, T[4], LIN_CONT)])[-1]
    assert r["last_reset_at"] == T[4].isoformat()             # Q2 latest reset
    assert r["first_reset_at"] == T[1].isoformat()            # Q1 untouched
    assert r["threshold_crossings"] == 4
    # Q3: the cycle T2->T4 is recoverable because T2 was persisted at T3.


def test_a_new_episode_does_not_disturb_first_reset_evidence():
    r = _walk([(2.4, T[0], LIN_BEGIN), (1.6, T[1], LIN_CONT), (2.2, T[2], LIN_CONT)])
    assert r[2]["first_reset_at"] == r[1]["first_reset_at"]
    assert r[2]["first_reset_wait_bars"] == r[1]["first_reset_wait_bars"]


def test_re_chase_is_distinguishable_from_an_actionable_reset():
    """The whole point of two axes: 'has reset' must not mean 'safe forever'."""
    r = _walk([(2.4, T[0], LIN_BEGIN), (1.6, T[1], LIN_CONT), (2.2, T[2], LIN_CONT)])
    actionable = r[1]["state"] == STATE_NOT_EXTENDED and r[1]["first_reset_at"]
    rechased = r[2]["state"] == STATE_EXTENDED and r[2]["first_reset_at"]
    assert actionable and rechased
    assert r[2]["current_extension_started_at"] is not None


def test_a_third_and_fourth_crossing_keep_updating_only_episode_fields():
    r = _walk([(2.4, T[0], LIN_BEGIN), (1.6, T[1], LIN_CONT), (2.2, T[2], LIN_CONT),
               (1.5, T[3], LIN_CONT), (2.6, T[4], LIN_CONT), (1.2, T[5], LIN_CONT)])
    assert all(x["first_reset_at"] == T[1].isoformat() for x in r[1:])
    assert r[5]["last_reset_at"] == T[5].isoformat()
    assert r[5]["threshold_crossings"] == 6
    assert r[4]["current_extension_started_at"] == T[4].isoformat()


def test_there_is_no_settled_state():
    r = _walk([(2.4, T[0], LIN_BEGIN), (1.6, T[1], LIN_CONT), (1.5, T[2], LIN_CONT)])
    assert {x["state"] for x in r} <= {
        STATE_NOT_EXTENDED, STATE_EXTENDED, STATE_EXPIRED, STATE_CLOSED,
        STATE_UNRESOLVED}
    assert "settled" not in str(r)


def test_the_episode_anchor_is_unique_per_episode():
    """(lineage_id, current_extension_started_at) must separate reset #1 from
    reset #2, or later microstructure capture cannot be attributed."""
    r = _walk([(2.4, T[0], LIN_BEGIN), (1.6, T[1], LIN_CONT), (2.2, T[2], LIN_CONT),
               (1.4, T[3], LIN_CONT)])
    anchors = {x["current_extension_started_at"] for x in r if x["state"] == STATE_EXTENDED}
    assert anchors == {T[0].isoformat(), T[2].isoformat()}


# ══ 2 · FIRST-RESET IMMUTABILITY ═══════════════════════════════════════════
def test_first_reset_is_written_exactly_once_per_lineage():
    r = _walk([(2.4, T[0], LIN_BEGIN), (1.6, T[1], LIN_CONT), (2.2, T[2], LIN_CONT),
               (1.4, T[3], LIN_CONT), (2.7, T[4], LIN_CONT), (1.1, T[5], LIN_CONT)])
    freezing = [i for i, x in enumerate(r)
                if x["first_reset_at"] == T[i].isoformat()]
    assert freezing == [1], f"first_reset froze on rows {freezing}"


def test_a_lineage_that_never_extended_never_produces_a_first_reset():
    r = _walk([(0.4, T[0], LIN_BEGIN), (0.9, T[1], LIN_CONT), (1.2, T[2], LIN_CONT)])
    assert all(x["first_reset_at"] is None for x in r)
    assert all(x["last_reset_at"] is None for x in r)
    assert all(x["threshold_crossings"] == 0 for x in r)


def test_first_reset_wait_bars_counts_evaluations_not_wall_clock():
    """Bars and minutes diverge when evaluations are skipped — that divergence is
    itself the finding, so the bar count must come from a carried counter rather
    than elapsed/duration arithmetic."""
    r = _walk([(2.4, T[0], LIN_BEGIN), (2.5, T[1], LIN_CONT), (2.6, T[2], LIN_CONT),
               (1.4, T[3], LIN_CONT)])
    assert r[3]["first_reset_wait_bars"] == 3
    # minutes stay derivable from the two persisted timestamps
    assert r[3]["extension_detected_at"] == T[0].isoformat()
    assert r[3]["first_reset_at"] == T[3].isoformat()


def test_a_gap_in_evaluation_does_not_inflate_the_bar_count():
    """Two evaluations, an hour apart: one bar of chase, not four."""
    late = T[0] + timedelta(hours=1)
    r = _walk([(2.4, T[0], LIN_BEGIN), (1.4, late, LIN_CONT)])
    assert r[1]["first_reset_wait_bars"] == 1


# ══ 3 · THRESHOLD SEMANTICS ════════════════════════════════════════════════
def test_the_reference_threshold_is_the_pre_registered_two_atr():
    assert RESET_REFERENCE_THRESHOLD == 2.0
    assert RESET_REFERENCE_THRESHOLD in (0.5, 1.0, 1.5, 2.0, 3.0)


def test_every_record_carries_the_threshold_it_was_evaluated_against():
    r = _walk([(2.4, T[0], LIN_BEGIN)])[0]
    assert r["extension_threshold"] == RESET_REFERENCE_THRESHOLD
    assert r["schema_version"] == RESET_SCHEMA_VERSION


def test_the_raw_extension_value_is_stored_unrounded_and_unthresholded():
    """Storing only a boolean would make every other X permanently unanswerable."""
    for ext in (0.37, 1.99, 2.0, 2.01, 7.4):
        r = _walk([(ext, T[0], LIN_BEGIN)])[0]
        assert r["extension_value"] == ext


def test_other_thresholds_remain_reconstructable_from_the_raw_series():
    r = _walk([(0.6, T[0], LIN_BEGIN), (1.7, T[1], LIN_CONT), (2.4, T[2], LIN_CONT),
               (1.1, T[3], LIN_CONT)])
    series = [x["extension_value"] for x in r]
    # at X=1.0 this lineage crossed up at T1 and back down at T3
    assert [v >= 1.0 for v in series] == [False, True, True, True]
    # at X=2.0 (the reference) only T2 is extended — a DIFFERENT answer
    assert [x["state"] == STATE_EXTENDED for x in r] == [False, False, True, False]


def test_the_boundary_is_inclusive_at_the_reference_threshold():
    assert _walk([(2.0, T[0], LIN_BEGIN)])[0]["state"] == STATE_EXTENDED
    assert _walk([(1.999, T[0], LIN_BEGIN)])[0]["state"] == STATE_NOT_EXTENDED


# ══ 4 · BOUNDARY RULES ═════════════════════════════════════════════════════
def test_a_terminated_lineage_that_was_extended_expires():
    r = _walk([(2.4, T[0], LIN_BEGIN)])
    end = _step(r[0], ext=None, at=T[1], lineage_state=LIN_TERM, prev_bar_time=T[0])
    assert end["state"] == STATE_EXPIRED
    assert end["extension_value"] is None


def test_a_terminated_lineage_that_never_extended_closes():
    r = _walk([(0.5, T[0], LIN_BEGIN)])
    end = _step(r[0], ext=None, at=T[1], lineage_state=LIN_TERM, prev_bar_time=T[0])
    assert end["state"] == STATE_CLOSED


@pytest.mark.parametrize("boundary", ["direction_flip", "neutral", "terminal_anchor",
                                      "safety_ceiling"])
def test_every_lineage_boundary_closes_the_reset_window(boundary):
    """Reset never re-derives a boundary — it consumes CP-J's verdict, so all
    four arrive as the same `terminated` lineage state and behave identically."""
    r = _walk([(2.4, T[0], LIN_BEGIN)])
    end = _step(r[0], ext=None, at=T[1], lineage_state=LIN_TERM, prev_bar_time=T[0])
    assert end["state"] == STATE_EXPIRED
    assert end["current_extension_started_at"] is None


def test_a_new_lineage_never_inherits_the_previous_lineages_reset_evidence():
    """After a flip the predecessor ROW still carries a full reset namespace.
    Carrying it would recreate the 97.2% aliasing defect at the reset layer."""
    old = _walk([(2.4, T[0], LIN_BEGIN), (1.6, T[1], LIN_CONT)])[-1]
    fresh = _step(old, ext=2.3, at=T[2], lineage_state=LIN_BEGIN, prev_bar_time=T[1])
    assert fresh["first_reset_at"] is None
    assert fresh["last_reset_at"] is None
    assert fresh["threshold_crossings"] == 1
    assert fresh["extension_detected_at"] == T[2].isoformat()
    assert fresh["current_extension_started_at"] == T[2].isoformat()


def test_a_fresh_lineage_below_threshold_starts_completely_empty():
    fresh = _step(None, ext=0.3, at=T[0], lineage_state=LIN_BEGIN)
    assert fresh["state"] == STATE_NOT_EXTENDED
    assert fresh["extension_detected_at"] is None
    assert fresh["current_extension_started_at"] is None
    assert fresh["threshold_crossings"] == 0


# ══ 5 · UNRESOLVED ═════════════════════════════════════════════════════════
def test_a_substituted_atr_never_produces_a_normalised_number():
    """The risk engine substitutes a flat 2% when ATR is NaN. Dividing by it
    yields a value that looks measured and is not."""
    r = _step(None, ext=3.1, at=T[0], lineage_state=LIN_BEGIN, atr_fallback_used=True)
    assert r["state"] == STATE_UNRESOLVED
    assert r["extension_value"] is None
    assert r["unresolved_reason"] == "atr_substituted"


def test_a_missing_extension_value_is_unresolved_not_zero():
    r = _step(None, ext=None, at=T[0], lineage_state=LIN_BEGIN)
    assert r["state"] == STATE_UNRESOLVED
    assert r["extension_value"] is None
    assert r["unresolved_reason"]


def test_an_unresolved_lineage_forces_an_unresolved_reset():
    r = _step(None, ext=2.4, at=T[0], lineage_state=LIN_UNRES)
    assert r["state"] == STATE_UNRESOLVED
    assert r["unresolved_reason"] == "lineage_unresolved"


def test_the_failure_payload_is_an_explicit_sentinel_never_a_bare_none():
    out = unresolved_reset_payload("PredecessorLookupError")
    assert out["state"] == STATE_UNRESOLVED
    assert out["unresolved_reason"] == "PredecessorLookupError"
    assert out["schema_version"] == RESET_SCHEMA_VERSION
    assert out["extension_value"] is None
    assert out is not None


def test_an_absent_namespace_is_distinguishable_from_a_failure():
    """Historical rows have no namespace at all; the backfill ban is only
    checkable while those two cases stay distinct."""
    historical = {"primary_demotion_reason": "published"}
    assert RESET_NAMESPACE not in historical
    failed = {RESET_NAMESPACE: unresolved_reset_payload("boom")}
    assert failed[RESET_NAMESPACE]["state"] == STATE_UNRESOLVED


def test_unresolved_carries_prior_evidence_forward_rather_than_erasing_it():
    prior = _walk([(2.4, T[0], LIN_BEGIN), (1.6, T[1], LIN_CONT)])[-1]
    r = _step(prior, ext=None, at=T[2], lineage_state=LIN_CONT, prev_bar_time=T[1])
    assert r["state"] == STATE_UNRESOLVED
    assert r["first_reset_at"] == T[1].isoformat(), "a blip erased frozen evidence"


def test_no_field_is_silently_dropped_on_any_path():
    """`None` inside a namespace must remain an explicit null, never a missing
    key — a missing key reads as 'this build predates the field'."""
    expected = {"schema_version", "state", "extension_value", "extension_threshold",
                "atr_source", "extension_detected_at", "first_reset_at",
                "first_reset_wait_bars", "bars_in_current_extension",
                "current_extension_started_at", "last_reset_at",
                "threshold_crossings", "unresolved_reason"}
    for rec in (_step(None, ext=2.4, at=T[0], lineage_state=LIN_BEGIN),
                _step(None, ext=0.2, at=T[0], lineage_state=LIN_BEGIN),
                _step(None, ext=None, at=T[0], lineage_state=LIN_TERM),
                unresolved_reset_payload("x")):
        assert set(rec) == expected, f"field set drifted: {set(rec) ^ expected}"


# ══ 6 · RESTART / IDEMPOTENCY ══════════════════════════════════════════════
def test_the_decision_is_a_pure_function_of_persisted_inputs():
    """Restart safety is structural: given the same predecessor namespace the
    answer is identical, so nothing can be lost with process memory."""
    prev = _walk([(2.4, T[0], LIN_BEGIN), (1.6, T[1], LIN_CONT)])[-1]
    a = _step(prev, ext=2.2, at=T[2], prev_bar_time=T[1])
    b = _step(dict(prev), ext=2.2, at=T[2], prev_bar_time=T[1])
    assert a == b


def test_the_module_holds_no_mutable_state():
    """Private names count too. An earlier version skipped anything starting with
    an underscore, so a mutant that installed `_EPISODE_CACHE = {}` as the real
    authority survived — which is exactly the restart-unsafe design this contract
    exists to forbid."""
    import app.services.reset_lifecycle as rl

    containers = [n for n in vars(rl)
                  if not (n.startswith("__") and n.endswith("__"))
                  and type(vars(rl)[n]).__name__ in ("dict", "list", "set")]
    assert containers == [], f"reset lifecycle kept authority in memory: {containers}"


# ══ 7 · SAME-BAR REPLAY ════════════════════════════════════════════════════
def test_replaying_the_same_bar_returns_the_recorded_namespace_verbatim():
    """The row is keyed on the bar with ON CONFLICT DO NOTHING, so a replay
    writes nothing — but it must not COMPUTE a different episode that the
    conflict then hides."""
    prev = _walk([(2.4, T[0], LIN_BEGIN), (1.6, T[1], LIN_CONT)])[-1]
    again = _step(prev, ext=1.6, at=T[1], prev_bar_time=T[1])
    assert again == prev


def test_a_replay_cannot_create_a_second_episode_or_bump_the_counter():
    prev = _walk([(2.4, T[0], LIN_BEGIN), (1.6, T[1], LIN_CONT), (2.2, T[2], LIN_CONT)])[-1]
    again = _step(prev, ext=2.2, at=T[2], prev_bar_time=T[2])
    assert again["threshold_crossings"] == prev["threshold_crossings"]
    assert again["current_extension_started_at"] == prev["current_extension_started_at"]


# ══ 8 · FORBIDDEN SURFACES · NO FUTURE DATA · NO RUNTIME READS ═════════════
def test_the_module_does_not_name_the_guarded_observation_tokens():
    src = (BACKEND / "app" / "services" / "reset_lifecycle.py").read_text(encoding="utf-8")
    for token in ("extension_from_low_atr", "range_position_pct", "bars_since_low",
                  "shadow_observation_v1"):
        assert token not in src, f"guarded observation token leaked: {token}"


def test_the_module_names_no_frozen_predicate():
    src = (BACKEND / "app" / "services" / "reset_lifecycle.py").read_text(encoding="utf-8")
    for token in ("would_keep", "would_filter", "sl_dist_lt_"):
        assert token not in src, token


def test_the_reference_threshold_never_appears_in_a_runtime_file():
    """It is a shadow label. If a decision file ever names it, it has become a
    gate — which this CP forbids."""
    hits = []
    for p in (BACKEND / "app").rglob("*.py"):
        if "__pycache__" in str(p) or p.name == "reset_lifecycle.py":
            continue
        src = p.read_text(encoding="utf-8", errors="ignore")
        if "RESET_REFERENCE_THRESHOLD" in src and p.name != "candidate_log.py":
            hits.append(p.name)
    assert hits == [], f"the shadow threshold reached the runtime: {hits}"


def test_no_runtime_branch_reads_the_reset_namespace():
    hits = []
    for p in (BACKEND / "app").rglob("*.py"):
        if "__pycache__" in str(p) or p.name in ("reset_lifecycle.py", "candidate_log.py"):
            continue
        src = p.read_text(encoding="utf-8", errors="ignore")
        for token in (RESET_NAMESPACE, "threshold_crossings", "last_reset_at"):
            if token in src:
                hits.append(f"{p.name}:{token}")
    assert hits == [], f"reset evidence leaked into the runtime: {hits}"


def test_future_outcome_cannot_enter_the_decision_signature():
    import inspect

    params = set(inspect.signature(decide_reset_lifecycle).parameters)
    for future in ("outcome", "shadow_outcome", "result", "tp", "sl", "stop",
                   "expiry", "entry_reached", "mfe", "mae", "pnl", "r_multiple",
                   "realized", "realised"):
        assert future not in params, f"future data reached identity: {future}"


def test_timestamps_use_the_pinned_utc_isoformat():
    r = _walk([(2.4, T[0], LIN_BEGIN), (1.6, T[1], LIN_CONT)])[-1]
    for key in ("extension_detected_at", "first_reset_at", "last_reset_at"):
        value = r[key]
        assert value.endswith("+00:00"), f"{key} lost its offset: {value}"
        assert "T" in value, f"{key} is not isoformat: {value}"
        datetime.strptime(value, ISO)


def test_the_record_is_strict_json():
    import json

    r = _walk([(2.4, T[0], LIN_BEGIN), (1.6, T[1], LIN_CONT)])[-1]
    json.dumps(r, allow_nan=False)


# ══ GAPS FOUND BY SABOTAGE ═════════════════════════════════════════════════
def test_the_module_imports_no_mutating_construct():
    """S6. A substring ban on 'update(' misses `from sqlalchemy import update`,
    so the import list is inspected instead of the text."""
    import ast

    src = (BACKEND / "app" / "services" / "reset_lifecycle.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom):
            names = {a.name for a in node.names}
            for banned in ("update", "delete", "insert"):
                assert banned not in names, f"reset lifecycle imports {banned}"


def test_replaying_an_extended_bar_does_not_advance_its_episode_counter():
    """S9. Replaying a bar that is BELOW the threshold is indistinguishable from
    recomputation — both legitimately produce the same record, so it proves
    nothing. The discriminating case is replaying an EXTENDED bar, where
    recomputation would advance `bars_in_current_extension`."""
    prev = _walk([(2.4, T[0], LIN_BEGIN), (2.5, T[1], LIN_CONT)])[-1]
    assert prev["bars_in_current_extension"] == 2
    again = _step(prev, ext=2.5, at=T[1], prev_bar_time=T[1])
    assert again == prev
    assert again["bars_in_current_extension"] == 2, "a replay advanced the episode"


# ══ WIRING — the namespace must actually reach the row ═════════════════════
class _FakeRes:
    def __init__(self, row=None):
        self._row = row

    def first(self):
        return self._row

    def scalar_one_or_none(self):
        return "row-id"


class _WiredDB:
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

    idx = pd.date_range("2026-08-20", periods=60, freq="15min", tz="UTC")
    df = pd.DataFrame({"open": [100.0] * 60, "high": [101.0] * 60,
                       "low": [99.0] * 60, "close": [100.0 + i for i in range(60)],
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
              df=df, evaluated_at=T[0], verdict="dropped",
              demotion_reason="not_actionable", final_signal_type="BUY",
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
async def test_the_reset_namespace_actually_reaches_the_inserted_row():
    """S1. Every other test here exercises the pure decision; without this one a
    mutant that simply never merges the namespace passes everything."""
    from app.services import candidate_log

    db = _WiredDB(predecessor=None)
    assert await candidate_log.record_candidate(db, **_wire_kw()) is True
    extra = _written_extra(db) or {}
    assert RESET_NAMESPACE in extra, "the reset namespace never reached the row"
    ns = extra[RESET_NAMESPACE]
    assert ns["schema_version"] == RESET_SCHEMA_VERSION
    assert ns["extension_threshold"] == RESET_REFERENCE_THRESHOLD
    assert ns["state"] in (STATE_NOT_EXTENDED, STATE_EXTENDED, STATE_UNRESOLVED)


@pytest.mark.asyncio
async def test_the_reset_namespace_does_not_disturb_its_neighbours():
    from app.services import candidate_log
    from app.services.candidate_lineage import LINEAGE_NAMESPACE

    db = _WiredDB(predecessor=None)
    await candidate_log.record_candidate(db, **_wire_kw())
    extra = _written_extra(db) or {}
    for neighbour in (LINEAGE_NAMESPACE, "primary_demotion_reason",
                      "decision_input_version", "threshold_direction"):
        assert neighbour in extra, f"reset telemetry destroyed {neighbour}"


@pytest.mark.asyncio
async def test_one_insert_and_one_predecessor_read_per_candidate():
    """The reset namespace must ride the lineage lookup, not add a second."""
    from app.services import candidate_log

    db = _WiredDB(predecessor=None)
    await candidate_log.record_candidate(db, **_wire_kw())
    inserts = [s for s in db.statements if "INSERT" in str(s).upper()[:80]]
    selects = [s for s in db.statements if "SELECT" in str(s).upper()[:80]]
    assert len(inserts) == 1, f"expected 1 INSERT, saw {len(inserts)}"
    assert len(selects) <= 1, f"reset added a second read: {len(selects)} selects"


# ══ DEFECTS FOUND IN ADVERSARIAL PRE-COMMIT REVIEW ═════════════════════════
@pytest.mark.asyncio
async def test_the_atr_fallback_flag_comes_from_the_authoritative_source():
    """`atr_pct_regime is None` cannot detect ATR substitution and mislabels the
    one case it does catch.

    The regime detector returns atr_pct=0.0, never None, when ATR is NaN
    (detector.py:119), so `is None` is true only when detect_regime CRASHED — and
    stamping that as 'atr_substituted' asserts something false about the ATR. The
    real flag is computed at signal_generator.py:360 and travels in
    birth_telemetry, which is in scope on this path.
    """
    from app.services import candidate_log

    kw = _wire_kw()
    kw["decision"] = dict(kw["decision"])
    kw["decision"]["birth_telemetry"] = {"atr_pct": 0.5, "atr_fallback_used": True}
    db = _WiredDB(predecessor=None)
    await candidate_log.record_candidate(db, **kw)
    ns = (_written_extra(db) or {})[RESET_NAMESPACE]
    assert ns["state"] == STATE_UNRESOLVED
    assert ns["unresolved_reason"] == "atr_substituted"
    assert ns["extension_value"] is None


@pytest.mark.asyncio
async def test_a_healthy_atr_is_not_reported_as_substituted():
    from app.services import candidate_log

    kw = _wire_kw()
    kw["decision"] = dict(kw["decision"])
    kw["decision"]["birth_telemetry"] = {"atr_pct": 0.5, "atr_fallback_used": False}
    db = _WiredDB(predecessor=None)
    await candidate_log.record_candidate(db, **kw)
    ns = (_written_extra(db) or {})[RESET_NAMESPACE]
    assert ns["unresolved_reason"] != "atr_substituted"


def test_the_predecessor_read_is_savepoint_isolated():
    """A SELECT issued on the caller's session in front of its staged writes must
    not be able to abort them. candidate_log's own docstring names this exact
    fail-open-becomes-fail-closed trap: the caller may be holding a staged
    reversal close, and a server-side error without a SAVEPOINT poisons the whole
    transaction."""
    import inspect

    from app.services import candidate_log

    src = inspect.getsource(candidate_log.record_candidate)
    head = src.split("load_predecessor(", 1)[0]
    assert "begin_nested()" in head, \
        "the predecessor read is not inside a savepoint"
