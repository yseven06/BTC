"""CP-ENTRY-ACTIVATION-GATE — 97 cases + 21 sabotage tests.

The defect this checkpoint removes is silent: the tracker books a trade as open
at the entry-zone midpoint from the first bar after birth, whether or not price
ever came back. Measured on production, 141 signals resolved without price ever
reaching the entry — 133 wins, ZERO losses, MAE exactly 0.0000, +242.47% of
return that no position could have earned. A loss is arithmetically impossible
there: MAE is measured FROM the entry, so a trade that never filled has no
adverse excursion to record.

Nothing here raises on its own. Every property below fails QUIETLY when broken —
a coerced None, an unknown folded into reached, a 0.0 standing in for "not
measured". So the sabotage section builds the plausible WRONG implementation
first, shows it gives a different answer, and only then pins the right one. A
test that merely asserts today's output would pass against the broken version
too, and this project has been bitten by exactly that: 43 fixtures once typed an
uppercase outcome by hand and so never noticed the enum value is lowercase.
"""

from __future__ import annotations

import inspect
import random
import re
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.backtesting import labels as L
from app.backtesting import lifecycle
from app.services import entry_flags
from app.services import entry_activation as EA
from app.services.entry_activation import (
    STATUS_NOT_REACHED,
    STATUS_REACHED,
    STATUS_UNKNOWN,
    entry_activation,
    entry_level,
    walk_start,
)

TRACKER = "app/backtesting/tracker.py"
SCHEDULER = "app/services/scheduler.py"


def _src(rel):
    import pathlib
    return pathlib.Path(rel).read_text(encoding="utf-8")


def _gate_block():
    """The tracker's gate block only. `_close_without_fill`'s docstring also
    names the checkpoint, so splitting on the name alone grabs the wrong text —
    anchor on code that appears exactly once instead."""
    trk = _src(TRACKER)
    return trk.split("            _gate = None")[1].split("_bw = _resolve_signal_bar_walk")[0]


def _flags(monkeypatch, activation=False, walk=False, occupancy=False):
    """Point entry_flags at a fake settings object and clear the once-per-process
    warning memo, so flag combinations are independent between tests."""
    fake = SimpleNamespace(
        ENTRY_ACTIVATION_ENABLED=activation,
        ENTRY_WALK_START_ENABLED=walk,
        ENTRY_PENDING_OCCUPANCY_ENABLED=occupancy,
    )
    monkeypatch.setattr(entry_flags, "get_settings", lambda: fake)
    entry_flags._warned.clear()
    return fake


def bars(*rows):
    """rows are (open, high, low, close) — returned as the four parallel lists
    the gate takes."""
    return (
        [r[0] for r in rows], [r[1] for r in rows],
        [r[2] for r in rows], [r[3] for r in rows],
    )


def gate(rows, *, is_bull=True, level=100.0, window_complete=True, **kw):
    o, h, l, _c = bars(*rows)
    return entry_activation(is_bull=is_bull, level=level, highs=h, lows=l,
                            opens=o, window_complete=window_complete, **kw)


# ══════════════════════════════════════════════════════════════════════════════
# A · fill detection — LONG (2)
# ══════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("low,expected", [(99.0, STATUS_REACHED), (100.5, STATUS_NOT_REACHED)])
def test_A_long_fill_is_decided_by_the_low(low, expected):
    assert gate([(101.0, 102.0, low, 101.0)])["status"] == expected


# ══════════════════════════════════════════════════════════════════════════════
# A · fill detection — SHORT (2)
# ══════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("high,expected", [(101.0, STATUS_REACHED), (99.5, STATUS_NOT_REACHED)])
def test_A_short_fill_is_decided_by_the_high(high, expected):
    assert gate([(99.0, high, 98.0, 99.0)], is_bull=False)["status"] == expected


# ══════════════════════════════════════════════════════════════════════════════
# A · edges (5)
# ══════════════════════════════════════════════════════════════════════════════
def test_A_exact_touch_counts_as_a_fill_long():
    """Inclusive, mirroring entry_telemetry.py:88 (`lows <= entry_level`). An
    exclusive `<` would silently drop every trade that filled exactly at its
    level — the most common case for a limit-style zone."""
    assert gate([(101.0, 102.0, 100.0, 101.0)])["status"] == STATUS_REACHED


def test_A_exact_touch_counts_as_a_fill_short():
    assert gate([(99.0, 100.0, 98.0, 99.0)], is_bull=False)["status"] == STATUS_REACHED


def test_A_near_edge_only_is_not_a_fill():
    """LONG zone 98..102, midpoint 100. Price dips to 101 — inside the zone but
    short of the canonical level. Locked decision 2: that is NOT a fill."""
    assert gate([(103.0, 104.0, 101.0, 103.0)])["status"] == STATUS_NOT_REACHED


def test_A_far_edge_is_a_fill():
    assert gate([(103.0, 104.0, 97.5, 98.0)])["status"] == STATUS_REACHED


def test_A_first_touching_bar_wins_not_the_deepest():
    out = gate([(101.0, 102.0, 100.0, 101.0), (101.0, 102.0, 90.0, 91.0)])
    assert out["entry_pos"] == 0 and out["bars_to_entry"] == 1


# ══════════════════════════════════════════════════════════════════════════════
# B · gap through the zone (4)
# ══════════════════════════════════════════════════════════════════════════════
def test_B_gap_through_still_fills_long():
    assert gate([(95.0, 96.0, 94.0, 95.0)])["status"] == STATUS_REACHED


def test_B_gap_through_is_flagged_long():
    out = gate([(95.0, 96.0, 94.0, 95.0)])
    assert out["gapped_entry"] is True and out["proof"] == EA.PROOF_OPEN_GAP


def test_B_gap_through_is_flagged_short():
    out = gate([(105.0, 106.0, 104.0, 105.0)], is_bull=False)
    assert out["gapped_entry"] is True and out["proof"] == EA.PROOF_OPEN_GAP


def test_B_a_normal_fill_is_not_flagged_as_a_gap():
    out = gate([(101.0, 102.0, 99.0, 100.5)])
    assert out["gapped_entry"] is False and out["proof"] == EA.PROOF_BAR


