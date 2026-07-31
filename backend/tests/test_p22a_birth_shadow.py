"""P2.2-a birth-time shadow classification.

~6 500 candidates a day carry engine_direction='neutral' — the engine said HOLD,
so no bar and no amount of waiting can ever produce a shadow verdict for them.
They were being inserted pending and retired by a separate UPDATE afterwards,
which meant `shadow_evaluated_at IS NULL` meant two different things at once and
the retirement pass had to be run forever just to keep up with arrivals.

Everything the classification needs — direction and geometry — is already final
when the row is written. So it is decided once, at birth.

What this must NOT do: touch the decision. verdict, demotion_reason, confidence,
composite, direction, geometry and lifecycle are all final before the logger is
called, and nothing here writes back to them.
"""
import ast
import inspect
import re
import textwrap
from datetime import datetime, timezone

import pandas as pd
import pytest

from app.models.decision_candidate import (
    EVALUABLE_DIRECTIONS,
    SHADOW_NO_FILL,
    SHADOW_PERMANENT_REASONS,
    SHADOW_REASON_NO_DIRECTION,
    SHADOW_REASON_NO_GEOMETRY,
    SHADOW_UNDECIDABLE,
    SignalDecisionCandidate,
    classify_birth_shadow,
)
from app.services import candidate_log

BAR = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
EZ_LOW, EZ_HIGH, SL, TP1, TP2, TP3 = 99.0, 101.0, 97.0, 101.5, 103.0, 105.0

MEASUREMENT_FIELDS = (
    "shadow_return_pct", "shadow_r_multiple", "shadow_mfe_pct", "shadow_mae_pct",
    "shadow_bars_walked", "shadow_resolved_at", "shadow_resolution_path",
    "shadow_detail_label", "shadow_entry_reached", "shadow_entry_reached_at",
    "shadow_bars_to_entry", "shadow_never_entered", "shadow_max_zone_penetration_pct",
    "shadow_zone_far_edge_reached", "shadow_stop_before_valid_entry",
    "shadow_invalidated_before_entry",
)


def _frame():
    idx = pd.date_range(BAR, periods=1, freq="15min", tz="UTC")
    return pd.DataFrame([(100.0, 100.5, 99.5, 100.0)],
                        columns=["open", "high", "low", "close"], index=idx)


def _values(*, direction="bullish", entry_low=EZ_LOW, entry_high=EZ_HIGH, stop=SL,
            verdict="dropped", **over):
    kw = dict(
        asset_id="a", symbol="BTCUSDT", timeframe="15m",
        decision={"signal_type": "BUY", "direction": direction, "confidence_score": 71.0,
                  "entry_zone_low": entry_low, "entry_zone_high": entry_high,
                  "stop_loss": stop, "tp1": TP1, "tp2": TP2, "tp3": TP3,
                  "engine_results": [], "birth_telemetry": {}, "consensus_telemetry": {}},
        df=_frame(), evaluated_at=BAR, verdict=verdict, demotion_reason=None,
    )
    kw.update(over)
    return candidate_log.build_candidate_values(**kw)


# ── 1-2 · permanently unevaluable rows are stamped at birth ────────────────
@pytest.mark.parametrize("direction", ["neutral", None, "", "sideways"])
def test_1_no_direction_candidate_is_undecidable_at_birth(direction):
    """Anything that is not a walkable direction is permanent, not just the
    literal 'neutral' — an unrecognised value must not fall through as evaluable."""
    v = _values(direction=direction)
    assert v["shadow_outcome"] == SHADOW_UNDECIDABLE
    assert v["shadow_resolution_reason"] == SHADOW_REASON_NO_DIRECTION
    assert v["shadow_evaluated_at"] == BAR


@pytest.mark.parametrize("missing", ["entry_low", "entry_high", "stop"])
def test_2_no_geometry_candidate_is_undecidable_at_birth(missing):
    v = _values(**{missing: None})
    assert v["shadow_outcome"] == SHADOW_UNDECIDABLE
    assert v["shadow_resolution_reason"] == SHADOW_REASON_NO_GEOMETRY
    assert v["shadow_evaluated_at"] == BAR


# ── 3-5 · evaluable rows stay pending ──────────────────────────────────────
@pytest.mark.parametrize("direction", list(EVALUABLE_DIRECTIONS))
def test_3_4_evaluable_candidate_stays_pending(direction):
    v = _values(direction=direction)
    assert v["shadow_outcome"] is None, "an evaluable row must not be pre-stamped"
    assert v["shadow_resolution_reason"] is None
    assert v["shadow_evaluated_at"] is None, "must stay in the pass-B queue"


@pytest.mark.parametrize("direction", list(EVALUABLE_DIRECTIONS))
def test_5_published_candidate_is_never_stamped(direction):
    """Measured on production: all 14 published rows carry a real direction and
    complete geometry, so the predicate cannot reach them. Pinned here so a
    future geometry change cannot silently start retiring published candidates."""
    v = _values(direction=direction, verdict="published", demotion_reason="published")
    assert v["shadow_outcome"] is None
    assert v["shadow_evaluated_at"] is None
    assert v["verdict"] == "published", "the verdict must be untouched"


