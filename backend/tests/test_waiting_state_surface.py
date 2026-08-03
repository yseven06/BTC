"""CP-ENTRY-WAITING-STATE-SURFACE — history + status-vocabulary contract.

Two debts, both of which failed SILENTLY in production for 49 minutes while
every health check stayed green:

  A. `signal_status_history` never learned the word `waiting_entry`. The birth
     row hardcoded to_status="active" THIRTEEN LINES BELOW the constructor that
     set live_status=WAITING_ENTRY, and the fill promotion ran before the
     lifecycle evaluator, so `prev_status` was already "active" by the time the
     evaluator's change test ran and the promotion was never logged. A signal
     that waited 3m13s for its entry read, in its own audit trail, as "born
     active, nothing ever happened".

  B. The frontend had no `waiting_entry` key, and every surface fell back to
     `active` — so a signal that had NOT been entered rendered as a green
     "Aktif" pill on the dashboard, the detail panel and the public landing
     page, while LifecycleJourney printed the raw token `waiting_entry`.

Neither raised. Both are the same failure shape: a NEW value flowing into a
lookup that silently answers with an OLD one. So the tests below do not assert
"today's output" — they assert the PROPERTY that makes the bug unrepresentable
(the birth row is DERIVED from the column; the fallback cannot be `active`), and
the sabotage section builds the previous wrong implementation first to prove
each test can actually see it.
"""

from __future__ import annotations

import inspect
import pathlib
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.backtesting import labels as L
from app.backtesting import lifecycle
from app.models.signal import SignalOutcome
from app.services.lifecycle_log import apply_live_status, birth_event, make_event

TRACKER = "app/backtesting/tracker.py"
SCHEDULER = "app/services/scheduler.py"
API_SIGNALS = "app/api/routes/signals.py"
BADGE = "../frontend/src/components/ui/LiveStatusBadge.tsx"
JOURNEY = "../frontend/src/components/ui/LifecycleJourney.tsx"
GATES = "../frontend/scripts/design-gates.mjs"

T0 = datetime(2026, 8, 3, 14, 22, 21, 418626, tzinfo=timezone.utc)


def _src(rel: str) -> str:
    return pathlib.Path(rel).read_text(encoding="utf-8")


def _sig(status="active", since=T0):
    """Minimal stand-in for a Signal row. apply_live_status only ever touches
    these five attributes, and using a real model here would drag in a session."""
    return SimpleNamespace(
        id=uuid4(), live_status=status, live_status_since=since,
        status_reason=None, status_updated_at=None,
    )


def _perf():
    return SimpleNamespace(
        outcome=None, detail_label=None, resolution_source=None,
        resolution_version=None, closed_at=None, detected_at=None, is_expired=None,
        actual_return=1.0, max_drawdown=1.0, mfe_pct=1.0, bars_to_outcome=7,
        hit_time=object(), tp1_hit_at=object(), tp2_hit_at=object(), tp3_hit_at=object(),
        hit_tp1=True, hit_tp2=True, hit_tp3=True,
    )


# ───────────────────────── A. apply_live_status behaviour ────────────────────

def test_A1_unchanged_phase_emits_no_row():
    s = _sig("active")
    assert apply_live_status(s, to_status="active", reason="r", at=T0) is None


def test_A2_unchanged_phase_does_not_move_since():
    s = _sig("active", since=T0)
    later = T0 + timedelta(minutes=5)
    apply_live_status(s, to_status="active", reason="r", at=later)
    assert s.live_status_since == T0, "an unchanged phase must not restart its clock"


def test_A3_unchanged_phase_still_refreshes_reason_and_stamp():
    # The reason is the CURRENT assessment, not a property of the transition —
    # this matched the previous inline behaviour and must survive the refactor.
    s = _sig("active")
    later = T0 + timedelta(minutes=5)
    apply_live_status(s, to_status="active", reason="yeni gerekçe", at=later)
    assert s.status_reason == "yeni gerekçe"
    assert s.status_updated_at == later


def test_A4_changed_phase_emits_row_and_moves_status():
    s = _sig(lifecycle.WAITING_ENTRY)
    at = T0 + timedelta(minutes=4)
    ev = apply_live_status(s, to_status=lifecycle.ACTIVE, reason="r", at=at)
    assert ev is not None
    assert s.live_status == lifecycle.ACTIVE
    assert s.live_status_since == at