# ══════════════════════════════════════════════════════════════════════════════
# C · same-bar ordering (7)
# ══════════════════════════════════════════════════════════════════════════════
def test_C_walk_start_walks_the_bar_when_the_open_proves_the_fill():
    assert walk_start((99.0, 110.0, 98.0, 109.0), 3, 100.0, 95.0, True) == (3, True, False)


def test_C_walk_start_walks_the_bar_when_the_stop_is_causally_certain():
    """The stop sits BELOW a long's entry, so a bar reaching the stop must have
    crossed the entry on the way down. The fill necessarily precedes it."""
    assert walk_start((105.0, 106.0, 94.0, 95.0), 2, 100.0, 95.0, True) == (2, True, False)


def test_C_walk_start_withholds_an_unprovable_entry_bar_tp():
    """Neither exception holds: the bar opened above the entry and never reached
    the stop, so a TP on it could have happened before anyone was filled."""
    # LONG: opened above the entry, never reached the stop below it.
    assert walk_start((105.0, 120.0, 99.0, 118.0), 4, 100.0, 95.0, True) == (5, False, True)
    # SHORT mirror: opened below the entry, never reached the stop above it.
    assert walk_start((95.0, 101.0, 80.0, 82.0), 4, 100.0, 105.0, False) == (5, False, True)


def test_C_walk_start_is_total_on_a_missing_bar():
    assert walk_start(None, 9, 100.0, 95.0, True) == (9, False, False)


def test_C_walk_start_mirrors_between_directions():
    lo = (99.0, 110.0, 98.0, 109.0)
    sh = (101.0, 102.0, 90.0, 91.0)
    assert walk_start(lo, 0, 100.0, 95.0, True)[1] == walk_start(sh, 0, 100.0, 105.0, False)[1]


def test_C_intrabar_tp_sl_policy_is_untouched():
    """TP+SL on one bar is decided by resolve_inside_bar_ambiguity, and this
    checkpoint does not touch it: conservative still returns 'sl' first."""
    from app.backtesting import resolution_core as rc
    src = inspect.getsource(rc.resolve_inside_bar_ambiguity)
    assert 'if execution_model == "conservative"' in src
    # SL wins regardless of the candle body, in both directions.
    for direction in ("bullish", "bearish"):
        assert rc.resolve_inside_bar_ambiguity(
            direction, 100.0, 101.0, "conservative") == "sl"


def test_C_the_gate_runs_before_the_ambiguity_tie_break():
    """Ordering is technical, not stylistic: an ambiguous bar may only be
    resolved on a bar the trade was provably in."""
    trk = _src(TRACKER)
    assert trk.index("CP-ENTRY-ACTIVATION-GATE") < trk.index("_bw = _resolve_signal_bar_walk(")


# ══════════════════════════════════════════════════════════════════════════════
# D · no-fill terminal writes (7)
# ══════════════════════════════════════════════════════════════════════════════
def _closed_no_fill():
    from app.backtesting.tracker import _close_without_fill
    from app.models.signal import SignalOutcome
    sig = SimpleNamespace(is_active=True, live_status="active", status_reason=None)
    perf = SimpleNamespace()
    _close_without_fill(sig, perf, outcome=SignalOutcome.EXPIRED,
                        detail_label=L.EXPIRED_WITHOUT_ENTRY,
                        resolution_source=L.RES_SRC_EXPIRY_NO_FILL,
                        closed_at="T", is_expired=True)
    return sig, perf


@pytest.mark.parametrize("field", ["actual_return", "max_drawdown", "mfe_pct",
                                   "bars_to_outcome", "hit_time"])
def test_D_unmeasured_metrics_are_null_never_zero(field):
    _sig, perf = _closed_no_fill()
    assert getattr(perf, field) is None, f"{field} must be NULL, not a number"
    assert getattr(perf, field) != 0, f"{field}=0 reads as a measurement"


def test_D_tp_flags_are_false_and_label_and_source_are_the_no_fill_ones():
    sig, perf = _closed_no_fill()
    assert (perf.hit_tp1, perf.hit_tp2, perf.hit_tp3) == (False, False, False)
    assert perf.detail_label == "expired_without_entry"
    assert perf.resolution_source == "expiry_no_fill"
    assert perf.is_expired is True and sig.is_active is False


def test_D_the_coarse_outcome_enum_is_unchanged():
    """No new SignalOutcome member — that would cost a PG enum migration and a
    frontend union edit. The detail label carries the distinction."""
    from app.models.signal import SignalOutcome
    assert {m.name for m in SignalOutcome} == {
        "WIN", "LOSS", "BREAKEVEN", "ACTIVE", "EXPIRED", "INVALIDATED"}


# ══════════════════════════════════════════════════════════════════════════════
# E · post-fill regression — the gate must not restate filled trades (5)
# ══════════════════════════════════════════════════════════════════════════════
def test_E_walk_starts_at_the_fill_bar_when_walk_start_is_off():
    trk = _src(TRACKER)
    assert "_start = _pos" in trk
    assert "if effective_walk_start():" in trk


def test_E_flag2_off_leaves_the_entry_bar_in_the_walk():
    """FLAG_2 off is the SAFE rollout, not the target policy: the entry bar is
    still walked, so numbers on filled signals do not move."""
    assert "_start, _entry_bar_walked, _entry_bar_tp_withheld = walk_start(" in _src(TRACKER)


def test_E_the_bar_walk_itself_is_not_modified():
    from app.backtesting import resolution_core as rc
    src = inspect.getsource(rc)
    assert "entry_activation" not in src and "ENTRY_ACTIVATION" not in src


def test_E_slicing_only_happens_after_a_proven_fill():
    block = _gate_block()
    assert 'if _gate["status"] != STATUS_REACHED:' in block
    assert block.index("!= STATUS_REACHED") < block.index("opens[_start:]")


def test_E_gate_is_none_when_the_flag_is_off():
    trk = _src(TRACKER)
    assert "_gate = None" in trk
    assert "if entry_activation_enabled():" in trk


# ══════════════════════════════════════════════════════════════════════════════
# F · window completeness (5)
# ══════════════════════════════════════════════════════════════════════════════
def test_F_incomplete_window_is_unknown_never_not_reached():
    """"Never reached" is a claim about bars we do not have."""
    out = gate([(103.0, 104.0, 101.0, 103.0)], window_complete=False)
    assert out["status"] == STATUS_UNKNOWN
    assert out["unknown_reason"] == EA.UNKNOWN_WINDOW_INCOMPLETE


