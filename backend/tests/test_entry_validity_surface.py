"""CP-ENTRY-VALIDITY-TELEMETRY-SURFACE — canonical entry-validity classifier & report.

The properties pinned here are the ones whose violation is SILENT: a coerced
``None``, an ``unknown`` folded into ``reached``, an infinite profit factor on a
cohort with no losses. Each of those makes the numbers look better and none of
them raises. So most tests below are written as MUTATION tests: they construct
the plausible wrong implementation, show it produces a different answer, and
then pin the real one. A test that only asserts the current output would pass
against the broken version too.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from app.services import entry_validity as ev
from app.services.entry_validity import (
    CANONICAL_ENTRY_KEYS,
    MIN_RELIABLE_SAMPLE,
    classify_entry_validity,
    compute_entry_validity_report,
    select_trade_path_row,
    summarize_cohort,
)

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
BACKEND = pathlib.Path(__file__).resolve().parents[1]
PRODUCER = BACKEND / "app" / "engines" / "ai_decision" / "entry_telemetry.py"


def block(**over):
    """A well-formed, current-shape entry block (all nine canonical keys)."""
    base = {
        "telemetry_version": 1,
        "entry_level": 100.0,
        "data_available": True,
        "entry_reached": True,
        "entry_reached_at": "2026-08-01T00:00:00",
        "bars_to_entry": 3,
        "wait_seconds": 900,
        "max_zone_penetration_pct": 0.42,
        "never_entered": False,
    }
    base.update(over)
    return base


def never_block(**over):
    return block(
        entry_reached=False,
        never_entered=True,
        entry_reached_at=None,
        bars_to_entry=None,
        **over,
    )


def rec(status_block, *, outcome="WIN", ret=1.0, **over):
    r = {
        "signal_id": over.pop("signal_id", "s"),
        "symbol": over.pop("symbol", "BTCUSDT"),
        "timeframe": over.pop("timeframe", "15m"),
        "direction": over.pop("direction", "bullish"),
        "risk_level": over.pop("risk_level", "medium"),
        "confidence": over.pop("confidence", 70.0),
        "regime": over.pop("regime", "trending_bull"),
        "outcome": outcome,
        "return_pct": ret,
        "mfe_pct": over.pop("mfe_pct", 2.0),
        "mae_pct": over.pop("mae_pct", 0.5),
        "hit_tp1": over.pop("hit_tp1", True),
        "hit_tp2": over.pop("hit_tp2", False),
        "hit_tp3": over.pop("hit_tp3", False),
        "entry_validity": status_block,
    }
    r.update(over)
    return r


class _Row:
    """Minimal stand-in for a SignalTradePath ORM row."""

    def __init__(self, rid, created_at, extra=None):
        self.id = rid
        self.created_at = created_at
        self.extra = extra


class _Stamp:
    """Comparable, isoformat-able fake timestamp (no real clock in tests)."""

    def __init__(self, n):
        self.n = n

    def isoformat(self):
        return f"2026-08-0{self.n}T00:00:00"


# --------------------------------------------------------------------------- #
# 1. contract pin — the field names come from the PRODUCER, not from us
# --------------------------------------------------------------------------- #
def test_canonical_keys_match_the_producer_module_verbatim():
    """The nine key names are pinned as literals AND cross-checked against the
    dict literal that actually writes them, parsed out of entry_telemetry.py.

    Neither side may be derived from the other: the literals below are typed by
    hand, and the producer side is read from source. A rename in either place
    breaks this test, which is the entire point — the whole surface reads keys
    by name, so a silent rename would turn every row into ``unknown``.
    """
    expected = (
        "telemetry_version",
        "entry_level",
        "data_available",
        "entry_reached",
        "entry_reached_at",
        "bars_to_entry",
        "wait_seconds",
        "max_zone_penetration_pct",
        "never_entered",
    )
    assert tuple(CANONICAL_ENTRY_KEYS) == expected

    tree = ast.parse(PRODUCER.read_text(encoding="utf-8"))
    produced = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign):
            continue
        if getattr(node.target, "id", None) == "base" and isinstance(node.value, ast.Dict):
            produced = tuple(
                k.value for k in node.value.keys if isinstance(k, ast.Constant)
            )
            break

    assert produced is not None, "entry_telemetry.py no longer defines `base` as a dict literal"
    assert set(produced) == set(expected), (
        f"producer writes {sorted(produced)}, surface reads {sorted(expected)}"
    )


def test_producer_still_documents_data_available_as_not_never_entered():
    """``data_available=False`` must stay 'no bars to observe', not 'no fill'.

    If that comment ever flips, the 18 production rows currently classified as
    ``unknown`` would belong in ``not_reached`` instead — a semantic change the
    surface cannot detect at runtime.
    """
    src = PRODUCER.read_text(encoding="utf-8")
    assert "no post-birth bars to observe" in src
    assert "never entered" in src


# --------------------------------------------------------------------------- #
# 2. the three cohorts, and only the three
# --------------------------------------------------------------------------- #
def test_reached_not_reached_unknown_are_the_only_statuses():
    cases = [
        classify_entry_validity(block()),
        classify_entry_validity(never_block()),
        classify_entry_validity(None),
        classify_entry_validity(None, has_trade_path=False),
        classify_entry_validity(block(entry_reached=True, never_entered=True)),
        classify_entry_validity(block(data_available=False, entry_reached=None, never_entered=None)),
        classify_entry_validity("not a mapping"),
        classify_entry_validity(block(entry_reached="true")),
    ]
    assert {c["status"] for c in cases} <= set(ev.CANONICAL_STATUSES)
    assert classify_entry_validity(block())["status"] == ev.STATUS_REACHED
    assert classify_entry_validity(never_block())["status"] == ev.STATUS_NOT_REACHED


def test_no_trade_path_and_no_entry_block_are_distinguishable_unknowns():
    """Both are unknown, but they are different failures and production has
    both (604 rows with no trade_path, 1291 with a path but no entry block)."""
    a = classify_entry_validity(None, has_trade_path=False)
    b = classify_entry_validity(None, has_trade_path=True)
    assert a["status"] == b["status"] == ev.STATUS_UNKNOWN
    assert a["unknown_reason"] != b["unknown_reason"]
    assert a["unknown_reason"] == ev.UNKNOWN_NO_TRADE_PATH
    assert b["unknown_reason"] == ev.UNKNOWN_NO_ENTRY_BLOCK


# --------------------------------------------------------------------------- #
# 3. MUTATION: null is never coerced
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "blk",
    [
        {"telemetry_version": 1, "entry_level": 1.0, "data_available": False},
        block(entry_reached=None, never_entered=None, data_available=True),
        {},
    ],
)
def test_absent_flags_are_unknown_not_false(blk):
    """The plausible bug is ``bool(entry_block.get("entry_reached"))``, which
    turns every absent flag into a confident False. Show that wrong reading
    disagrees, then pin the right one."""
    naive_status = "not_reached" if not blk.get("entry_reached") else "reached"
    real = classify_entry_validity(blk)

    assert naive_status == "not_reached"          # what the coercing version says
    assert real["status"] == ev.STATUS_UNKNOWN    # what we say
    assert real["entry_reached"] is None          # and we never invent a value


def test_data_unavailable_is_unknown_not_not_reached():
    """18 production rows. Calling them 'never entered' would move real signals
    into the phantom cohort and understate it nowhere — it would corrupt both."""
    out = classify_entry_validity(
        block(data_available=False, entry_reached=None, never_entered=None,
              entry_reached_at=None, bars_to_entry=None)
    )
    assert out["status"] == ev.STATUS_UNKNOWN
    assert out["unknown_reason"] == ev.UNKNOWN_NO_POST_BIRTH_BARS
    assert out["conflict_reason"] is None  # absence is not a contradiction


@pytest.mark.parametrize("bad", ["true", "false", 1, 0, [], {}, "yes"])
def test_non_boolean_flag_is_a_conflict_not_a_truth_value(bad):
    """``"false"`` is truthy in Python. A row carrying it must never become
    ``reached`` — it must refuse to classify."""
    out = classify_entry_validity(block(entry_reached=bad))
    assert out["status"] == ev.STATUS_UNKNOWN
    assert out["conflict_reason"] == ev.CONFLICT_FLAG_NOT_BOOLEAN
    assert out["entry_reached"] is None


# --------------------------------------------------------------------------- #
# 4. contradictions
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "over,reason",
    [
        ({"entry_reached": True, "never_entered": True}, ev.CONFLICT_BOTH_TRUE),
        ({"entry_reached": False, "never_entered": False}, ev.CONFLICT_BOTH_FALSE),
        (
            {"entry_reached": True, "never_entered": False, "data_available": False},
            ev.CONFLICT_REACHED_WITHOUT_DATA,
        ),
        (
            {"entry_reached": False, "never_entered": True, "data_available": False},
            ev.CONFLICT_NEVER_WITHOUT_DATA,
        ),
    ],
)
def test_contradictory_fields_downgrade_to_unknown_with_a_reason(over, reason):
    out = classify_entry_validity(block(**over))
    assert out["status"] == ev.STATUS_UNKNOWN
    assert out["conflict_reason"] == reason
    assert out["entry_reached"] is None


def test_conflict_is_checked_before_any_positive_conclusion():
    """Ordering matters: if ``entry_reached is True`` were tested first, the
    both-true row would silently become ``reached``."""
    out = classify_entry_validity(block(entry_reached=True, never_entered=True))
    assert out["status"] != ev.STATUS_REACHED


def test_a_partially_flagged_row_decides_but_records_the_gap():
    only_reached = block(never_entered=None)
    del only_reached["never_entered"]
    out = classify_entry_validity(only_reached)
    assert out["status"] == ev.STATUS_REACHED
    assert out["source"] == ev.SOURCE_TELEMETRY_PARTIAL
    assert out["completeness"] < 1.0


# --------------------------------------------------------------------------- #
# 5. shape drift — the 25 production rows with a tenth, deleted key
# --------------------------------------------------------------------------- #
def test_unknown_extra_keys_are_ignored_not_trusted():
    """25 live rows carry ``invalidated_before_entry``, which no longer exists
    anywhere in the repo — and they carry ``telemetry_version: 1``, the same
    version as the nine-key shape. Classification must not consult it."""
    with_ghost = block(invalidated_before_entry=True)
    without = block()
    a, b = classify_entry_validity(with_ghost), classify_entry_validity(without)
    assert a["status"] == b["status"] == ev.STATUS_REACHED
    assert a["completeness"] == b["completeness"] == 1.0


def test_version_number_is_not_used_as_a_shape_discriminator():
    """Both live shapes report version 1, so branching on the version would be
    branching on a value that does not discriminate."""
    truncated = {"telemetry_version": 1, "entry_level": 5.0, "data_available": True}
    out = classify_entry_validity(truncated)
    assert out["status"] == ev.STATUS_UNKNOWN
    assert out["telemetry_version"] == 1
    assert out["completeness"] < 1.0


# --------------------------------------------------------------------------- #
# 6. deterministic row selection
# --------------------------------------------------------------------------- #
def test_duplicate_trade_path_rows_resolve_deterministically():
    rows = [
        _Row("b", _Stamp(1), {"entry": block()}),
        _Row("a", _Stamp(3), {"entry": never_block()}),
        _Row("c", _Stamp(2), {"entry": block()}),
    ]
    chosen = select_trade_path_row(rows)
    assert chosen.id == "a"                                   # newest wins
    assert select_trade_path_row(list(reversed(rows))).id == "a"
    assert select_trade_path_row(rows[::-1]) is chosen or select_trade_path_row(rows[::-1]).id == "a"


def test_selection_breaks_ties_on_id_and_survives_missing_timestamps():
    same = [_Row("z", _Stamp(1)), _Row("y", _Stamp(1))]
    assert select_trade_path_row(same).id == "z"
    assert select_trade_path_row(list(reversed(same))).id == "z"

    mixed = [_Row("n", None), _Row("t", _Stamp(1))]
    assert select_trade_path_row(mixed).id == "t"   # a timestamped row outranks a null one
    assert select_trade_path_row([]) is None
    assert select_trade_path_row([None, None]) is None


# --------------------------------------------------------------------------- #
# 7. profit factor & win rate safety
# --------------------------------------------------------------------------- #
def test_profit_factor_is_undefined_not_infinite_when_there_are_no_losses():
    """The 141-signal phantom cohort has zero losses. ``gross_profit / 0`` is
    either a ZeroDivisionError or ``inf``; both would be reported as a superb
    strategy. It has to be None."""
    stats = summarize_cohort([rec(classify_entry_validity(never_block()), ret=r) for r in (1.0, 2.0, 3.0)])
    assert stats["gross_loss"] == 0
    assert stats["profit_factor"] is None
    assert stats["profit_factor_undefined_reason"] == "no_realised_loss"


def test_profit_factor_is_computed_when_a_real_loss_exists():
    stats = summarize_cohort(
        [rec(classify_entry_validity(block()), outcome="WIN", ret=3.0),
         rec(classify_entry_validity(block()), outcome="LOSS", ret=-1.5)]
    )
    assert stats["profit_factor"] == 2.0


def test_win_rate_denominator_excludes_breakeven_expired_and_active():
    stats = summarize_cohort([
        rec(classify_entry_validity(block()), outcome="WIN", ret=1.0),
        rec(classify_entry_validity(block()), outcome="LOSS", ret=-1.0),
        rec(classify_entry_validity(block()), outcome="BREAKEVEN", ret=0.0),
        rec(classify_entry_validity(block()), outcome="EXPIRED", ret=0.0),
        rec(classify_entry_validity(block()), outcome="ACTIVE", ret=None),
    ])
    assert stats["n"] == 5
    assert stats["n_terminal"] == 4     # ACTIVE excluded
    assert stats["n_active"] == 1
    assert stats["win_rate"] == 50.0    # 1 / (1 WIN + 1 LOSS)


def test_outcome_matching_is_immune_to_the_enum_spelling():
    """``SignalOutcome.WIN.value`` is ``"win"``; the stored column holds ``"WIN"``.

    A surface that hard-codes one spelling reports zero wins, zero losses and a
    null win rate — no exception, just a plausible table of zeroes. The first
    production run of this endpoint did exactly that, and the tests missed it
    because every fixture here typed the uppercase form by hand. So this test
    takes the spellings FROM THE MODEL and asserts the three agree.
    """
    from app.models.signal import SignalOutcome

    # Pinned from the enum itself — if these ever change, the surface must know.
    assert SignalOutcome.WIN.value == "win"
    assert SignalOutcome.ACTIVE.value == "active"

    def cohort(win, loss, active):
        return summarize_cohort([
            rec(classify_entry_validity(block()), outcome=win, ret=2.0),
            rec(classify_entry_validity(block()), outcome=loss, ret=-1.0),
            rec(classify_entry_validity(block()), outcome=active, ret=None),
        ])

    stored = cohort("WIN", "LOSS", "ACTIVE")                 # column spelling
    valued = cohort(SignalOutcome.WIN.value, SignalOutcome.LOSS.value,
                    SignalOutcome.ACTIVE.value)              # .value spelling
    member = cohort(SignalOutcome.WIN, SignalOutcome.LOSS, SignalOutcome.ACTIVE)

    for name, stats in (("stored", stored), ("valued", valued), ("member", member)):
        assert stats["outcomes"]["win"] == 1, name
        assert stats["outcomes"]["loss"] == 1, name
        assert stats["n_terminal"] == 2, name       # ACTIVE excluded in every spelling
        assert stats["n_active"] == 1, name
        assert stats["win_rate"] == 50.0, name
        assert stats["profit_factor"] == 2.0, name


def test_a_record_with_no_outcome_is_not_counted_as_resolved():
    stats = summarize_cohort([rec(classify_entry_validity(block()), outcome=None, ret=None)])
    assert stats["n"] == 1
    assert stats["n_terminal"] == 0
    assert stats["n_active"] == 1
    assert stats["win_rate"] is None


def test_win_rate_is_none_not_zero_when_nothing_resolved():
    stats = summarize_cohort([rec(classify_entry_validity(block()), outcome="ACTIVE", ret=None)])
    assert stats["win_rate"] is None
    assert stats["profit_factor"] is None


def test_small_samples_are_flagged_unreliable_rather_than_hidden():
    small = summarize_cohort([rec(classify_entry_validity(block()), ret=1.0)])
    assert small["reliable"] is False
    assert small["win_rate"] == 100.0          # still reported…
    assert small["min_reliable_sample"] == MIN_RELIABLE_SAMPLE   # …with the caveat attached

    big = summarize_cohort(
        [rec(classify_entry_validity(block()), ret=1.0) for _ in range(MIN_RELIABLE_SAMPLE)]
    )
    assert big["reliable"] is True


def test_empty_cohort_never_raises_and_never_fabricates():
    stats = summarize_cohort([])
    assert stats["n"] == 0
    assert stats["win_rate"] is None
    assert stats["profit_factor"] is None
    assert stats["avg_return_pct"] is None
    assert stats["total_return_pct"] is None


# --------------------------------------------------------------------------- #
# 8. the report: integrity, legacy preservation, contamination
# --------------------------------------------------------------------------- #
def _population():
    """Mirrors production's shape: many reached, a phantom cohort with no
    losses at all, and three flavours of unknown."""
    reached = [
        rec(classify_entry_validity(block()), outcome="WIN", ret=2.0, signal_id=f"r{i}")
        for i in range(30)
    ] + [
        rec(classify_entry_validity(block()), outcome="LOSS", ret=-3.0, signal_id=f"l{i}")
        for i in range(20)
    ]
    phantom = [
        rec(classify_entry_validity(never_block()), outcome="WIN", ret=5.0, signal_id=f"p{i}")
        for i in range(10)
    ]
    unknown = [
        rec(classify_entry_validity(None), outcome="WIN", ret=1.0, signal_id="u1"),
        rec(classify_entry_validity(None, has_trade_path=False), outcome="LOSS", ret=-1.0, signal_id="u2"),
        rec(
            classify_entry_validity(block(entry_reached=None, never_entered=None, data_available=False)),
            outcome="ACTIVE", ret=None, signal_id="u3",
        ),
    ]
    return reached + phantom + unknown


def test_cohort_counts_are_exhaustive_and_mutually_exclusive():
    report = compute_entry_validity_report(_population())
    ci = report["cohort_integrity"]
    assert ci["reached"] == 50
    assert ci["not_reached"] == 10
    assert ci["unknown"] == 3
    assert ci["sum"] == ci["total_signals"] == 63
    assert ci["sum_matches_total"] is True


def test_unknown_is_never_folded_into_reached():
    """The mutation: ``status != 'not_reached'`` as the definition of a valid
    entry. That reading counts all three unknowns as fills."""
    pop = _population()
    naive_valid = [r for r in pop if r["entry_validity"]["status"] != ev.STATUS_NOT_REACHED]
    report = compute_entry_validity_report(pop)

    assert len(naive_valid) == 53                                    # wrong reading
    assert report["cohorts"]["valid_entry_only"]["n"] == 50          # ours
    assert report["cohorts"]["unknown"]["n"] == 3


def test_raw_all_is_preserved_verbatim_and_labelled_legacy():
    pop = _population()
    report = compute_entry_validity_report(pop)
    raw = report["cohorts"]["raw_all"]

    assert raw["legacy_raw"] is True
    assert report["cohorts"]["valid_entry_only"]["legacy_raw"] is False
    # raw_all must equal the untouched whole-population aggregate, unmodified.
    baseline = summarize_cohort(pop)
    for key, value in baseline.items():
        assert raw[key] == value, f"raw_all.{key} was rewritten"


def test_the_phantom_cohort_separates_and_its_inflation_is_visible():
    report = compute_entry_validity_report(_population())
    phantom = report["cohorts"]["not_reached"]
    assert phantom["outcomes"]["loss"] == 0
    assert phantom["win_rate"] == 100.0
    assert phantom["profit_factor"] is None          # no losses => undefined
    assert phantom["total_return_pct"] == 50.0       # 10 x 5.0 of pure fiction

    raw, valid = report["cohorts"]["raw_all"], report["cohorts"]["valid_entry_only"]
    assert raw["total_return_pct"] > valid["total_return_pct"]


def test_contamination_is_measured_and_declares_itself_measurement_only():
    report = compute_entry_validity_report(_population())
    c = report["learning_pool_contamination"]
    assert c["measurement_only"] is True
    assert c["not_reached_in_pool"] == 10
    assert c["unknown_in_pool"] == 2                 # the ACTIVE unknown is not terminal
    assert c["contaminated_in_pool"] == 12
    assert c["contaminated_pct"] == pytest.approx(19.35, abs=0.01)
    assert c["effect_on_metrics"]["win_rate_delta"] is not None


def test_status_provenance_accounts_for_every_row():
    pop = _population()
    report = compute_entry_validity_report(pop)
    assert sum(report["status_provenance"]["by_source"].values()) == len(pop)
    assert report["status_provenance"]["unknown_reasons"][ev.UNKNOWN_NO_TRADE_PATH] == 1
    assert report["status_provenance"]["unknown_reasons"][ev.UNKNOWN_NO_ENTRY_BLOCK] == 1
    assert report["status_provenance"]["unknown_reasons"][ev.UNKNOWN_NO_POST_BIRTH_BARS] == 1


def test_breakdowns_exist_per_cohort_and_cover_every_required_dimension():
    report = compute_entry_validity_report(_population())
    required = {
        "by_symbol", "by_timeframe", "by_direction",
        "by_regime", "by_risk_level", "by_confidence_band",
    }
    for cohort in ("raw_all", "valid_entry_only", "not_reached", "unknown"):
        assert required <= set(report["breakdowns"][cohort]), cohort


def test_symbol_breakdown_cap_is_declared_rather_than_silent():
    pop = [
        rec(classify_entry_validity(block()), symbol=f"SYM{i}", signal_id=f"s{i}")
        for i in range(20)
    ]
    report = compute_entry_validity_report(pop, top_symbols=3)
    assert len(report["breakdowns"]["raw_all"]["by_symbol"]) <= 3
    assert "3" in report["breakdown_limits"]["by_symbol"]


def test_report_marks_itself_read_only():
    assert compute_entry_validity_report([])["read_only"] is True


def test_an_unrecognised_status_is_bucketed_as_unknown_not_dropped():
    """Defence in depth: if some future producer emits a fourth status, the
    counts must still add up rather than silently losing rows."""
    rogue = rec({"status": "probably_fine"}, outcome="WIN", ret=99.0)
    report = compute_entry_validity_report([rogue])
    ci = report["cohort_integrity"]
    assert ci["unknown"] == 1
    assert ci["sum_matches_total"] is True
    assert report["cohorts"]["valid_entry_only"]["n"] == 0


# --------------------------------------------------------------------------- #
# 9. additivity — nothing existing is renamed or removed
# --------------------------------------------------------------------------- #
def test_classification_never_mutates_the_input_block():
    original = block()
    snapshot = dict(original)
    classify_entry_validity(original)
    assert original == snapshot


def test_classification_never_raises_on_hostile_input():
    for hostile in (None, "", 0, [], (), {"entry_reached": object()}, {"entry_level": "abc"}):
        out = classify_entry_validity(hostile)
        assert out["status"] in ev.CANONICAL_STATUSES
