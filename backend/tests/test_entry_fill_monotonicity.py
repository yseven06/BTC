"""CP-ENTRY-FILL-MONOTONICITY — a proven fill may never be un-proven.

Measured in production, ENTRY_ACTIVATION_ENABLED on:

    16:42:02  BNBUSDT H1  waiting_entry -> active
    16:44:02  BNBUSDT H1  active -> waiting_entry
    17:02:03  BNBUSDT H1  waiting_entry -> active

Three verdicts, one trade. The mechanism is sharper than "the candle closed":
that H1 candle closes at 17:00, sixteen minutes AFTER the reversal.

    `_post_signal_bars` filters the frame with a strict `index > generated_at`
    (tracker.py:345), so a signal born at 16:01:20 can never see its own 16:00
    candle with real high/low. While that candle is alive the frame holds ONE
    row — the compensating bar whose high and low are collapsed to the live
    close (tracker.py:370-373, a deliberate locked rule: OHLCV carries no
    intra-candle ordering, so a wick cannot be attributed to after the signal).

So during the birth candle the gate's whole evidence is a single instantaneous
price sample, `entry_activation` is pure and memoryless, and its verdict is
persisted nowhere — the answer is re-derived from scratch every pass and tracks
price up and down.

Each PROMOTION was right: price really was at the entry. The DEMOTION was the
error. And it is not cosmetic — a filled signal superseded while wearing the
wrong state is written off as `invalidated_before_entry` with NULL P&L: a trade
that happened, recorded as one that never opened.

The tests below pin the property (monotone in ONE direction only), not today's
output, and the sabotage section rebuilds the memoryless behaviour first to show
each test can actually see it.
"""

from __future__ import annotations

import inspect
import pathlib
from uuid import uuid4

import pytest

from app.services.entry_activation import (
    STATUS_NOT_REACHED,
    STATUS_REACHED,
    STATUS_UNKNOWN,
    apply_monotonic_latch,
    entry_activation,
)

TRACKER = "app/backtesting/tracker.py"


def _src(rel: str) -> str:
    return pathlib.Path(rel).read_text(encoding="utf-8")


def _impl():
    from app.backtesting.tracker import _track_and_resolve_active_signals_impl
    return inspect.getsource(_track_and_resolve_active_signals_impl)


def gate(status, **kw):
    base = {"status": status, "entry_pos": None, "unknown_reason": None}
    base.update(kw)
    return base


# ───────────────────────── A. the latch itself ───────────────────────────────

def test_A1_proven_not_reached_becomes_reached():
    out = apply_monotonic_latch(gate(STATUS_NOT_REACHED), already_proven=True)
    assert out["status"] == STATUS_REACHED


def test_A2_proven_unknown_becomes_reached():
    # An incomplete window is missing evidence, not counter-evidence.
    out = apply_monotonic_latch(gate(STATUS_UNKNOWN), already_proven=True)
    assert out["status"] == STATUS_REACHED


def test_A3_unproven_not_reached_stays_not_reached():
    out = apply_monotonic_latch(gate(STATUS_NOT_REACHED), already_proven=False)
    assert out["status"] == STATUS_NOT_REACHED


def test_A4_unproven_unknown_stays_unknown():
    out = apply_monotonic_latch(gate(STATUS_UNKNOWN), already_proven=False)
    assert out["status"] == STATUS_UNKNOWN


def test_A5_the_latch_is_one_way_only():
    # THE property. It may only ever turn not-reached INTO reached; a reached
    # verdict is never downgraded, whatever `already_proven` says.
    for proven in (True, False):
        out = apply_monotonic_latch(gate(STATUS_REACHED, entry_pos=7), already_proven=proven)
        assert out["status"] == STATUS_REACHED
        assert out["entry_pos"] == 7, "a real entry position must survive untouched"


def test_A6_reached_verdict_is_returned_unchanged_object_wise():
    g = gate(STATUS_REACHED, entry_pos=3)
    assert apply_monotonic_latch(g, already_proven=True) is g


def test_A7_latch_does_not_mutate_the_caller_verdict():
    g = gate(STATUS_NOT_REACHED)
    apply_monotonic_latch(g, already_proven=True)
    assert g["status"] == STATUS_NOT_REACHED, "verdict mutated in place"


def test_A8_latched_verdict_is_marked():
    out = apply_monotonic_latch(gate(STATUS_NOT_REACHED), already_proven=True)
    assert out["monotonic_latch"] is True


def test_A9_a_genuine_verdict_is_not_marked():
    assert "monotonic_latch" not in apply_monotonic_latch(
        gate(STATUS_REACHED), already_proven=True)