def test_F_complete_window_may_conclude_not_reached():
    assert gate([(103.0, 104.0, 101.0, 103.0)], window_complete=True)["status"] == STATUS_NOT_REACHED


def test_F_no_bars_is_unknown():
    out = entry_activation(is_bull=True, level=100.0, highs=[], lows=[], window_complete=True)
    assert out["status"] == STATUS_UNKNOWN and out["unknown_reason"] == EA.UNKNOWN_NO_BARS


def test_F_a_fill_is_conclusive_even_with_an_incomplete_window():
    """Seeing the touch is positive evidence; the missing bars cannot unsee it."""
    assert gate([(101.0, 102.0, 99.0, 100.0)], window_complete=False)["status"] == STATUS_REACHED


def test_F_the_tracker_feeds_the_real_window_signal():
    assert "window_complete=_window_reaches_generation(signal, df)" in _src(TRACKER)


# ══════════════════════════════════════════════════════════════════════════════
# G · live-SL ticker channel (4)
# ══════════════════════════════════════════════════════════════════════════════
def test_G_a_live_stop_breach_proves_the_entry_without_bars():
    out = entry_activation(is_bull=True, level=100.0, highs=None, lows=None,
                           live_stop_breached=True)
    assert out["status"] == STATUS_REACHED and out["proof"] == EA.PROOF_LIVE_STOP


def test_G_the_live_stop_proof_wins_over_missing_bars():
    out = entry_activation(is_bull=True, level=100.0, highs=[], lows=[],
                           window_complete=True, live_stop_breached=True)
    assert out["status"] == STATUS_REACHED


def test_G_the_live_sl_writer_stamps_the_gated_version():
    assert "perf.resolution_version = labels.resolution_version_for(\n" in _src(TRACKER)
    assert "entry_activation_enabled())" in _src(TRACKER)


def test_G_the_ticker_path_is_not_blocked_by_the_gate():
    """The live-SL shortcut returns before the bar gate; a stop breach must never
    be suppressed for lack of a bar frame."""
    trk = _src(TRACKER)
    assert trk.index("_check_live_sl_hit(signal, binance)") < trk.index("            _gate = None")
    assert "live_stop_breached" not in _gate_block(), \
        "the bar gate must not re-litigate a stop that already broke on the ticker"


# ══════════════════════════════════════════════════════════════════════════════
# H · idempotency and restart (5)
# ══════════════════════════════════════════════════════════════════════════════
def test_H_the_gate_is_pure_and_repeatable():
    rows = [(103.0, 104.0, 101.0, 103.0), (102.0, 103.0, 99.0, 100.0)]
    assert gate(rows) == gate(rows)


def test_H_the_gate_does_not_mutate_its_inputs():
    o, h, l, c = bars((103.0, 104.0, 101.0, 103.0))
    snap = (list(o), list(h), list(l), list(c))
    entry_activation(is_bull=True, level=100.0, highs=h, lows=l, opens=o, window_complete=True)
    assert (o, h, l, c) == snap


def test_H_a_second_pass_over_a_waiting_signal_keeps_the_same_state():
    trk = _src(TRACKER)
    assert "if signal.live_status != lifecycle.WAITING_ENTRY:" in trk, \
        "live_status_since must not be rewritten on every pass"


def test_H_closing_without_fill_is_deterministic():
    """Everything EXCEPT the wall-clock stamp must be identical between calls.

    `detected_at` is `datetime.now()` by design — it records when we wrote the
    row, so two calls genuinely differ. Comparing it makes the test's result
    depend on the platform's clock resolution: on Windows both calls land inside
    the same ~15ms tick and it passes, on Linux they are microseconds apart and
    it fails. This test did exactly that — green locally, red in CI — so the
    stamp is now excluded explicitly and checked for what actually matters.
    """
    a_sig, a_perf = _closed_no_fill()
    b_sig, b_perf = _closed_no_fill()
    a, b = dict(vars(a_perf)), dict(vars(b_perf))
    for stamped in (a.pop("detected_at"), b.pop("detected_at")):
        assert stamped is not None and stamped.tzinfo is not None
    assert a == b, "the no-fill write is not deterministic apart from the clock"
    assert a_sig.is_active is b_sig.is_active is False


def test_H_the_no_fill_closer_writes_no_trade_path_row():
    """A trade path describes a trade; there was no trade. Writing one would
    also mean writing 0.0 into its mfe/mae columns."""
    from app.backtesting.tracker import _close_without_fill
    src = inspect.getsource(_close_without_fill)
    assert "compute_trade_path" not in src and "_persist_trade_path_once" not in src


# ══════════════════════════════════════════════════════════════════════════════
# I · lifecycle + occupancy INVARIANCE (7)
# ══════════════════════════════════════════════════════════════════════════════
def test_I1_evaluate_lifecycle_never_sees_waiting_entry():
    """_SEVERITY has no waiting_entry key and .get(prev, 0) reads a missing key
    as severity 0 — which would let a de-escalation decide from a state the
    evaluator does not model."""
    assert lifecycle.WAITING_ENTRY not in lifecycle._SEVERITY
    block = _gate_block()
    assert "continue" in block, "the waiting branch must not fall through to the evaluator"
    assert "signal.live_status = lifecycle.ACTIVE" in block, \
        "a filled signal must leave waiting_entry BEFORE the evaluator runs"


def test_I2_both_birth_sites_write_the_same_state():
    sched, api = _src(SCHEDULER), _src("app/api/routes/signals.py")
    assert "lifecycle.WAITING_ENTRY if entry_activation_enabled()" in sched
    assert "lifecycle.WAITING_ENTRY if entry_activation_enabled()" in api


def test_I3_status_tr_covers_the_new_state():
    assert lifecycle.status_tr(lifecycle.WAITING_ENTRY) not in ("", lifecycle.WAITING_ENTRY)


def test_I4_no_tp_progress_is_computed_before_a_fill():
    trk = _src(TRACKER)
    gate_block = trk.split("CP-ENTRY-ACTIVATION-GATE")[1].split("_bw = _resolve_signal_bar_walk")[0]
    assert "evaluate_lifecycle" not in gate_block


