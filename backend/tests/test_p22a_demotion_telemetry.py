"""P2.2-a M2 — the FIRST demotion reason must survive the overwrite.

`demotion_reason` is overwritten by design at each later decision site. That is
right for "how did this end", but it destroyed the reason that fired first: a
call rejected by the confidence gate that then also met an active signal was
filed purely as duplicate_or_existing, making confidence-gate rejections
uncountable — and that count is exactly what P2.2-b's threshold calibration
needs.

The fix is telemetry only. It adds a second first-write-wins local in the
scheduler and one key inside the existing `extra` JSON column: no migration, no
new column, no branch reads either value, and the terminal `demotion_reason`
keeps its meaning for every existing row and query.
"""
import inspect
from datetime import datetime, timezone

import pandas as pd
import pytest

from app.models.decision_candidate import (
    REASON_CONFIDENCE_GATE,
    REASON_DUPLICATE_OR_EXISTING,
    REASON_NOT_ACTIONABLE,
    REASON_PUBLISHED,
    REASON_REVERSAL_DEFER,
)
from app.services import candidate_log

BAR = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
EZ_LOW, EZ_HIGH, SL, TP1, TP2, TP3 = 99.0, 101.0, 97.0, 101.5, 103.0, 105.0


def _frame(rows):
    idx = pd.date_range(BAR, periods=len(rows), freq="15min", tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


def _kw(**over):
    kw = dict(
        asset_id="a", symbol="BTCUSDT", timeframe="15m",
        decision={"signal_type": "BUY", "direction": "bullish", "confidence_score": 60.0,
                  "entry_zone_low": EZ_LOW, "entry_zone_high": EZ_HIGH, "stop_loss": SL,
                  "tp1": TP1, "tp2": TP2, "tp3": TP3, "engine_results": [],
                  "birth_telemetry": {}, "consensus_telemetry": {}},
        df=_frame([(100.0, 100.5, 99.5, 100.0)]),
        evaluated_at=BAR, verdict="dropped", demotion_reason=REASON_NOT_ACTIONABLE,
    )
    kw.update(over)
    return kw


@pytest.mark.parametrize("primary,terminal", [
    (REASON_CONFIDENCE_GATE, REASON_CONFIDENCE_GATE),          # only the gate fired
    (REASON_DUPLICATE_OR_EXISTING, REASON_DUPLICATE_OR_EXISTING),  # only the skip fired
    (REASON_CONFIDENCE_GATE, REASON_DUPLICATE_OR_EXISTING),    # gate FIRST, then skip
    (REASON_NOT_ACTIONABLE, REASON_DUPLICATE_OR_EXISTING),     # engine HOLD, then skip
    (REASON_NOT_ACTIONABLE, REASON_NOT_ACTIONABLE),            # engine HOLD only
    (REASON_REVERSAL_DEFER, REASON_REVERSAL_DEFER),            # reversal defer
    (REASON_PUBLISHED, REASON_PUBLISHED),                      # published
])
def test_m2_both_reasons_are_recorded(primary, terminal):
    v = candidate_log.build_candidate_values(
        **_kw(demotion_reason=terminal, primary_demotion_reason=primary))
    assert v["demotion_reason"] == terminal, "terminal reason must keep its meaning"
    assert v["extra"]["primary_demotion_reason"] == primary, "first reason was lost"


def test_m2_confidence_gate_rejection_stays_countable_when_a_skip_follows():
    """The exact case that was invisible: the gate rejected it, then an active
    signal existed, and the row was filed purely as duplicate_or_existing."""
    v = candidate_log.build_candidate_values(**_kw(
        verdict="skipped",
        demotion_reason=REASON_DUPLICATE_OR_EXISTING,
        primary_demotion_reason=REASON_CONFIDENCE_GATE))
    assert v["demotion_reason"] == REASON_DUPLICATE_OR_EXISTING
    assert v["extra"]["primary_demotion_reason"] == REASON_CONFIDENCE_GATE


def test_m2_scheduler_assigns_primary_first_write_wins():
    from app.services import scheduler

    src = inspect.getsource(scheduler._generate_signal)
    # Initialised once, then only ever set behind a None check.
    assert "primary_demotion_reason = demotion_reason" in src
    assert src.count("if primary_demotion_reason is None:") == 3
    # Every record_candidate call carries it.
    assert src.count("primary_demotion_reason=") == 3


def test_m2_needs_no_migration():
    """`extra` is an existing JSON column, so nothing about the schema, existing
    rows or existing queries changes."""
    from app.models.decision_candidate import SignalDecisionCandidate

    cols = set(SignalDecisionCandidate.__table__.columns.keys())
    assert "extra" in cols
    assert "primary_demotion_reason" not in cols, "must NOT become a column in this checkpoint"


def test_m2_omitting_the_new_kwarg_stays_safe():
    """Callers that predate the change must not break."""
    v = candidate_log.build_candidate_values(**_kw())
    assert v["extra"]["primary_demotion_reason"] is None


# ── live decision behaviour is untouched ───────────────────────────────────
def test_live_gates_and_thresholds_are_unchanged():
    from app.engines.ai_decision import signal_generator as sg
    from app.services import scheduler

    gen = inspect.getsource(sg.generate_signal)
    for band in ("composite_score >= 68.0", "composite_score >= 54.0",
                 "composite_score >= 46.0", "composite_score >= 32.0"):
        assert band in gen
    assert "min(bullish_count, bearish_count) * 4.0" in gen

    sch = inspect.getsource(scheduler._generate_signal)
    assert "MIN_ACTIONABLE_CONFIDENCE = 65.0" in sch
    assert "REVERSAL_MIN_CONFIDENCE = 72.0" in sch
    assert sch.count("await record_candidate(") == 3
    # The new local is written but never branched on.
    for banned in ("if primary_demotion_reason ==", "elif primary_demotion_reason",
                   "if not primary_demotion_reason:"):
        assert banned not in sch