def test_A10_latched_entry_pos_is_none_so_the_walk_starts_at_zero():
    # `_pos = _gate["entry_pos"] or 0` — a latched pass has no located bar, and
    # 0 is correct: the fill happened in the birth candle, which the strict
    # `> generated_at` filter keeps out of every window, so every bar the walk
    # can see opened after it.
    out = apply_monotonic_latch(gate(STATUS_NOT_REACHED), already_proven=True)
    assert out["entry_pos"] is None
    assert (out["entry_pos"] or 0) == 0


def test_A11_unknown_reason_survives_for_telemetry():
    out = apply_monotonic_latch(
        gate(STATUS_UNKNOWN, unknown_reason="observation_window_incomplete"),
        already_proven=True)
    assert out["unknown_reason"] == "observation_window_incomplete"


def test_A12_latch_is_idempotent():
    once = apply_monotonic_latch(gate(STATUS_NOT_REACHED), already_proven=True)
    twice = apply_monotonic_latch(once, already_proven=True)
    assert once == twice


# ───────────────── B. the oscillation, replayed against the real gate ────────

def _collapsed(price):
    """The frame the tracker builds while the birth candle is still forming:
    one row, high = low = close = the live price."""
    return dict(highs=[price], lows=[price], opens=[price])


ENTRY = 592.0825          # BNBUSDT H1, (592.05 + 592.115) / 2
BULL = True


def test_B1_the_real_gate_reproduces_the_production_flip():
    # 16:42 price at/below entry -> reached. 16:44 price back above -> not.
    at_1642 = entry_activation(is_bull=BULL, level=ENTRY, window_complete=True,
                               **_collapsed(592.00))
    at_1644 = entry_activation(is_bull=BULL, level=ENTRY, window_complete=True,
                               **_collapsed(592.49))
    assert at_1642["status"] == STATUS_REACHED
    assert at_1644["status"] == STATUS_NOT_REACHED, "this is the defect, unlatched"


def test_B2_the_latch_holds_the_fill_across_the_flip():
    at_1644 = entry_activation(is_bull=BULL, level=ENTRY, window_complete=True,
                               **_collapsed(592.49))
    held = apply_monotonic_latch(at_1644, already_proven=True)
    assert held["status"] == STATUS_REACHED


def test_B3_short_side_flips_the_same_way_and_is_held():
    lvl = 0.693187
    touched = entry_activation(is_bull=False, level=lvl, window_complete=True,
                               **_collapsed(0.6940))
    away = entry_activation(is_bull=False, level=lvl, window_complete=True,
                            **_collapsed(0.6900))
    assert touched["status"] == STATUS_REACHED
    assert away["status"] == STATUS_NOT_REACHED
    assert apply_monotonic_latch(away, already_proven=True)["status"] == STATUS_REACHED


def test_B4_many_consecutive_passes_stay_reached_once_proven():
    # Monotone across a whole sequence, not just one pass.
    prices = [592.49, 593.10, 591.90, 594.00, 592.20, 600.00]
    out = [apply_monotonic_latch(
        entry_activation(is_bull=BULL, level=ENTRY, window_complete=True, **_collapsed(p)),
        already_proven=True)["status"] for p in prices]
    assert out == [STATUS_REACHED] * len(prices)


def test_B5_an_unproven_signal_still_oscillates_by_design():
    # The latch must not freeze a signal that has never filled — it keeps being
    # evaluated so a genuine later fill is still caught.
    away = apply_monotonic_latch(
        entry_activation(is_bull=BULL, level=ENTRY, window_complete=True, **_collapsed(593.0)),
        already_proven=False)
    near = apply_monotonic_latch(
        entry_activation(is_bull=BULL, level=ENTRY, window_complete=True, **_collapsed(592.0)),
        already_proven=False)
    assert away["status"] == STATUS_NOT_REACHED
    assert near["status"] == STATUS_REACHED


def test_B6_empty_window_is_unknown_and_latched_only_when_proven():
    for empty in ([], (), None):
        g = entry_activation(is_bull=BULL, level=ENTRY, highs=empty, lows=empty,
                             opens=empty, window_complete=True)
        assert g["status"] == STATUS_UNKNOWN
        assert apply_monotonic_latch(g, already_proven=False)["status"] == STATUS_UNKNOWN
        assert apply_monotonic_latch(g, already_proven=True)["status"] == STATUS_REACHED


def test_B7_gap_through_entry_is_reached_without_the_latch():
    # A LONG gaps THROUGH its entry by opening below it — the fill is real and
    # needs no latch. (Opening above, with the low never reaching entry, is the
    # opposite case and correctly reads not_reached; see test_B5.)
    g = entry_activation(is_bull=BULL, level=ENTRY, highs=[591.0], lows=[585.0],
                         opens=[591.0], window_complete=True)
    assert g["status"] == STATUS_REACHED
    assert "monotonic_latch" not in apply_monotonic_latch(g, already_proven=True)


# ───────────────── C. wiring: the proof is persistent and per-signal ─────────