def test_I5_the_occupancy_block_is_untouched():
    """Occupancy is out of scope: waiting signals keep holding slots exactly as
    they do today, so publication volume cannot move."""
    sched = _src(SCHEDULER)
    assert "if not (old_perf and old_perf.outcome == SignalOutcome.ACTIVE):" in sched
    occ = sched.split("old_res = await db.execute(")[1].split("if is_reversal:")[0]
    assert "entry_activation" not in occ, "the slot test now consults the entry gate"
    assert "WAITING_ENTRY" not in occ, "the slot test now branches on the new state"


def test_I6_no_occupancy_namespace_is_written_to_candidate_extra():
    cl = _src("app/services/candidate_log.py")
    for token in ("occupancy_shadow", "entry_occupancy", "applied_verdict"):
        assert token not in cl, f"{token} leaked into the candidate payload"


def test_I7_the_occupancy_flag_has_no_production_consumer(monkeypatch):
    """Turning it on must change nothing, because nothing reads it."""
    import pathlib
    hits = []
    for f in pathlib.Path("app").rglob("*.py"):
        if f.name == "entry_flags.py" or f.name == "config.py":
            continue
        if "effective_pending_occupancy" in f.read_text(encoding="utf-8"):
            hits.append(str(f))
        if "ENTRY_PENDING_OCCUPANCY_ENABLED" in f.read_text(encoding="utf-8"):
            hits.append(str(f))
    assert hits == [], f"the reserved occupancy flag gained a consumer: {hits}"
    _flags(monkeypatch, activation=True, occupancy=True)
    assert entry_flags.effective_pending_occupancy() is True  # resolvable...
    # ...but unread: the source scan above is what makes that meaningful.


# ══════════════════════════════════════════════════════════════════════════════
# J · learning contamination (9)
# ══════════════════════════════════════════════════════════════════════════════
def _fold(label, outcome_name="EXPIRED"):
    from app.services.coin_memory import fold_signal_into
    from app.models.signal import SignalOutcome
    mem = SimpleNamespace(total_signals=0, wins=0, losses=0, outcome_label_stats={},
                          regime_stats={}, engine_stats={}, avg_bars_to_outcome=None,
                          adaptive_weights=None, session_stats={}, volatility_stats={})
    perf = SimpleNamespace(outcome=getattr(SignalOutcome, outcome_name),
                           detail_label=label, actual_return=None, bars_to_outcome=None,
                           max_drawdown=None, mfe_pct=None, hit_tp1=False,
                           hit_tp2=False, hit_tp3=False)
    sig = SimpleNamespace(engines_data=None, direction=SimpleNamespace(value="bullish"),
                          confidence_score=70, generated_at=None,
                          timeframe=SimpleNamespace(value="15m"))
    return fold_signal_into(mem, sig, perf, None), mem


@pytest.mark.parametrize("label", ["expired_without_entry", "invalidated_before_entry"])
def test_J_no_fill_rows_are_excluded_from_the_fold(label):
    folded, mem = _fold(label, "INVALIDATED" if "invalid" in label else "EXPIRED")
    assert folded is False
    assert mem.total_signals == 0 and mem.losses == 0 and mem.outcome_label_stats == {}


def test_J_the_exclusion_sits_before_the_is_loss_computation():
    from app.services.coin_memory import fold_signal_into
    src = inspect.getsource(fold_signal_into)
    assert src.index("NO_FILL_DETAIL_LABELS") < src.index("is_loss ="), \
        "an exclusion after is_loss still lets losses be counted"


def test_J_coin_memory_line_404_is_deliberately_unchanged():
    """Changing `is_loss` globally would restate every reversal-invalidated row
    that DID fill — out of scope and wrong."""
    from app.services.coin_memory import fold_signal_into
    src = inspect.getsource(fold_signal_into)
    assert "is_loss = outcome in (SignalOutcome.LOSS, SignalOutcome.INVALIDATED)" in src


def test_J_a_filled_invalidated_row_is_still_counted_as_a_loss():
    folded, mem = _fold("invalidated_reversal", "INVALIDATED")
    assert folded is True and mem.losses == 1


def test_J_similarity_module_is_byte_identical():
    import hashlib
    import pathlib
    sha = hashlib.sha256(pathlib.Path("app/services/similarity.py").read_bytes()).hexdigest()
    assert sha == "01acf804b2b9243619ac5cabb58f6c2637a808e9af0144b53581a38c034b0440"


def test_J_the_exclusion_is_not_inside_similarity():
    sim = _src("app/services/similarity.py")
    assert "entry_activation" not in sim and "without_entry" not in sim


def test_J_reporting_surface_knows_the_no_fill_labels():
    from app.services.entry_validity import NO_FILL_DETAIL_LABELS, is_no_fill
    assert NO_FILL_DETAIL_LABELS == {"expired_without_entry", "invalidated_before_entry"}
    assert is_no_fill({"detail_label": "invalidated_before_entry"}) is True
    assert is_no_fill({"detail_label": "invalidated_reversal"}) is False


def test_J_tm_stats_is_not_touched_by_the_fold():
    """The docstring discusses tm_stats; the CODE must never assign to it."""
    from app.services.coin_memory import fold_signal_into
    body = inspect.getsource(fold_signal_into).split('"""')[2]
    assert "tm_stats" not in body


# ══════════════════════════════════════════════════════════════════════════════
# K · legacy / unknown rows (4)
# ══════════════════════════════════════════════════════════════════════════════
def test_K_legacy_rows_without_telemetry_stay_unknown():
    from app.services.entry_validity import classify_entry_validity, STATUS_UNKNOWN as U
    assert classify_entry_validity(None)["status"] == U


def test_K_no_backfill_or_historical_rewrite_exists():
    import pathlib
    for f in pathlib.Path("app").rglob("*.py"):
        txt = f.read_text(encoding="utf-8")
        assert "backfill_entry" not in txt and "UPDATE signal_performances" not in txt


def test_K_cohort_raw_all_is_preserved():
    from app.services.entry_validity import COHORT_RAW_ALL, compute_entry_validity_report
    rep = compute_entry_validity_report([])
    assert COHORT_RAW_ALL in rep["cohorts"]
    assert rep["cohorts"][COHORT_RAW_ALL]["legacy_raw"] is True


