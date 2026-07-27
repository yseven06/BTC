"""P2.2-a M1 — the shadow evaluator must not degrade silently.

Two defects with the same shape: the observation tooling kept reporting numbers
while quietly measuring the wrong thing. That is worse than failing outright,
because those numbers are what decide whether the live policy changes.

M1a  A tz-naive frame made the 48h horizon cap raise TypeError, which a blanket
     `except: pass` swallowed — the cap silently did not apply and lifetime
     extrema leaked into the measurement.

M1b  Rows that can NEVER be evaluated (93.6 % of production candidates carry
     engine_direction='neutral') were filtered in the Python loop, so they sat
     at the head of an oldest-first LIMIT query forever, starved every evaluable
     row behind them, and cost one Binance fetch each to re-discover. Excluding
     them in SQL fixes the starvation but leaves them as permanent NULLs, so a
     second bounded pass retires them without fetching anything.
"""
import inspect
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.models.decision_candidate import SHADOW_UNDECIDABLE
from app.services.shadow_eval import evaluate_candidate_shadow

BAR = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
EZ_LOW, EZ_HIGH, SL, TP1, TP2, TP3 = 99.0, 101.0, 97.0, 101.5, 103.0, 105.0


def _frame(rows, *, tz):
    """OHLC frame whose index is genuinely tz-aware or genuinely naive.

    The start timestamp must be naive to get a naive index: pd.date_range built
    from a tz-AWARE start returns a tz-aware index even when tz=None is passed,
    so seeding it with BAR would make the "naive" case silently aware and the
    test would pass without ever exercising the path it names.
    """
    start = BAR if tz else BAR.replace(tzinfo=None)
    idx = pd.date_range(start, periods=len(rows), freq="15min", tz=tz)
    assert (idx.tz is not None) == bool(tz), "fixture failed to build the requested tz-awareness"
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