def test_A5_row_carries_both_ends_of_the_move():
    s = _sig(lifecycle.WAITING_ENTRY)
    ev = apply_live_status(s, to_status=lifecycle.ACTIVE, reason="r", at=T0)
    assert ev.from_status == lifecycle.WAITING_ENTRY
    assert ev.to_status == lifecycle.ACTIVE


def test_A6_timestamp_parity_row_equals_since():
    # A reader joining history to signals cannot tell real ordering from clock
    # skew unless these are the SAME instant, not two now() calls.
    s = _sig(lifecycle.WAITING_ENTRY)
    at = T0 + timedelta(seconds=193)
    ev = apply_live_status(s, to_status=lifecycle.ACTIVE, reason="r", at=at)
    assert ev.created_at == at == s.live_status_since


def test_A7_first_ever_status_is_a_birth():
    s = _sig(None, since=None)
    ev = apply_live_status(s, to_status=lifecycle.WAITING_ENTRY, reason="r", at=T0)
    assert ev.kind == "birth" and ev.from_status is None


def test_A8_subsequent_change_is_a_transition():
    s = _sig(lifecycle.WAITING_ENTRY)
    ev = apply_live_status(s, to_status=lifecycle.ACTIVE, reason="r", at=T0)
    assert ev.kind == "transition"


def test_A9_same_status_but_no_since_still_emits():
    # A row whose clock was never started is not "unchanged" — it has never been
    # recorded at all.
    s = _sig("active", since=None)
    assert apply_live_status(s, to_status="active", reason="r", at=T0) is not None


def test_A10_explicit_kind_overrides_the_derived_one():
    s = _sig(lifecycle.WAITING_ENTRY)
    ev = apply_live_status(s, to_status="closed", reason="r", at=T0, kind="resolution")
    assert ev.kind == "resolution"


def test_A11_context_fields_pass_through():
    s = _sig(lifecycle.WAITING_ENTRY)
    ev = apply_live_status(
        s, to_status=lifecycle.ACTIVE, reason="r", at=T0,
        regime="trending_up", price=1.436, retrace_to_sl=0.25,
        progress_to_tp=0.5, structure_event="bos", momentum_dir="up",
    )
    assert (ev.regime, ev.price, ev.structure_event, ev.momentum_dir) == (
        "trending_up", 1.436, "bos", "up")
    assert (ev.retrace_to_sl, ev.progress_to_tp) == (0.25, 0.5)


def test_A12_waiting_entry_is_reachable_as_a_destination():
    s = _sig("approaching_tp")
    ev = apply_live_status(
        s, to_status=lifecycle.WAITING_ENTRY,
        reason=lifecycle.REASON_WAITING_ENTRY, at=T0)
    assert ev.to_status == lifecycle.WAITING_ENTRY
    assert ev.from_status == "approaching_tp"


# ───────────────────────── B. birth_event derives, never asserts ─────────────

def test_B1_birth_row_mirrors_waiting_entry():
    s = _sig(lifecycle.WAITING_ENTRY)
    assert birth_event(s, reason="Sinyal üretildi").to_status == lifecycle.WAITING_ENTRY


def test_B2_birth_row_mirrors_legacy_active():
    s = _sig(lifecycle.ACTIVE)
    assert birth_event(s, reason="Sinyal üretildi").to_status == lifecycle.ACTIVE


def test_B3_birth_row_shape():
    ev = birth_event(_sig(lifecycle.WAITING_ENTRY), reason="Sinyal üretildi", regime="chop")
    assert ev.from_status is None and ev.kind == "birth" and ev.regime == "chop"


def test_B4_birth_timestamp_follows_the_signal():
    s = _sig(lifecycle.WAITING_ENTRY, since=T0)
    assert birth_event(s, reason="r").created_at == T0


def test_B5_birth_row_CANNOT_disagree_with_the_column():
    # THE property. The old code hardcoded "active" next to a constructor that
    # wrote waiting_entry; deriving makes that disagreement unrepresentable for
    # every status the machine will ever have, including ones not invented yet.
    for status in (lifecycle.WAITING_ENTRY, lifecycle.ACTIVE, lifecycle.WEAKENING,
                   lifecycle.APPROACHING_TP, lifecycle.INVALIDATING, "a_future_phase"):
        assert birth_event(_sig(status), reason="r").to_status == status


# ───────────────────────── C. make_event created_at handling ────────────────