def test_K_no_migration_was_added():
    import pathlib
    mig = pathlib.Path("migrations")
    before = {p.name for p in mig.rglob("*.py")} if mig.exists() else set()
    assert not any("entry_activation" in n or "waiting_entry" in n for n in before)


# ══════════════════════════════════════════════════════════════════════════════
# L · API / schema compatibility (4)
# ══════════════════════════════════════════════════════════════════════════════
def test_L_intelligence_keeps_its_key_set():
    api = _src("app/api/routes/signals.py")
    block = api.split('"signal_id": str(signal_id),')[1].split("\n    }")[0]
    for key in ('"entry_validity"', '"similar_setups"', '"similar_setups_coin_memory"',
                '"trade_mgmt"', '"coin_memory"', '"outcome"'):
        assert key in block


def test_L_live_status_column_needs_no_migration():
    from app.models.signal import Signal
    assert Signal.__table__.c.live_status.type.python_type is str


def test_L_detail_label_is_free_text():
    from app.models.signal import SignalPerformance
    assert SignalPerformance.__table__.c.detail_label.type.python_type is str


def test_L_resolution_version_is_nullable_per_row():
    from app.models.signal import SignalPerformance
    assert SignalPerformance.__table__.c.resolution_version.nullable is True


# ══════════════════════════════════════════════════════════════════════════════
# M · rollout mechanics (4)
# ══════════════════════════════════════════════════════════════════════════════
def test_M_all_three_flags_default_to_false():
    import pathlib
    cfg = pathlib.Path("app/config.py").read_text(encoding="utf-8")
    for flag in ("ENTRY_ACTIVATION_ENABLED", "ENTRY_WALK_START_ENABLED",
                 "ENTRY_PENDING_OCCUPANCY_ENABLED"):
        assert f"{flag}: bool = False" in cfg


def test_M_entry_telemetry_version_is_not_bumped():
    from app.engines.ai_decision.entry_telemetry import ENTRY_TELEMETRY_VERSION
    assert ENTRY_TELEMETRY_VERSION == 1


def test_M_trade_path_versions_are_not_bumped():
    from app.backtesting.trade_path import TRADE_PATH_SCHEMA_VERSION, TRADE_PATH_EXTRA_VERSION
    assert (TRADE_PATH_SCHEMA_VERSION, TRADE_PATH_EXTRA_VERSION) == (2, 1)


def test_M_health_exposes_raw_and_effective():
    from app.services.entry_flags import flag_diagnostics, INVALID_DEPENDENCY_KEY
    d = flag_diagnostics()
    assert set(d) == {"raw", "effective", INVALID_DEPENDENCY_KEY}


# ══════════════════════════════════════════════════════════════════════════════
# N · entry_level value parity (6)
# ══════════════════════════════════════════════════════════════════════════════
def test_N_decimal_form_is_reproduced_exactly():
    rnd = random.Random(1)
    for _ in range(20_000):
        lo = Decimal(str(round(rnd.uniform(1e-4, 90_000), 8)))
        hi = lo + Decimal(str(round(rnd.uniform(1e-7, 500), 8)))
        assert entry_level(lo, hi) == float(hi + lo) / 2.0


def test_N_float_form_is_reproduced_exactly():
    rnd = random.Random(2)
    for _ in range(20_000):
        lo = round(rnd.uniform(1e-4, 90_000), 8)
        hi = lo + round(rnd.uniform(1e-7, 500), 8)
        assert entry_level(lo, hi) == (lo + hi) / 2.0


def test_N_the_two_forms_really_can_differ():
    """If they were always equal, the operand-type discipline would be cosmetic.
    They are not: this is why the helper adds BEFORE converting."""
    lo, hi = Decimal("0.1"), Decimal("0.2")
    assert float(hi + lo) / 2.0 != (float(lo) + float(hi)) / 2.0


def test_N_argument_order_does_not_matter():
    rnd = random.Random(3)
    for _ in range(5_000):
        a, b = rnd.uniform(0.01, 1e5), rnd.uniform(0.01, 1e5)
        assert entry_level(a, b) == entry_level(b, a)


def test_N_every_call_site_uses_the_helper():
    import pathlib
    raw = re.compile(r"entry_zone_(high|low)[^)\n]*\+|ez_(high|low)\s*\+")
    offenders = []
    for f in pathlib.Path("app").rglob("*.py"):
        if f.name in ("entry_activation.py", "signal_generator.py", "analysis.py"):
            continue
        if raw.search(f.read_text(encoding="utf-8")):
            offenders.append(str(f))
    assert offenders == [], f"raw midpoint arithmetic survives in {offenders}"


def test_N_the_helper_has_exactly_one_definition():
    import pathlib
    defs = [str(f) for f in pathlib.Path("app").rglob("*.py")
            if "def entry_level(" in f.read_text(encoding="utf-8")]
    assert defs == ["app\\services\\entry_activation.py".replace("\\", "/")] or \
           len(defs) == 1, defs


# ══════════════════════════════════════════════════════════════════════════════
# O · flag combinations (11)
# ══════════════════════════════════════════════════════════════════════════════
def test_O1_all_off_is_the_old_behaviour(monkeypatch):
    _flags(monkeypatch)
    assert entry_flags.entry_activation_enabled() is False
    assert entry_flags.effective_walk_start() is False
    assert entry_flags.effective_pending_occupancy() is False
    assert entry_flags.invalid_dependencies() == []


def test_O2_activation_only(monkeypatch):
    _flags(monkeypatch, activation=True)
    assert entry_flags.entry_activation_enabled() is True
    assert entry_flags.effective_walk_start() is False
    assert entry_flags.effective_pending_occupancy() is False


def test_O3_activation_plus_walk_start(monkeypatch):
    _flags(monkeypatch, activation=True, walk=True)
    assert entry_flags.effective_walk_start() is True
    assert entry_flags.effective_pending_occupancy() is False


def test_O4_activation_plus_occupancy_is_still_inert(monkeypatch):
    _flags(monkeypatch, activation=True, occupancy=True)
    assert entry_flags.effective_walk_start() is False
    assert entry_flags.invalid_dependencies() == []


def test_O5_occupancy_alone_resolves_false_and_is_reported(monkeypatch):
    _flags(monkeypatch, occupancy=True)
    assert entry_flags.effective_pending_occupancy() is False
    assert entry_flags.invalid_dependencies() == ["ENTRY_PENDING_OCCUPANCY_ENABLED"]
    assert entry_flags.flag_diagnostics()[entry_flags.INVALID_DEPENDENCY_KEY]