# ── 6 · reason priority is deterministic ───────────────────────────────────
def test_6_direction_wins_when_both_conditions_hold():
    v = _values(direction="neutral", entry_low=None, entry_high=None, stop=None)
    assert v["shadow_resolution_reason"] == SHADOW_REASON_NO_DIRECTION, \
        "direction must win; the SQL CASE tests it first and the two must agree"


def test_6b_python_and_sql_paths_agree_on_the_whole_truth_table():
    """The retirement pass decides the same thing in SQL. If the two ever drift,
    a row retired offline and the same row stamped at birth would carry different
    reasons — and neither would be wrong-looking on its own."""
    sql_text, params = _compiled_pass_a(_runner())

    # The reasons are bound, not inlined, so compare where their placeholders sit.
    key_dir = next(k for k, v in params.items() if v == SHADOW_REASON_NO_DIRECTION)
    key_geo = next(k for k, v in params.items() if v == SHADOW_REASON_NO_GEOMETRY)
    assert sql_text.index(key_dir) < sql_text.index(key_geo), \
        "SQL CASE must test direction first, exactly as classify_birth_shadow does"

    for direction in ("bullish", "bearish", "neutral", None, "unknown"):
        for geo in ((EZ_LOW, EZ_HIGH, SL), (None, EZ_HIGH, SL),
                    (EZ_LOW, None, SL), (EZ_LOW, EZ_HIGH, None), (None, None, None)):
            got = classify_birth_shadow(direction, *geo)
            if direction not in EVALUABLE_DIRECTIONS:
                want = SHADOW_REASON_NO_DIRECTION      # direction first, always
            elif None in geo:
                want = SHADOW_REASON_NO_GEOMETRY
            else:
                want = None
            assert got == want, f"{direction!r} {geo} -> {got!r}, beklenen {want!r}"


# ── 7 · timestamp ──────────────────────────────────────────────────────────
def test_7_stamp_is_timezone_aware_and_equals_the_decision_time():
    v = _values(direction="neutral")
    stamp = v["shadow_evaluated_at"]
    assert stamp.tzinfo is not None, "a naive stamp breaks every horizon comparison"
    assert stamp == v["evaluated_at"], "stamp must be the decision's own timestamp"


# ── 8 · a retired row is not a measurement ─────────────────────────────────
def test_8_birth_stamped_row_carries_no_measurement():
    v = _values(direction="neutral")
    for field in MEASUREMENT_FIELDS:
        assert v.get(field) is None, f"{field} must stay NULL — retired is not resolved"


# ── 9 · gate integrity ─────────────────────────────────────────────────────
def test_9_undecidable_is_not_counted_as_scored():
    """Birth-stamping gives ~6 500 rows a day a shadow_evaluated_at. If `resolved`
    were ever defined as that column being non-null, the observation gate would
    read orders of magnitude high."""
    rep = inspect.getsource(_runner().report)
    assert 'r.shadow_outcome != "undecidable"' in rep
    assert SHADOW_UNDECIDABLE == "undecidable"
    assert 'r.shadow_outcome != "never_entered"' in rep
    assert SHADOW_NO_FILL == "never_entered"


# ── 10-12 · the write path is unchanged ────────────────────────────────────
def test_10_idempotency_key_is_untouched():
    src = inspect.getsource(candidate_log.record_candidate)
    assert 'index_elements=["asset_id", "timeframe", "evaluated_bar_time",' in src
    assert "on_conflict_do_nothing" in src
    cols = {c.key for c in SignalDecisionCandidate.__table__.columns}
    for c in ("shadow_outcome", "shadow_resolution_reason", "shadow_evaluated_at"):
        assert c in cols, "no migration: these columns already exist"


def test_11_retry_does_not_duplicate_or_change_the_stamp():
    """Two builds of the same evaluation must be byte-identical, so a retry that
    loses the ON CONFLICT race cannot produce a differing row."""
    a, b = _values(direction="neutral"), _values(direction="neutral")
    assert a["shadow_outcome"] == b["shadow_outcome"]
    assert a["shadow_evaluated_at"] == b["shadow_evaluated_at"]
    assert (a["asset_id"], a["timeframe"], a["evaluated_bar_time"],
            a["policy_version"], a["source"]) == \
           (b["asset_id"], b["timeframe"], b["evaluated_bar_time"],
            b["policy_version"], b["source"])


def test_12_logger_stays_fail_open():
    src = inspect.getsource(candidate_log.record_candidate)
    assert "except Exception" in src
    assert "begin_nested" in src, "the savepoint must survive this change"
    # A frame with no scored bar still returns None rather than raising.
    assert candidate_log.build_candidate_values(
        asset_id="a", symbol="X", timeframe="15m",
        decision={"direction": "neutral"},
        df=pd.DataFrame(columns=["open", "high", "low", "close"]),
        evaluated_at=BAR, verdict="dropped", demotion_reason=None) is None