def test_C1_created_at_left_unset_when_not_given():
    # SQLAlchemy omits an UNSET column from the INSERT so the server_default
    # fires; explicitly assigning None puts it in __dict__ and sends NULL into a
    # NOT NULL column instead. The distinction is presence in __dict__, not the
    # value — `ev.created_at is None` is true either way.
    ev = make_event(signal_id=uuid4(), to_status="active")
    assert "created_at" not in ev.__dict__, "must stay unset so server_default applies"


def test_C1b_created_at_is_set_when_given():
    ev = make_event(signal_id=uuid4(), to_status="active", created_at=T0)
    assert "created_at" in ev.__dict__ and ev.created_at == T0


def test_C2_created_at_used_when_given():
    ev = make_event(signal_id=uuid4(), to_status="active", created_at=T0)
    assert ev.created_at == T0


# ───────────────────────── D. no-fill close now logs ─────────────────────────

def _close_without_fill():
    from app.backtesting.tracker import _close_without_fill as f
    return f


def test_D1_no_fill_close_returns_a_resolution_row():
    ev = _close_without_fill()(
        _sig(lifecycle.WAITING_ENTRY), _perf(), outcome=SignalOutcome.EXPIRED,
        detail_label=L.EXPIRED_WITHOUT_ENTRY, resolution_source=L.RES_SRC_EXPIRY_NO_FILL,
        closed_at=T0, is_expired=True)
    assert ev is not None and ev.to_status == "closed" and ev.kind == "resolution"


def test_D2_no_fill_close_origin_is_the_phase_it_was_actually_in():
    # Captured BEFORE the function forces live_status to waiting_entry — reading
    # it afterwards would report waiting_entry for every signal, including one
    # that was still labelled approaching_tp when it expired.
    s = _sig("approaching_tp")
    ev = _close_without_fill()(
        s, _perf(), outcome=SignalOutcome.EXPIRED,
        detail_label=L.EXPIRED_WITHOUT_ENTRY, resolution_source=L.RES_SRC_EXPIRY_NO_FILL,
        closed_at=T0, is_expired=True)
    assert ev.from_status == "approaching_tp"
    assert s.live_status == lifecycle.WAITING_ENTRY


def test_D3_no_fill_close_never_invents_an_active_hop():
    s = _sig(lifecycle.WAITING_ENTRY)
    ev = _close_without_fill()(
        s, _perf(), outcome=SignalOutcome.EXPIRED,
        detail_label=L.EXPIRED_WITHOUT_ENTRY, resolution_source=L.RES_SRC_EXPIRY_NO_FILL,
        closed_at=T0, is_expired=True)
    assert ev.from_status == lifecycle.WAITING_ENTRY != lifecycle.ACTIVE


def test_D4_no_fill_close_carries_outcome_and_label():
    ev = _close_without_fill()(
        _sig(lifecycle.WAITING_ENTRY), _perf(), outcome=SignalOutcome.EXPIRED,
        detail_label=L.EXPIRED_WITHOUT_ENTRY, resolution_source=L.RES_SRC_EXPIRY_NO_FILL,
        closed_at=T0, is_expired=True)
    assert ev.outcome == SignalOutcome.EXPIRED.value
    assert ev.reason == L.label_tr(L.EXPIRED_WITHOUT_ENTRY)


def test_D5_no_fill_close_timestamp_matches_the_resolution():
    p = _perf()
    ev = _close_without_fill()(
        _sig(lifecycle.WAITING_ENTRY), p, outcome=SignalOutcome.EXPIRED,
        detail_label=L.EXPIRED_WITHOUT_ENTRY, resolution_source=L.RES_SRC_EXPIRY_NO_FILL,
        closed_at=T0, is_expired=True)
    assert ev.created_at == p.detected_at


def test_D6_REGRESSION_no_fill_metrics_are_still_all_null():
    # The whole point of the previous checkpoint. Adding a history row must not
    # have disturbed it.
    p = _perf()
    _close_without_fill()(
        _sig(lifecycle.WAITING_ENTRY), p, outcome=SignalOutcome.EXPIRED,
        detail_label=L.EXPIRED_WITHOUT_ENTRY, resolution_source=L.RES_SRC_EXPIRY_NO_FILL,
        closed_at=T0, is_expired=True)
    assert p.actual_return is None and p.max_drawdown is None
    assert p.mfe_pct is None and p.bars_to_outcome is None
    assert p.hit_tp1 is False and p.hit_tp2 is False and p.hit_tp3 is False
    assert p.tp1_hit_at is None and p.hit_time is None
    assert p.resolution_version == L.resolution_version_for(True)