def _runner():
    """Import the runner script by path — it lives in scripts/, not a package."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "p22a_shadow_eval.py"
    spec = importlib.util.spec_from_file_location("p22a_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── M1 · horizon cap must behave identically for aware and naive frames ─────
@pytest.mark.parametrize("tz", ["UTC", None])
def test_m1_shadow_evaluation_works_for_aware_and_naive_frames(tz):
    """The evaluator is handed frames from a collector whose tz-awareness is not
    guaranteed. A naive frame must produce the same verdict, not a silent
    degradation to 'undecidable'."""
    bars = [
        (101.0, 101.2, 100.8, 101.0),   # scored bar
        (100.0, 100.2, 99.8, 100.0),    # dips to the 100.0 midpoint → filled
        (99.8, 100.0, 96.5, 97.0),      # through SL 97.0
    ]
    out = evaluate_candidate_shadow(
        direction="bullish", entry_zone_low=EZ_LOW, entry_zone_high=EZ_HIGH,
        stop_loss=SL, tp1=TP1, tp2=TP2, tp3=TP3,
        df=_frame(bars, tz=tz), bar_time=BAR)

    assert out["shadow_outcome"] == "stop", f"tz={tz} verdict degraded"
    assert out["shadow_entry_reached"] is True
    assert out["shadow_r_multiple"] == pytest.approx(-1.0, abs=0.02)


def test_m1_horizon_cap_compares_matching_tz_awareness():
    """The runner must align both sides before comparing. The previous code
    compared a tz-aware horizon against a possibly-naive index and swallowed the
    TypeError, so the cap silently did not apply."""
    src = inspect.getsource(_runner().evaluate)

    # No blanket swallow around the cap any more.
    assert "except Exception:  # noqa: BLE001\n                    pass" not in src
    # Both branches are present and the naive branch strips the tz.
    assert "cutoff_ts = horizon.replace(tzinfo=None)" in src
    assert 'if getattr(idx, "tz", None) is None:' in src
    # And a real failure is counted and skipped, not measured around.
    assert "except TypeError" in src
    assert 'stats["horizon_error"]' in src


def test_m1_naive_horizon_comparison_would_have_raised():
    """Pins the underlying pandas behaviour the fix exists for — if a future
    pandas stops raising, this test says so instead of the fix rotting."""
    naive_idx = pd.date_range(BAR.replace(tzinfo=None), periods=3, freq="15min")
    assert naive_idx.tz is None
    aware_horizon = BAR + timedelta(hours=48)
    with pytest.raises(TypeError):
        _ = naive_idx <= aware_horizon
    # Aligned comparison is fine — this is what the fix does.
    assert (naive_idx <= aware_horizon.replace(tzinfo=None)).all()


# ── M1 · permanent vs transient undecidable ────────────────────────────────
def test_m1_permanent_reasons_are_named_and_terminal():
    runner = _runner()
    assert runner.PERMANENT_REASONS == frozenset({"no_direction", "no_geometry"})

    # These are exactly the reasons the evaluator emits for rows that can never
    # become evaluable, so the two definitions must not drift apart.
    neutral = evaluate_candidate_shadow(
        direction="neutral", entry_zone_low=EZ_LOW, entry_zone_high=EZ_HIGH,
        stop_loss=SL, tp1=TP1, tp2=TP2, tp3=TP3, df=_frame([(1, 1, 1, 1)], tz="UTC"),
        bar_time=BAR)
    assert neutral["shadow_resolution_reason"] in runner.PERMANENT_REASONS

    no_geom = evaluate_candidate_shadow(
        direction="bullish", entry_zone_low=None, entry_zone_high=None,
        stop_loss=None, tp1=None, tp2=None, tp3=None,
        df=_frame([(1, 1, 1, 1)], tz="UTC"), bar_time=BAR)
    assert no_geom["shadow_resolution_reason"] in runner.PERMANENT_REASONS


def test_m1_transient_undecidable_is_not_permanent():
    """No post-bar data is absence of evidence — it must stay retryable, not be
    retired as if it had been decided."""
    runner = _runner()
    only_scored_bar = evaluate_candidate_shadow(
        direction="bullish", entry_zone_low=EZ_LOW, entry_zone_high=EZ_HIGH,
        stop_loss=SL, tp1=TP1, tp2=TP2, tp3=TP3,
        df=_frame([(101.0, 101.2, 100.8, 101.0)], tz="UTC"), bar_time=BAR)

    assert only_scored_bar["shadow_outcome"] == SHADOW_UNDECIDABLE
    assert only_scored_bar["shadow_resolution_reason"] == "no_post_bars"
    assert only_scored_bar["shadow_resolution_reason"] not in runner.PERMANENT_REASONS


# ── M1 · the queue cannot be starved ───────────────────────────────────────
def test_m1_query_excludes_unevaluable_rows_at_the_database():
    """93.6 % of production candidates are engine_direction='neutral'. Filtering
    them in the loop instead of in SQL is what let them occupy the head of an
    oldest-first LIMIT query forever — and cost one Binance fetch each."""
    runner = _runner()
    src = inspect.getsource(runner.evaluate)
    assert "evaluable_predicate()" in src
    # The filter must precede the fetch, or the saving is only in the DB.
    assert src.index("evaluable_predicate()") < src.index("_fetch_bars")

    pred = inspect.getsource(runner.evaluable_predicate)
    assert 'engine_direction.in_(("bullish", "bearish"))' in pred
    assert "entry_zone_low.isnot(None)" in pred
    assert "stop_loss.isnot(None)" in pred


def test_m1_stale_rows_are_retired_rather_than_retried_forever():
    runner = _runner()
    # Shortened from 14d: a row still pending at day 14 would be counted as
    # outstanding work at the very moment the observation gate is assessed.
    assert runner.MAX_RETRY_AGE == timedelta(days=7)
    src = inspect.getsource(runner.evaluate)
    assert "too_old" in src
    assert "_finalise_undecidable" in src


def test_m1_retiring_a_row_claims_it_without_claiming_a_result():
    """shadow_evaluated_at is what removes a row from the queue; shadow_outcome
    must stay 'undecidable' so no analysis counts it as a measurement."""
    src = inspect.getsource(_runner()._finalise_undecidable)
    assert '"shadow_evaluated_at"' in src
    assert "SHADOW_UNDECIDABLE" in src
    # Single-claim under a concurrent run.
    assert "shadow_evaluated_at.is_(None)" in src
    # Still routed through the write guard.
    assert "_assert_write_targets" in src


def test_m1_write_guard_still_rejects_decision_columns():
    runner = _runner()
    assert all(c.startswith("shadow_") for c in runner._WRITABLE)
    with pytest.raises(RuntimeError):
        runner._assert_write_targets({"shadow_outcome": "stop", "verdict": "published"})


# ── M1b · the two passes must partition the table, not overlap or leak ─────
def test_m1b_evaluable_and_unevaluable_predicates_partition_the_table():
    """Written out separately rather than derived with NOT(), because SQL
    three-valued logic makes NOT(col IN (...)) evaluate to NULL — not TRUE — when
    col is NULL. A row that belongs to neither half would be invisible to both
    passes and never measured, never retired."""
    runner = _runner()
    ev = str(runner.evaluable_predicate().compile(compile_kwargs={"literal_binds": True}))
    un = str(runner.unevaluable_predicate().compile(compile_kwargs={"literal_binds": True}))

    # Every column the evaluable side requires must appear on the unevaluable side.
    for col in ("engine_direction", "entry_zone_low", "entry_zone_high", "stop_loss"):
        assert col in ev and col in un, f"{col} missing from one half"
    # The unevaluable side must handle NULL direction explicitly.
    assert "engine_direction IS NULL" in un
    # And it must be an OR of failures, not an AND.
    assert " OR " in un and " AND " in ev


def test_m1b_pass_a_retires_permanent_rows_without_fetching_bars():
    """The whole point of pass A: 93.6 % of rows are unevaluable, and paying one
    Binance call each to discover that is both slow and rate-limit risk."""
    runner = _runner()
    src = inspect.getsource(runner.retire_permanent)
    assert "_fetch_bars" not in src, "pass A must never touch the network"
    assert "BinanceCollector" not in src
    # One bounded statement, not a per-row loop.
    assert "for " not in src.split('"""')[2], "pass A must be a batch UPDATE"