# ── 13-15 · the offline pass still behaves ─────────────────────────────────
def test_13_pass_a_still_selects_legacy_backlog():
    """Rows written before this change are still pending and must remain
    reachable — birth-stamping is not retroactive."""
    runner = _runner()
    src = inspect.getsource(runner.retire_permanent)
    assert "shadow_evaluated_at.is_(None)" in src
    assert "unevaluable_predicate()" in src


def test_14_pass_a_skips_rows_already_stamped_at_birth():
    """A birth-stamped row has shadow_evaluated_at set, so the same
    `IS NULL` predicate that gives idempotency also excludes it — pass A
    naturally stops re-processing them without a second mechanism."""
    runner = _runner()
    ids_where = inspect.getsource(runner.retire_permanent)
    assert "shadow_evaluated_at.is_(None)" in ids_where
    assert ids_where.count("shadow_evaluated_at.is_(None)") == 2


def test_15_evaluable_candidate_remains_selectable_for_pass_b():
    runner = _runner()
    pred = inspect.getsource(runner.evaluable_predicate)
    assert "EVALUABLE_DIRECTIONS" in pred
    v = _values(direction="bullish")
    # The row this build produces satisfies pass B's selection.
    assert v["shadow_evaluated_at"] is None
    assert v["engine_direction"] in EVALUABLE_DIRECTIONS
    assert v["entry_zone_low"] is not None and v["stop_loss"] is not None


# ── 16 · live decision behaviour is untouched ──────────────────────────────
def test_16_live_gates_and_thresholds_are_unchanged():
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
    # The classifier must not have leaked into the decision file.
    assert "classify_birth_shadow" not in sch
    # Nor may any Pass A / Pass B COLUMN be written from it. This was a blanket
    # `"shadow_" not in sch`, which CP-MACRO-SHADOW-B's additive `macro_shadow=`
    # keyword trips without touching a single one of those fields. Spelling the
    # columns out is strictly stronger than the substring it replaces: the old
    # form would have missed a column added under a different prefix, and it
    # could not distinguish "writes a shadow column" from "mentions the word".
    for col in ("shadow_outcome", "shadow_resolution_reason", "shadow_evaluated_at",
                "shadow_resolution_path", "shadow_resolved_at", "shadow_detail_label",
                "shadow_return_pct", "shadow_r_multiple", "shadow_mfe_pct",
                "shadow_mae_pct", "shadow_bars_walked", "shadow_entry_reached",
                "shadow_entry_reached_at", "shadow_bars_to_entry",
                "shadow_never_entered", "shadow_max_zone_penetration_pct",
                "shadow_zone_far_edge_reached", "shadow_stop_before_valid_entry",
                "shadow_invalidated_before_entry"):
        assert col not in sch, col
    # And the shadow-shaped identifiers that ARE allowed in the decision file are
    # exactly these two — the additive telemetry argument and its builder. Scanned
    # on CODE: `ast.unparse` drops comments, so prose that merely says "shadow"
    # cannot fail this, and only real identifiers can.
    code = ast.unparse(ast.parse(textwrap.dedent(sch)))
    shadowish = {t for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", code) if "shadow" in t}
    assert shadowish == {"macro_shadow", "build_candidate_macro_shadow",
                         "get_shadow_macro_snapshot"}, shadowish


def test_16b_classification_does_not_read_or_alter_the_decision():
    """Same inputs, two verdicts: the stamp depends only on direction+geometry."""
    for verdict, reason in (("dropped", "not_actionable"), ("skipped", "duplicate_or_existing")):
        v = _values(direction="neutral", verdict=verdict, demotion_reason=reason)
        assert v["verdict"] == verdict
        assert v["demotion_reason"] == reason
        assert v["shadow_outcome"] == SHADOW_UNDECIDABLE
    # And an evaluable row is untouched regardless of verdict.
    assert _values(direction="bullish", verdict="skipped")["shadow_outcome"] is None


def test_permanent_reasons_are_exactly_the_two_the_classifier_can_return():
    assert SHADOW_PERMANENT_REASONS == {SHADOW_REASON_NO_DIRECTION, SHADOW_REASON_NO_GEOMETRY}
    produced = {classify_birth_shadow(d, *g)
                for d in ("neutral", None, "bullish")
                for g in ((EZ_LOW, EZ_HIGH, SL), (None, None, None))}
    assert produced - {None} == SHADOW_PERMANENT_REASONS


def _compiled_pass_a(runner):
    """Capture and compile pass A's UPDATE so its CASE ordering can be inspected."""
    import asyncio

    from sqlalchemy.dialects import postgresql

    class _Rec:
        def __init__(self):
            self.stmts = []

        async def execute(self, stmt):
            self.stmts.append(stmt)

            class R:
                rowcount = 0
            return R()

    rec = _Rec()
    asyncio.run(runner.retire_permanent(rec, 1))
    compiled = rec.stmts[0].compile(dialect=postgresql.dialect())
    return str(compiled), compiled.params


def _runner():
    """Import the runner script by path — it lives in scripts/, not a package."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "p22a_shadow_eval.py"
    spec = importlib.util.spec_from_file_location("p22a_runner_birth", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