# ───────────────────────── E. wiring (source-level, unavoidable) ─────────────

def test_E1_scheduler_birth_derives_and_never_hardcodes():
    src = _src(SCHEDULER)
    assert "birth_event(" in src
    assert 'to_status="active"' not in src, "birth row must be derived, not asserted"


def test_E2_api_birth_path_has_parity_with_the_scheduler():
    # This path wrote NO birth row at all, so a manually generated signal's
    # journey began at its first transition.
    assert "birth_event(new_signal" in _src(API_SIGNALS)


def test_E3_gate_records_entry_into_waiting():
    blk = _src(TRACKER).split("            _gate = None")[1].split("_bw = _resolve_signal_bar_walk")[0]
    assert "apply_live_status(" in blk
    assert "to_status=lifecycle.WAITING_ENTRY" in blk


def test_E4_gate_records_the_fill_promotion():
    blk = _src(TRACKER).split("            _gate = None")[1].split("_bw = _resolve_signal_bar_walk")[0]
    promo = blk.split("# Filled.")[1]
    assert "apply_live_status(" in promo and "to_status=lifecycle.ACTIVE" in promo
    assert "db.add(" in promo, "the promotion row must actually be persisted"


def test_E5_gate_uses_one_clock_for_the_whole_decision():
    blk = _src(TRACKER).split("            _gate = None")[1].split("_bw = _resolve_signal_bar_walk")[0]
    assert "_gate_now = datetime.now(timezone.utc)" in blk
    assert blk.count("datetime.now(timezone.utc)") == 1, (
        "three separate now() calls cannot be ordered against each other")


def test_E6_lifecycle_block_shares_the_same_helper():
    src = _src(TRACKER)
    assert src.count("apply_live_status(") == 3, (
        "waiting-entry, promotion and lifecycle must all route through one helper")


def test_E7_expiry_without_fill_persists_its_row():
    blk = _src(TRACKER).split("            _gate = None")[1].split("_bw = _resolve_signal_bar_walk")[0]
    assert "db.add(_close_without_fill(" in blk


def test_E8_LOCKED_severity_axis_still_excludes_waiting_entry():
    # evaluate_lifecycle must never see waiting_entry as prev_status: a missing
    # key reads as severity 0 and would let a de-escalation decide from a state
    # the model does not have.
    assert lifecycle.WAITING_ENTRY not in getattr(lifecycle, "_SEVERITY", {})


def test_E9_reason_constants_are_real_turkish_not_stripped_ascii():
    # These reach the badge tooltip. They shipped as "Giris seviyesi henuz
    # gorulmedi" and that is what users read.
    for text in (lifecycle.REASON_WAITING_ENTRY, lifecycle.REASON_ENTRY_TOUCHED,
                 lifecycle.REASON_NEVER_ENTERED):
        assert any(ch in text for ch in "şüğıçöİŞÜĞÇÖ"), f"diacritics stripped: {text!r}"


def test_E10_reasons_are_referenced_not_retyped():
    src = _src(TRACKER)
    assert "lifecycle.REASON_WAITING_ENTRY" in src
    assert "lifecycle.REASON_NEVER_ENTERED" in src
    assert "Giris seviyesi" not in src, "ASCII literal survived somewhere"


def test_E11_lifecycle_log_does_not_import_backtesting():
    # Keeps the observability leaf importable from both sides without a cycle,
    # and out of reach of the production-module import guard.
    import app.services.lifecycle_log as mod
    assert "app.backtesting" not in inspect.getsource(mod)


# ───────────────────────── F. duplicate / restart idempotency ────────────────

def test_F1_repeating_the_same_pass_writes_one_row_then_nothing():
    s = _sig(lifecycle.WAITING_ENTRY)
    first = apply_live_status(s, to_status=lifecycle.ACTIVE, reason="r", at=T0)
    second = apply_live_status(s, to_status=lifecycle.ACTIVE, reason="r",
                               at=T0 + timedelta(minutes=2))
    assert first is not None and second is None