def test_m1b_pass_a_is_bounded_and_can_never_be_a_full_table_update():
    src = inspect.getsource(_runner().retire_permanent)
    assert ".limit(limit)" in src, "LIMIT must bound the id sub-select"
    assert "id.in_(ids)" in src, "the UPDATE must be scoped to the bounded id list"
    # Re-running must not re-claim rows.
    assert "shadow_evaluated_at.is_(None)" in src


def test_m1b_pass_a_marks_undecidable_not_a_result():
    src = inspect.getsource(_runner().retire_permanent)
    assert "SHADOW_UNDECIDABLE" in src
    assert "_assert_write_targets" in src
    # The reason is decided in SQL so it cannot disagree with the predicate that
    # selected the row.
    assert "no_direction" in src and "no_geometry" in src


def test_m1b_dry_run_writes_nothing():
    src = inspect.getsource(_runner().retire_permanent)
    body = src.split("if dry_run:")[1]
    # The dry-run arm returns before the UPDATE is ever constructed.
    assert "return len(" in body.split("payload")[0]
    assert "update(" not in body.split("return len(")[0]


def test_m1b_report_mode_performs_no_write():
    runner = _runner()
    rep = inspect.getsource(runner.report)
    for w in ("update(", "insert(", "delete(", "db.commit"):
        assert w not in rep, f"report() must be read-only, found {w!r}"

    main_src = inspect.getsource(runner.main)
    # --report skips both writing passes.
    assert "elif not args.report:" in main_src
    assert "retire_permanent" in main_src.split("elif not args.report:")[1]


def test_m1b_limit_applies_to_each_pass_independently():
    main_src = inspect.getsource(_runner().main)
    assert "retire_permanent(db, args.limit)" in main_src
    assert "evaluate(args.limit)" in main_src


def test_m1b_pending_count_separates_evaluable_from_permanently_unevaluable():
    """Before pass A runs, a raw `shadow_evaluated_at IS NULL` count overstates
    the gate's remaining work by more than an order of magnitude."""
    rep = inspect.getsource(_runner().report)
    assert "pending_evaluable" in rep
    assert "kalici degerlendirilemez" in rep


def test_m1b_retry_window_retires_before_the_observation_gate():
    """MAX_RETRY_AGE must be comfortably shorter than the 14-day gate, or a row
    can still be pending at the moment the gate is assessed."""
    runner = _runner()
    assert runner.MAX_RETRY_AGE < timedelta(days=14)
    assert runner.MAX_RETRY_AGE >= timedelta(days=2), "must exceed the 48h eligibility age"