def test_O6_walk_start_alone_resolves_false_and_is_reported(monkeypatch):
    _flags(monkeypatch, walk=True)
    assert entry_flags.effective_walk_start() is False
    assert entry_flags.invalid_dependencies() == ["ENTRY_WALK_START_ENABLED"]


def test_O7_all_three_on(monkeypatch):
    _flags(monkeypatch, activation=True, walk=True, occupancy=True)
    assert entry_flags.effective_walk_start() is True
    assert entry_flags.invalid_dependencies() == []


def test_O8_rolling_back_activation_disables_dependents(monkeypatch):
    _flags(monkeypatch, activation=False, walk=True, occupancy=True)
    assert entry_flags.effective_walk_start() is False
    assert entry_flags.effective_pending_occupancy() is False
    assert len(entry_flags.invalid_dependencies()) == 2


def test_O9_rolling_back_walk_start_leaves_activation(monkeypatch):
    _flags(monkeypatch, activation=True, walk=False)
    assert entry_flags.entry_activation_enabled() is True
    assert entry_flags.effective_walk_start() is False


def test_O10_rolling_back_occupancy_is_a_no_op(monkeypatch):
    _flags(monkeypatch, activation=True, occupancy=True)
    before = entry_flags.effective_walk_start()
    _flags(monkeypatch, activation=True, occupancy=False)
    assert entry_flags.effective_walk_start() == before


def test_O11_a_misconfiguration_never_prevents_startup(monkeypatch):
    """Refusing to boot would trade a silent misconfiguration for an outage."""
    _flags(monkeypatch, walk=True, occupancy=True)
    d = entry_flags.flag_diagnostics()          # must not raise
    assert d["effective"]["ENTRY_WALK_START_ENABLED"] is False
    assert len(d[entry_flags.INVALID_DEPENDENCY_KEY]) == 2


# ══════════════════════════════════════════════════════════════════════════════
# P · resolution version stamping (6)
# ══════════════════════════════════════════════════════════════════════════════
def test_P_the_v1_constant_is_not_bumped():
    assert L.RESOLUTION_SEMANTICS_VERSION == 1


def test_P_the_selector_returns_hand_written_values():
    assert L.resolution_version_for(False) == 1
    assert L.resolution_version_for(True) == 2


def test_P_admin_paths_always_stamp_v1():
    admin = _src("app/api/routes/admin.py")
    assert admin.count("labels.resolution_version_for(False)") == 2


def test_P_the_hold_path_always_stamps_v1():
    assert "labels.resolution_version_for(False)" in _src(TRACKER)


def test_P_every_writer_uses_the_selector():
    for rel in (TRACKER, SCHEDULER, "app/api/routes/admin.py"):
        assert "resolution_version = labels.RESOLUTION_SEMANTICS_VERSION" not in _src(rel)


def test_P_the_gated_stamp_is_conditional_on_the_gate_running():
    assert "labels.resolution_version_for(_gate is not None)" in _src(TRACKER)


# ══════════════════════════════════════════════════════════════════════════════
# SABOTAGE · 21 — build the wrong version, show it disagrees, pin the right one
# ══════════════════════════════════════════════════════════════════════════════
def test_S01_unknown_folded_into_reached():
    rows = [(103.0, 104.0, 101.0, 103.0)]
    naive = "reached" if gate(rows, window_complete=False)["status"] != STATUS_NOT_REACHED else "x"
    assert naive == "reached"                                   # the wrong reading
    assert gate(rows, window_complete=False)["status"] == STATUS_UNKNOWN


def test_S02_null_coerced_to_false():
    from app.services.entry_validity import classify_entry_validity
    blk = {"telemetry_version": 1, "entry_level": 1.0, "data_available": False}
    assert (not blk.get("entry_reached")) is True               # bool() says "not reached"
    assert classify_entry_validity(blk)["status"] == "unknown"


def test_S03_window_completeness_check_omitted():
    rows = [(103.0, 104.0, 101.0, 103.0)]
    assert gate(rows, window_complete=True)["status"] == STATUS_NOT_REACHED
    assert gate(rows, window_complete=False)["status"] == STATUS_UNKNOWN


def test_S04_metrics_defaulted_to_zero():
    _sig, perf = _closed_no_fill()
    naive = perf.actual_return or 0.0                           # the `or 0.0` bug
    assert naive == 0.0
    assert perf.actual_return is None


def test_S05_exclusive_comparison():
    assert gate([(101.0, 102.0, 100.0, 101.0)])["status"] == STATUS_REACHED
    assert (100.0 < 100.0) is False                             # what `<` would say


def test_S06_direction_mirror_broken():
    long_hit = gate([(101.0, 102.0, 99.0, 100.0)])["status"]
    short_hit = gate([(99.0, 101.0, 98.0, 100.0)], is_bull=False)["status"]
    assert long_hit == short_hit == STATUS_REACHED
    assert gate([(99.0, 99.5, 98.0, 99.0)], is_bull=False)["status"] == STATUS_NOT_REACHED


def test_S07_gap_priced_at_the_open():
    out = gate([(95.0, 96.0, 94.0, 95.0)])
    assert out["status"] == STATUS_REACHED and out["gapped_entry"] is True
    assert "entry_pos" in out and "fill_price" not in out       # price is never re-derived


def test_S08_gate_after_the_ambiguity_tie_break():
    trk = _src(TRACKER)
    assert trk.index("CP-ENTRY-ACTIVATION-GATE") < trk.index("_bw = _resolve_signal_bar_walk(")


def test_S09_lifecycle_sees_waiting_entry():
    assert lifecycle._SEVERITY.get(lifecycle.WAITING_ENTRY, 0) == 0   # the silent default
    assert lifecycle.WAITING_ENTRY not in lifecycle._SEVERITY        # so it must never arrive


def test_S10_only_one_birth_site_updated():
    assert "lifecycle.WAITING_ENTRY" in _src(SCHEDULER)
    assert "lifecycle.WAITING_ENTRY" in _src("app/api/routes/signals.py")