def test_F2_restart_replays_from_the_persisted_column_not_from_memory():
    # After a restart the tracker re-reads live_status from the DB. Simulate a
    # fresh object carrying the already-committed status.
    s = _sig(lifecycle.WAITING_ENTRY)
    apply_live_status(s, to_status=lifecycle.ACTIVE, reason="r", at=T0)
    reloaded = _sig(s.live_status, since=s.live_status_since)
    assert apply_live_status(reloaded, to_status=lifecycle.ACTIVE, reason="r",
                             at=T0 + timedelta(hours=1)) is None


def test_F3_a_real_round_trip_still_logs_both_legs():
    s = _sig(lifecycle.WAITING_ENTRY)
    a = apply_live_status(s, to_status=lifecycle.ACTIVE, reason="r", at=T0)
    b = apply_live_status(s, to_status=lifecycle.WAITING_ENTRY, reason="r",
                          at=T0 + timedelta(minutes=2))
    assert a.to_status == lifecycle.ACTIVE and b.to_status == lifecycle.WAITING_ENTRY


# ───────────────────────── G. frontend vocabulary contract ───────────────────
# No React test runner exists in this repo; the enforcement point is the CI
# design gate (frontend/scripts/design-gates.mjs, gate-7, run by
# `npm run lint:design:strict`). These assertions are the second, independent
# mechanism so a frontend-only revert cannot pass the backend suite either.

def test_G1_waiting_entry_is_mapped():
    assert re.search(r"\bwaiting_entry\s*:\s*\{", _src(BADGE))


def test_G2_label_is_the_canonical_user_text():
    assert re.search(r"label:\s*['\"]Giriş Bekleniyor['\"]", _src(BADGE))


def test_G3_waiting_entry_is_not_green():
    row = next(l for l in _src(BADGE).splitlines() if re.search(r"\bwaiting_entry\s*:\s*\{", l))
    assert "bullish" not in row, "an unfilled signal must not wear the active colour"


def test_G4_unknown_status_has_its_own_meta():
    assert "export const UNKNOWN_STATUS_META" in _src(BADGE)
    assert "export function statusMeta" in _src(BADGE)


def test_G5_nothing_falls_back_to_active():
    for rel in (BADGE, JOURNEY, "../frontend/src/components/ui/IntelligencePanel.tsx",
                "../frontend/src/app/page.tsx"):
        src = _src(rel)
        assert not re.search(r"LIVE_STATUS_META\s*\.\s*active", src), rel
        assert not re.search(r"\|\|\s*['\"]Aktif['\"]", src), rel


def test_G6_raw_token_cannot_reach_the_user():
    assert not re.search(r"\?\?\s*s\s*[;,)]", _src(JOURNEY)), (
        "`?? s` printed the literal string waiting_entry into the timeline")


def test_G7_timeline_has_a_dot_for_the_waiting_phase():
    j = _src(JOURNEY)
    assert re.search(r"PHASE_DOT[\s\S]{0,240}?waiting_entry\s*:", j)


def test_G8_the_gate_that_enforces_all_of_this_exists():
    g = _src(GATES)
    assert "gate-7" in g and "gate7Fail" in g
    assert "gate7Fail" in g.split("process.exit")[1], "gate-7 must be able to fail the build"


# ───────────────────────── SABOTAGE ──────────────────────────────────────────
# Each rebuilds the previous WRONG implementation and shows the corresponding
# test above can actually see it. A test that only asserts today's output would
# pass against the broken version too.

def test_S1_hardcoding_the_birth_status_is_caught():
    def broken_birth(signal, *, reason, regime=None, created_at=None):
        return make_event(signal_id=signal.id, from_status=None,
                          to_status="active", kind="birth", reason=reason)
    s = _sig(lifecycle.WAITING_ENTRY)
    assert broken_birth(s, reason="r").to_status == "active"
    assert birth_event(s, reason="r").to_status == lifecycle.WAITING_ENTRY
    assert broken_birth(s, reason="r").to_status != birth_event(s, reason="r").to_status


def test_S2_promoting_without_logging_is_caught():
    # The shipped bug: mutate the column, emit nothing, and the evaluator's own
    # change test is then false because prev_status already reads "active".
    s = _sig(lifecycle.WAITING_ENTRY)
    s.live_status = lifecycle.ACTIVE          # hand-rolled promotion
    s.live_status_since = T0
    prev_status = s.live_status               # what tracker.py:1097 would read
    assert prev_status == lifecycle.ACTIVE
    assert apply_live_status(s, to_status=lifecycle.ACTIVE, reason="r", at=T0) is None, (
        "this is exactly why the fill vanished from the timeline")
    fresh = _sig(lifecycle.WAITING_ENTRY)
    assert apply_live_status(fresh, to_status=lifecycle.ACTIVE, reason="r", at=T0) is not None