def test_C1_the_proof_set_is_read_once_per_pass():
    src = _impl()
    assert "proven_entry_ids" in src
    assert src.count("proven_entry_ids = set(") == 1, "one query per pass, not per signal"


def test_C2_the_proof_is_the_persistent_promotion_row():
    src = _impl()
    assert "SignalStatusHistory.from_status == lifecycle.WAITING_ENTRY" in src
    assert "SignalStatusHistory.to_status == lifecycle.ACTIVE" in src


def test_C3_the_proof_is_NOT_merely_being_active():
    # A legacy signal born `active` has never been gated; shielding it would let
    # the phantom-fill cohort this gate exists to catch slip straight through.
    src = _impl()
    latch_call = src.split("apply_monotonic_latch(")[1][:200]
    assert "signal.id in proven_entry_ids" in latch_call
    assert "live_status != " not in latch_call


def test_C4_the_query_is_skipped_when_the_flag_is_off():
    src = _impl()
    head = src.split("proven_entry_ids: set = set()")[1][:160]
    assert "if entry_activation_enabled():" in head


def test_C5_the_latch_runs_before_the_demotion():
    src = _impl()
    assert src.index("apply_monotonic_latch(") < src.index("to_status=lifecycle.WAITING_ENTRY")


def test_C6_the_latch_logic_lives_in_one_place():
    # Not re-implemented inline next to its own helper.
    src = _impl()
    assert "monotonic_latch=True" not in src, "latch rebuilt in the tracker"


def test_C7_LOCKED_the_collapse_rule_is_untouched():
    # Three tests pin high=low=close; the fix must not reach for it.
    src = _src(TRACKER)
    assert 'still_forming["high"] = still_forming["close"]' in src
    assert 'still_forming["low"] = still_forming["close"]' in src


def test_C8_LOCKED_the_strict_birth_candle_filter_is_untouched():
    assert "df_after = df[df_naive_idx > sig_time]" in _src(TRACKER)


# ───────────────────────── SABOTAGE ─────────────────────────────────────────

def test_S1_a_memoryless_gate_loses_the_fill():
    # The shipped behaviour: no latch at all.
    def broken(gate_dict, *, already_proven):
        return gate_dict
    away = entry_activation(is_bull=BULL, level=ENTRY, window_complete=True,
                            **_collapsed(592.49))
    assert broken(away, already_proven=True)["status"] == STATUS_NOT_REACHED
    assert apply_monotonic_latch(away, already_proven=True)["status"] == STATUS_REACHED


def test_S2_a_two_way_latch_would_un_fill_a_real_entry():
    def broken(gate_dict, *, already_proven):
        return dict(gate_dict, status=STATUS_REACHED if already_proven else STATUS_NOT_REACHED)
    real = entry_activation(is_bull=BULL, level=ENTRY, window_complete=True,
                            **_collapsed(592.00))
    assert real["status"] == STATUS_REACHED
    assert broken(real, already_proven=False)["status"] == STATUS_NOT_REACHED
    assert apply_monotonic_latch(real, already_proven=False)["status"] == STATUS_REACHED


def test_S3_latching_on_live_status_would_shield_legacy_signals():
    # "already active" is not proof the GATE ever cleared it.
    legacy_active_never_gated = False   # no promotion row exists
    away = entry_activation(is_bull=BULL, level=ENTRY, window_complete=True,
                            **_collapsed(593.0))
    assert apply_monotonic_latch(
        away, already_proven=legacy_active_never_gated)["status"] == STATUS_NOT_REACHED


def test_S4_mutating_the_verdict_in_place_leaks_across_passes():
    def broken(gate_dict, *, already_proven):
        if already_proven:
            gate_dict["status"] = STATUS_REACHED     # in-place
        return gate_dict
    g = gate(STATUS_NOT_REACHED)
    broken(g, already_proven=True)
    assert g["status"] == STATUS_REACHED, "the caller's dict was corrupted"
    g2 = gate(STATUS_NOT_REACHED)
    apply_monotonic_latch(g2, already_proven=True)
    assert g2["status"] == STATUS_NOT_REACHED


def test_S5_a_per_signal_query_would_be_n_plus_1():
    src = _impl()
    gate_block = src.split("_gate = None")[1].split("_bw = _resolve_signal_bar_walk")[0]
    assert "await db.execute" not in gate_block, "proof lookup moved inside the loop"


def test_S6_keeping_the_real_entry_pos_matters():
    # If the latch overwrote entry_pos on a genuine verdict the walk would
    # restart from bar 0 and could book a target hit that predates the fill.
    def broken(gate_dict, *, already_proven):
        return dict(gate_dict, status=STATUS_REACHED, entry_pos=None)
    real = gate(STATUS_REACHED, entry_pos=5)
    assert broken(real, already_proven=True)["entry_pos"] is None
    assert apply_monotonic_latch(real, already_proven=True)["entry_pos"] == 5