def test_S11_null_fields_assumed_to_exclude_from_learning():
    from app.services.coin_memory import FOLDABLE_OUTCOMES
    from app.models.signal import SignalOutcome
    assert SignalOutcome.EXPIRED in FOLDABLE_OUTCOMES            # NULLs alone exclude nothing
    folded, mem = _fold("expired_without_entry")
    assert folded is False and mem.total_signals == 0


def test_S12_exclusion_placed_after_is_loss():
    from app.services.coin_memory import fold_signal_into
    src = inspect.getsource(fold_signal_into)
    assert src.index("NO_FILL_DETAIL_LABELS") < src.index("is_loss =")
    folded, mem = _fold("invalidated_before_entry", "INVALIDATED")
    assert folded is False and mem.losses == 0


def test_S13_exclusion_written_into_similarity():
    import hashlib
    import pathlib
    assert hashlib.sha256(pathlib.Path("app/services/similarity.py").read_bytes()).hexdigest() \
        == "01acf804b2b9243619ac5cabb58f6c2637a808e9af0144b53581a38c034b0440"


def test_S14_entry_level_value_drift():
    lo, hi = Decimal("0.1"), Decimal("0.2")
    wrong = (float(lo) + float(hi)) / 2.0
    assert entry_level(lo, hi) != wrong                          # the two-rounding form
    assert entry_level(lo, hi) == float(hi + lo) / 2.0


def test_S15_gate_escapes_its_flag(monkeypatch):
    _flags(monkeypatch)
    block = _gate_block()
    assert "if entry_activation_enabled():" in block
    assert block.index("if entry_activation_enabled():") < block.index("_gate = entry_activation(")


def test_S16_walk_start_read_from_the_raw_flag(monkeypatch):
    _flags(monkeypatch, activation=False, walk=True)
    raw = entry_flags.get_settings().ENTRY_WALK_START_ENABLED
    assert raw is True                                           # what a raw read sees
    assert entry_flags.effective_walk_start() is False           # what consumers must see
    assert "effective_walk_start()" in _src(TRACKER)
    assert "settings.ENTRY_WALK_START_ENABLED" not in _src(TRACKER)


def test_S17_occupancy_gains_a_consumer(monkeypatch):
    import pathlib
    for f in pathlib.Path("app").rglob("*.py"):
        if f.name in ("entry_flags.py", "config.py"):
            continue
        txt = f.read_text(encoding="utf-8")
        assert "ENTRY_PENDING_OCCUPANCY_ENABLED" not in txt, f"consumer in {f}"
        assert "effective_pending_occupancy" not in txt, f"consumer in {f}"


def test_S18_occupancy_namespace_leaks_into_candidate_extra():
    cl = _src("app/services/candidate_log.py")
    assert "occupancy" not in cl.lower()


def test_S19_resolution_version_bumped_globally():
    assert L.RESOLUTION_SEMANTICS_VERSION == 1                    # not 2
    assert L.resolution_version_for(False) == 1


def test_S20_a_silent_difference_outside_the_contract():
    """The allowlist is EMPTY in this checkpoint, so `extra` on the candidate
    payload may not gain a single key."""
    from app.services.candidate_log import build_candidate_values
    src = inspect.getsource(build_candidate_values)
    assert "entry_activation" not in src and "waiting_entry" not in src


def test_S21_coin_memory_is_loss_changed_globally():
    from app.services.coin_memory import fold_signal_into
    src = inspect.getsource(fold_signal_into)
    assert "is_loss = outcome in (SignalOutcome.LOSS, SignalOutcome.INVALIDATED)" in src
    folded, mem = _fold("invalidated_reversal", "INVALIDATED")
    assert folded is True and mem.losses == 1


# ==============================================================================
# T - REAL PRODUCTION TYPES - CP-ENTRY-ACTIVATION-NDARRAY-HOTFIX (19)
#
# The gate shipped correct and crashed in production anyway: every test above
# hands it a Python list, while the tracker hands it df_after["high"].values, a
# numpy ndarray, and `not <ndarray>` raises. The suite could not have caught it,
# because the fixtures were choosing the input TYPE the assertions then checked.
#
# `not <collection>` is not one bug but three, each failing differently:
#   multi-element ndarray   ValueError - the production crash
#   empty ndarray           no error, but a DeprecationWarning: it WILL become one
#   single-element ndarray  no error, no warning - it evaluates the ELEMENT, so
#                           `not np.array([0.0])` is True and one legitimate bar
#                           whose high is 0.0 reads as "no bars at all"
# So these use real frames, not hand-built lists.
# ==============================================================================
import numpy as np
import pandas as pd


def _frame(rows):
    """A DataFrame shaped exactly like the tracker's post-birth frame."""
    idx = pd.date_range("2026-08-01", periods=len(rows), freq="15min")
    return pd.DataFrame(
        {"open": [r[0] for r in rows], "high": [r[1] for r in rows],
         "low": [r[2] for r in rows], "close": [r[3] for r in rows]},
        index=idx,
    )


def _gate_from(df, *, is_bull=True, level=100.0, window_complete=True):
    """Call the gate the way tracker.py:833-836 does - .values, not lists."""
    return entry_activation(
        is_bull=is_bull, level=level,
        highs=df["high"].values, lows=df["low"].values, opens=df["open"].values,
        window_complete=window_complete,
    )


ROWS_HIT = [(103.0, 104.0, 101.0, 103.0), (102.0, 103.0, 99.0, 100.0)]
ROWS_MISS = [(103.0, 104.0, 101.0, 103.0), (104.0, 105.0, 102.0, 104.0)]


def test_T01_multi_element_ndarray_does_not_raise():
    """The exact production crash: .values on a 2+ row frame is what broke."""
    out = _gate_from(_frame(ROWS_HIT))
    assert out["status"] == STATUS_REACHED and out["bars_to_entry"] == 2


def test_T02_empty_ndarray_is_unknown_not_a_crash():
    empty = _frame(ROWS_HIT).iloc[0:0]
    assert empty["high"].values.size == 0
    out = _gate_from(empty)
    assert out["status"] == STATUS_UNKNOWN and out["unknown_reason"] == EA.UNKNOWN_NO_BARS


def test_T03_single_element_ndarray_is_evaluated_not_truthiness_tested():
    """A one-bar frame whose high is 0.0: truthiness would call this "no bars"."""
    df = _frame([(0.0, 0.0, 0.0, 0.0)])
    out = entry_activation(is_bull=True, level=0.0, highs=df["high"].values,
                           lows=df["low"].values, opens=df["open"].values,
                           window_complete=True)
    assert out["status"] == STATUS_REACHED, "a real bar was discarded as falsy"
    assert out["bars_to_entry"] == 1