def test_S3_dropping_the_change_test_duplicates_rows():
    def broken_apply(signal, *, to_status, reason, at):
        signal.live_status = to_status
        signal.live_status_since = at
        return make_event(signal_id=signal.id, from_status=to_status,
                          to_status=to_status, kind="transition", created_at=at)
    s = _sig(lifecycle.ACTIVE)
    rows = [broken_apply(s, to_status=lifecycle.ACTIVE, reason="r", at=T0) for _ in range(3)]
    assert len(rows) == 3, "every pass would write a row"
    s2 = _sig(lifecycle.ACTIVE)
    kept = [apply_live_status(s2, to_status=lifecycle.ACTIVE, reason="r", at=T0)
            for _ in range(3)]
    assert [r for r in kept if r is not None] == []


def test_S4_omitting_created_at_breaks_timestamp_parity():
    s = _sig(lifecycle.WAITING_ENTRY)
    loose = make_event(signal_id=s.id, from_status=lifecycle.WAITING_ENTRY,
                       to_status=lifecycle.ACTIVE, kind="transition")
    assert "created_at" not in loose.__dict__, (
        "would be filled by the DB clock, not the signal's — no parity possible")
    tight = apply_live_status(s, to_status=lifecycle.ACTIVE, reason="r", at=T0)
    assert tight.created_at == s.live_status_since


def test_S5_reading_the_origin_after_the_mutation_erases_it():
    # _close_without_fill forces live_status to waiting_entry. Capturing
    # from_status afterwards would report waiting_entry for EVERY signal.
    s = _sig("approaching_tp")
    ev = _close_without_fill()(
        s, _perf(), outcome=SignalOutcome.EXPIRED,
        detail_label=L.EXPIRED_WITHOUT_ENTRY, resolution_source=L.RES_SRC_EXPIRY_NO_FILL,
        closed_at=T0, is_expired=True)
    after = s.live_status
    assert after == lifecycle.WAITING_ENTRY
    assert ev.from_status == "approaching_tp" != after


def test_S6_deleting_the_frontend_mapping_is_caught():
    broken = re.sub(r"\n\s*waiting_entry:\s*\{[^\n]*\n", "\n", _src(BADGE), count=1)
    assert not re.search(r"\bwaiting_entry\s*:\s*\{", broken)
    assert re.search(r"\bwaiting_entry\s*:\s*\{", _src(BADGE))


def test_S7_an_active_fallback_is_caught():
    broken = "const meta = LIVE_STATUS_META[current.status] ?? LIVE_STATUS_META.active;"
    assert re.search(r"LIVE_STATUS_META\s*\.\s*active", broken)
    assert not re.search(r"LIVE_STATUS_META\s*\.\s*active", _src(BADGE))


def test_S8_a_raw_token_leak_is_caught():
    broken = "const phaseLabel = (s: string) => LIVE_STATUS_META[s]?.label ?? s;"
    assert re.search(r"\?\?\s*s\s*[;,)]", broken)
    assert not re.search(r"\?\?\s*s\s*[;,)]", _src(JOURNEY))


def test_S9_a_green_waiting_pill_is_caught():
    broken = "  waiting_entry: { label: 'Giriş Bekleniyor', cls: 'text-bullish', bg: 'bg-bullish/10' },"
    assert "bullish" in broken
    row = next(l for l in _src(BADGE).splitlines() if re.search(r"\bwaiting_entry\s*:\s*\{", l))
    assert "bullish" not in row


def test_S10_reverting_the_no_fill_row_is_caught():
    def broken_close(signal, perf, **kw):
        signal.live_status = lifecycle.WAITING_ENTRY
        return None
    assert broken_close(_sig(), _perf()) is None
    assert _close_without_fill()(
        _sig(lifecycle.WAITING_ENTRY), _perf(), outcome=SignalOutcome.EXPIRED,
        detail_label=L.EXPIRED_WITHOUT_ENTRY,
        resolution_source=L.RES_SRC_EXPIRY_NO_FILL,
        closed_at=T0, is_expired=True) is not None