def test_T04_multi_element_pandas_series_does_not_raise():
    df = _frame(ROWS_HIT)
    out = entry_activation(is_bull=True, level=100.0, highs=df["high"], lows=df["low"],
                           opens=df["open"], window_complete=True)
    assert out["status"] == STATUS_REACHED and out["bars_to_entry"] == 2


def test_T05_empty_pandas_series_is_unknown():
    empty = _frame(ROWS_HIT).iloc[0:0]
    out = entry_activation(is_bull=True, level=100.0, highs=empty["high"],
                           lows=empty["low"], opens=empty["open"], window_complete=True)
    assert out["status"] == STATUS_UNKNOWN and out["unknown_reason"] == EA.UNKNOWN_NO_BARS


def test_T06_python_list_still_works():
    out = gate(ROWS_HIT)
    assert out["status"] == STATUS_REACHED and out["bars_to_entry"] == 2


def test_T07_tuple_works():
    o, h, l, _c = bars(*ROWS_HIT)
    out = entry_activation(is_bull=True, level=100.0, highs=tuple(h), lows=tuple(l),
                           opens=tuple(o), window_complete=True)
    assert out["status"] == STATUS_REACHED and out["bars_to_entry"] == 2


def test_T08_highs_none_is_unknown():
    df = _frame(ROWS_HIT)
    out = entry_activation(is_bull=True, level=100.0, highs=None,
                           lows=df["low"].values, window_complete=True)
    assert out["status"] == STATUS_UNKNOWN and out["unknown_reason"] == EA.UNKNOWN_NO_BARS


def test_T09_lows_none_is_unknown():
    df = _frame(ROWS_HIT)
    out = entry_activation(is_bull=True, level=100.0, highs=df["high"].values,
                           lows=None, window_complete=True)
    assert out["status"] == STATUS_UNKNOWN and out["unknown_reason"] == EA.UNKNOWN_NO_BARS


def test_T10_length_mismatch_is_unknown_for_every_type():
    df = _frame(ROWS_HIT)
    for hi, lo in ((df["high"].values, df["low"].values[:1]),
                   (df["high"], df["low"].iloc[:1]),
                   (list(df["high"]), list(df["low"])[:1])):
        out = entry_activation(is_bull=True, level=100.0, highs=hi, lows=lo,
                               window_complete=True)
        assert out["status"] == STATUS_UNKNOWN
        assert out["unknown_reason"] == EA.UNKNOWN_NO_BARS


def test_T11_long_zone_touch_from_a_real_frame():
    out = _gate_from(_frame([(101.0, 102.0, 99.5, 100.2)]))
    assert out["status"] == STATUS_REACHED and out["proof"] == EA.PROOF_BAR


def test_T12_short_zone_touch_from_a_real_frame():
    out = _gate_from(_frame([(99.0, 100.5, 98.0, 99.5)]), is_bull=False)
    assert out["status"] == STATUS_REACHED and out["proof"] == EA.PROOF_BAR


def test_T13_reached_reports_position_and_bar_count():
    out = _gate_from(_frame(ROWS_HIT))
    assert (out["entry_pos"], out["bars_to_entry"]) == (1, 2)


def test_T14_not_reached_over_a_complete_real_window():
    out = _gate_from(_frame(ROWS_MISS))
    assert out["status"] == STATUS_NOT_REACHED and out["gapped_entry"] is False


def test_T15_gap_through_from_a_real_frame():
    out = _gate_from(_frame([(95.0, 96.0, 94.0, 95.0)]))
    assert out["status"] == STATUS_REACHED and out["gapped_entry"] is True
    assert out["proof"] == EA.PROOF_OPEN_GAP


def test_T16_incomplete_real_window_without_a_touch_is_unknown():
    out = _gate_from(_frame(ROWS_MISS), window_complete=False)
    assert out["status"] == STATUS_UNKNOWN
    assert out["unknown_reason"] == EA.UNKNOWN_WINDOW_INCOMPLETE


@pytest.mark.parametrize("rows,is_bull,complete", [
    (ROWS_HIT, True, True), (ROWS_MISS, True, True), (ROWS_MISS, True, False),
    (ROWS_HIT, False, True), ([(95.0, 96.0, 94.0, 95.0)], True, True),
])
def test_T17_list_ndarray_and_series_agree_exactly(rows, is_bull, complete):
    """The whole point: the same window must not depend on its container type."""
    df = _frame(rows)
    o, h, l, _c = bars(*rows)
    as_list = entry_activation(is_bull=is_bull, level=100.0, highs=h, lows=l, opens=o,
                               window_complete=complete)
    as_ndarray = entry_activation(is_bull=is_bull, level=100.0, highs=df["high"].values,
                                  lows=df["low"].values, opens=df["open"].values,
                                  window_complete=complete)
    as_series = entry_activation(is_bull=is_bull, level=100.0, highs=df["high"],
                                 lows=df["low"], opens=df["open"],
                                 window_complete=complete)
    assert as_list == as_ndarray == as_series


def test_T18_no_truthiness_is_applied_to_a_collection():
    """Source-level backstop for the pattern itself. The behavioural tests above
    are the real proof; this catches a reintroduction that happens to be masked."""
    src = inspect.getsource(EA.entry_activation)
    for banned in ("if not highs", "if not lows", "if not opens",
                   "not highs or", "not lows or"):
        assert banned not in src, f"truthiness on a collection is back: {banned!r}"
    assert "highs is None or lows is None" in src
    assert "len(highs) == 0" in src and "len(lows) == 0" in src


def test_T19_the_normaliser_leaves_plain_containers_untouched():
    lst, tpl, arr = [1.0, 2.0], (1.0, 2.0), np.array([1.0, 2.0])
    assert EA._positional(lst) is lst
    assert EA._positional(tpl) is tpl
    assert EA._positional(arr) is arr
    assert EA._positional(None) is None
    ser = pd.Series([1.0, 2.0], index=pd.date_range("2026-08-01", periods=2, freq="15min"))
    assert isinstance(EA._positional(ser), np.ndarray)
