"""CP-SHADOW-PASSB-A — the fetch window belongs to the candidate, not to `now`.

The runner used to ask the exchange for `limit=300` most-recent bars. At 15m that
is 3d3h, so a 15m candidate older than that could never be covered again and was
retired unmeasured — and 685 of the 979 evaluable rows are 15m. Everything here
is about pinning the window to `evaluated_bar_time` instead, and about keeping
"no bars yet" separate from "no bars ever".

Nothing in this checkpoint writes. The dry-run tests assert exactly that.
"""
from __future__ import annotations

import ast
import importlib.util
import inspect
import pathlib
import sys
import textwrap
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from app.models.decision_candidate import (SHADOW_PERMANENT_REASONS,
                                           SHADOW_REASON_DATA_UNAVAILABLE,
                                           SHADOW_TERMINAL_REASONS,
                                           SHADOW_UNDECIDABLE)
from app.services.candle_window import TIMEFRAME_DURATIONS
from app.services.shadow_eval import (EXCHANGE_MAX_LIMIT, SHADOW_EXECUTION_MODEL,
                                      SHADOW_FETCH_SAFETY_BARS, SHADOW_HORIZON,
                                      SHADOW_PASSB_VERSION, clip_to_window,
                                      evaluate_candidate_shadow, historical_window,
                                      shadow_passb_provenance)

BACKEND = pathlib.Path(__file__).resolve().parent.parent
UTC = timezone.utc
BAR_TIME = datetime(2026, 7, 27, 16, 30, tzinfo=UTC)


def _load_runner():
    """Import the runner by path — scripts/ is not a package."""
    path = BACKEND / "scripts" / "p22a_shadow_eval.py"
    spec = importlib.util.spec_from_file_location("p22a_shadow_eval_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


runner = _load_runner()


def frame(start: datetime, n: int, timeframe: str, *, tz=UTC, step=None):
    dur = step or TIMEFRAME_DURATIONS[timeframe]
    idx = pd.DatetimeIndex([start + i * dur for i in range(n)])
    if tz is None:
        idx = idx.tz_localize(None)
    return pd.DataFrame({
        "open": np.full(n, 100.0), "high": np.full(n, 101.0),
        "low": np.full(n, 99.0), "close": np.full(n, 100.0),
        "volume": np.full(n, 1000.0),
    }, index=idx)


# ------------------------------------------------------ 1-2, 5: the window
@pytest.mark.parametrize("timeframe,expected_limit", [
    ("15m", 212), ("1h", 68), ("4h", 32), ("1d", 22),
])
def test_the_limit_is_derived_from_the_timeframe(timeframe, expected_limit):
    start, end, limit = historical_window(BAR_TIME, timeframe)
    assert start == BAR_TIME
    assert end == BAR_TIME + SHADOW_HORIZON
    assert limit == expected_limit
    # ...and it really is derived, not four constants that happen to match.
    dur = TIMEFRAME_DURATIONS[timeframe]
    assert limit == -(-SHADOW_HORIZON // dur) + SHADOW_FETCH_SAFETY_BARS


def test_no_single_constant_covers_every_timeframe():
    limits = {tf: historical_window(BAR_TIME, tf)[2] for tf in ("15m", "1h", "4h", "1d")}
    assert len(set(limits.values())) == 4, limits
    assert all(v <= EXCHANGE_MAX_LIMIT for v in limits.values())


def test_the_window_follows_the_candidate_not_the_clock():
    """Two candidates on the same symbol, months apart, must get different windows."""
    old = historical_window(datetime(2025, 1, 13, 2, 45, tzinfo=UTC), "15m")
    new = historical_window(BAR_TIME, "15m")
    assert old[1] != new[1]
    assert old[2] == new[2] == 212       # same shape, different anchor


def test_an_unknown_timeframe_is_refused_rather_than_guessed():
    with pytest.raises(ValueError):
        historical_window(BAR_TIME, "30m")


@pytest.mark.asyncio
async def test_the_fetch_passes_end_time_ms_for_the_candidates_own_window():
    seen = {}

    class Collector:
        async def fetch_ohlcv(self, symbol, timeframe, limit=100, end_time_ms=None):
            seen.update(symbol=symbol, timeframe=timeframe, limit=limit,
                        end_time_ms=end_time_ms)
            return frame(BAR_TIME, 10, timeframe)

    df, requested, failed = await runner._fetch_bars(
        Collector(), "BTCUSDT", "15m", BAR_TIME)
    assert failed is False
    assert requested == 212
    assert seen["limit"] == 212
    assert seen["end_time_ms"] is not None
    assert seen["end_time_ms"] == int((BAR_TIME + SHADOW_HORIZON).timestamp() * 1000)


@pytest.mark.asyncio
async def test_a_very_old_candidate_still_gets_its_own_end_time():
    ancient = datetime(2024, 9, 10, 2, 45, tzinfo=UTC)
    seen = {}

    class Collector:
        async def fetch_ohlcv(self, symbol, timeframe, limit=100, end_time_ms=None):
            seen["end_time_ms"] = end_time_ms
            return frame(ancient, 5, timeframe)

    await runner._fetch_bars(Collector(), "MATICUSDT", "15m", ancient)
    assert seen["end_time_ms"] == int((ancient + SHADOW_HORIZON).timestamp() * 1000)
    # And it is in the past, not "now".
    assert seen["end_time_ms"] < datetime.now(UTC).timestamp() * 1000


@pytest.mark.asyncio
async def test_a_failed_fetch_is_reported_as_failure_not_as_emptiness():
    class Broken:
        async def fetch_ohlcv(self, *a, **kw):
            raise RuntimeError("boom")

    df, requested, failed = await runner._fetch_bars(Broken(), "BTCUSDT", "15m", BAR_TIME)
    assert df is None and failed is True and requested == 212


# ------------------------------------------- 3-4, 20: causality of the clip
def test_the_decision_bar_itself_is_never_walked():
    df = frame(BAR_TIME - timedelta(hours=1), 20, "15m")
    out = clip_to_window(df, BAR_TIME, "15m")
    assert len(out) > 0
    assert (out.index > BAR_TIME).all()
    assert BAR_TIME not in out.index


def test_bars_before_the_decision_are_excluded():
    df = frame(BAR_TIME - timedelta(days=5), 600, "15m")
    out = clip_to_window(df, BAR_TIME, "15m")
    assert out.index.min() > BAR_TIME


def test_bars_after_the_horizon_are_excluded():
    df = frame(BAR_TIME, 400, "15m")        # 100 hours of bars
    out = clip_to_window(df, BAR_TIME, "15m")
    assert out.index.max() <= BAR_TIME + SHADOW_HORIZON
    assert len(out) == 192                  # exactly 48h of 15m bars, decision bar dropped


def test_todays_market_cannot_leak_into_a_historical_candidates_window():
    """A frame that spans from an old candidate all the way to now must be cut
    back to that candidate's own 48 hours."""
    ancient = datetime(2025, 1, 13, 2, 45, tzinfo=UTC)
    df = frame(ancient, 900, "1d")          # runs well past the present
    out = clip_to_window(df, ancient, "1d")
    assert out.index.max() <= ancient + SHADOW_HORIZON
    assert out.index.max() < datetime.now(UTC) - timedelta(days=300)
    assert len(out) == 2


# --------------------------------------------------- 6-7: frame normalisation
def test_a_descending_frame_is_normalised_before_use():
    df = frame(BAR_TIME, 100, "15m").iloc[::-1]
    assert not df.index.is_monotonic_increasing
    out = clip_to_window(df, BAR_TIME, "15m")
    assert out.index.is_monotonic_increasing


def test_duplicate_bars_are_not_walked_twice():
    df = frame(BAR_TIME, 50, "15m")
    df = pd.concat([df, df.iloc[10:20]]).sort_index()
    out = clip_to_window(df, BAR_TIME, "15m")
    assert not out.index.duplicated().any()
    assert len(out) == 49                   # 50 bars minus the decision bar itself


def test_a_tz_naive_frame_is_handled_without_raising():
    df = frame(BAR_TIME, 100, "15m", tz=None)
    out = clip_to_window(df, BAR_TIME, "15m")
    assert len(out) > 0
    assert out.index.max() <= (BAR_TIME + SHADOW_HORIZON).replace(tzinfo=None)


# -------------------------------- 8-11: undecidable vs data_unavailable
def test_a_candidate_younger_than_the_horizon_is_not_yet_judgeable():
    now = datetime.now(UTC)
    assert runner._window_is_complete(now - timedelta(hours=47), now) is False
    assert runner._window_is_complete(now - timedelta(hours=48), now) is True


def test_an_exchange_that_answers_with_nothing_in_the_window_is_permanent():
    ancient = datetime(2025, 1, 13, 2, 45, tzinfo=UTC)
    stale = frame(ancient - timedelta(days=30), 20, "15m")     # ends before the window
    assert runner._exchange_has_nothing(stale, ancient, "15m") is True


def test_an_exchange_with_data_in_the_window_is_not_permanent():
    covering = frame(BAR_TIME, 100, "15m")
    assert runner._exchange_has_nothing(covering, BAR_TIME, "15m") is False


def test_no_answer_at_all_is_never_treated_as_proof_of_absence():
    assert runner._exchange_has_nothing(None, BAR_TIME, "15m") is False
    assert runner._exchange_has_nothing(frame(BAR_TIME, 0, "15m"), BAR_TIME, "15m") is False


def test_data_unavailable_is_a_distinct_terminal_reason():
    assert SHADOW_REASON_DATA_UNAVAILABLE == "data_unavailable"
    assert SHADOW_REASON_DATA_UNAVAILABLE in SHADOW_TERMINAL_REASONS
    # It is terminal, but it is NOT one of the row-shape reasons — those are
    # decidable at birth, this one needs the exchange to answer first.
    assert SHADOW_REASON_DATA_UNAVAILABLE not in SHADOW_PERMANENT_REASONS
    assert SHADOW_PERMANENT_REASONS < SHADOW_TERMINAL_REASONS


def test_data_unavailable_cannot_be_silently_folded_into_undecidable():
    """The outcome column stays `undecidable` — there is genuinely no outcome —
    but the reason must still tell the two apart."""
    src = textwrap.dedent(inspect.getsource(runner.evaluate))
    tree = ast.parse(src)

    # Every reason that reaches the row must come from a named constant or be one
    # of the explicitly transient labels — never a re-typed copy of the terminal
    # string, which is how the two would drift back together.
    reasons = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "_finalise_undecidable":
            reasons.append(node.args[2])
    assert reasons, "the retire path disappeared"
    literals = [r.value for r in reasons if isinstance(r, ast.Constant)]
    names = [r.id for r in reasons if isinstance(r, ast.Name)]
    assert "SHADOW_REASON_DATA_UNAVAILABLE" in names
    assert SHADOW_REASON_DATA_UNAVAILABLE not in literals, (
        "the terminal reason must come from the constant, not a duplicated literal")
    # The transient siblings stay distinguishable from it.
    assert "no_bars_after_retry_window" in literals
    assert "no_bars_in_horizon" in literals


# --------------------------------------- 12-13: walk semantics unchanged
def _levels(direction="bullish"):
    return dict(direction=direction, entry_zone_low=99.0, entry_zone_high=101.0,
                stop_loss=95.0, tp1=105.0, tp2=110.0, tp3=115.0)


def _walk_frame(rows):
    idx = pd.DatetimeIndex([BAR_TIME + (i + 1) * TIMEFRAME_DURATIONS["15m"]
                            for i in range(len(rows))])
    return pd.DataFrame(rows, index=idx,
                        columns=["open", "high", "low", "close"]).assign(volume=1000.0)


def test_a_bar_touching_both_tp_and_sl_stays_conservative_and_is_flagged():
    # One bar that reaches the entry, the TP and the stop. Conservative wins.
    out = evaluate_candidate_shadow(
        **_levels(), df=_walk_frame([[100.0, 106.0, 94.0, 100.0]]), bar_time=BAR_TIME)
    assert out["shadow_outcome"] == "stop"
    assert out["intrabar_ambiguous"] is True
    assert SHADOW_EXECUTION_MODEL == "conservative"


def test_a_clean_walk_reports_no_ambiguity():
    out = evaluate_candidate_shadow(
        **_levels(), df=_walk_frame([[100.0, 100.5, 99.5, 100.0],
                                     [100.0, 106.0, 99.8, 105.5]]), bar_time=BAR_TIME)
    assert out["intrabar_ambiguous"] is False
    assert out["shadow_outcome"] in ("tp1", "tp2", "tp3")


def test_a_setup_that_never_filled_is_not_a_loss():
    # Price runs away upward without ever coming back to the entry midpoint.
    out = evaluate_candidate_shadow(
        **_levels(), df=_walk_frame([[120.0, 125.0, 119.0, 124.0],
                                     [124.0, 130.0, 123.0, 129.0]]), bar_time=BAR_TIME)
    assert out["shadow_outcome"] == "never_entered"
    assert out["shadow_resolution_path"] == "no_fill"
    assert out["shadow_outcome"] != "stop"
    assert out["shadow_bars_walked"] == 0
    assert out["intrabar_ambiguous"] is None      # no walk ran


def test_missing_geometry_is_refused_rather_than_invented():
    for missing in ("entry_zone_low", "stop_loss"):
        lv = _levels()
        lv[missing] = None
        out = evaluate_candidate_shadow(**lv, df=_walk_frame([[100.0, 101.0, 99.0, 100.0]]),
                                        bar_time=BAR_TIME)
        assert out["shadow_outcome"] == SHADOW_UNDECIDABLE
        assert out["shadow_resolution_reason"] == "no_geometry"
    lv = _levels(direction="neutral")
    out = evaluate_candidate_shadow(**lv, df=_walk_frame([[100.0, 101.0, 99.0, 100.0]]),
                                    bar_time=BAR_TIME)
    assert out["shadow_resolution_reason"] == "no_direction"


def test_the_walk_result_is_identical_for_identical_bars():
    bars = _walk_frame([[100.0, 100.5, 99.5, 100.0], [100.0, 106.0, 99.8, 105.5]])
    a = evaluate_candidate_shadow(**_levels(), df=bars, bar_time=BAR_TIME)
    b = evaluate_candidate_shadow(**_levels(), df=bars.copy(), bar_time=BAR_TIME)
    assert a == b


# ------------------------------------------------------- 14: provenance
def test_the_provenance_records_the_window_that_was_asked_for():
    df = clip_to_window(frame(BAR_TIME, 300, "15m"), BAR_TIME, "15m")
    prov = shadow_passb_provenance(bar_time=BAR_TIME, timeframe="15m",
                                   requested_limit=212, df=df, dry_run=True,
                                   intrabar_ambiguous=False)
    assert prov["policy_version"] == SHADOW_PASSB_VERSION
    assert prov["execution_model"] == "conservative"
    assert prov["horizon_hours"] == 48.0
    assert prov["requested_limit"] == 212
    assert prov["actual_bar_count"] == len(df)
    assert prov["dry_run"] is True
    assert prov["intrabar_ambiguous"] is False
    assert prov["candidate_evaluated_bar_time"] == BAR_TIME.isoformat()
    assert prov["fetch_window_start"] == BAR_TIME.isoformat()
    assert prov["fetch_window_end"] == (BAR_TIME + SHADOW_HORIZON).isoformat()
    assert prov["first_bar_time"] > prov["fetch_window_start"]
    assert prov["last_bar_time"] <= prov["fetch_window_end"]
    # Timestamps carry their zone.
    for k in ("fetch_window_start", "fetch_window_end", "first_bar_time", "last_bar_time"):
        assert prov[k].endswith("+00:00"), (k, prov[k])


def test_the_provenance_carries_no_credential_or_message():
    prov = shadow_passb_provenance(bar_time=BAR_TIME, timeframe="1h",
                                   requested_limit=68, df=None, dry_run=True)
    import json as _json
    blob = _json.dumps(prov)
    for needle in ("postgres", "://", "token", "password", "Traceback", "http"):
        assert needle not in blob, needle
    assert prov["actual_bar_count"] == 0
    assert prov["first_bar_time"] is None


def _compiled(expr):
    """SQL text plus its bind values. JSONB has no literal renderer, so the
    payload has to be read from the params rather than inlined."""
    from sqlalchemy.dialects import postgresql
    c = expr.compile(dialect=postgresql.dialect())
    return str(c), c.params


def test_the_extra_write_is_a_merge_not_an_assignment():
    """Compiled SQL must concatenate onto the existing column, never replace it."""
    sql, params = _compiled(runner.extra_merge_expression({"policy_version": "x"}))
    assert "signal_decision_candidates.extra" in sql
    assert "||" in sql or "concat" in sql.lower()
    assert "jsonb_build_object" in sql
    assert "coalesce" in sql.lower()          # a NULL extra becomes {}, not NULL
    assert "shadow_passb" in list(params.values())


def test_the_provenance_key_is_namespaced_and_singular():
    prov = shadow_passb_provenance(bar_time=BAR_TIME, timeframe="1h",
                                   requested_limit=68, df=None, dry_run=True)
    sql, params = _compiled(runner.extra_merge_expression(prov))
    keys = [v for v in params.values() if isinstance(v, str)]
    assert "shadow_passb" in keys
    # Exactly one key is added, and the protected ones are never named — so this
    # statement cannot target them even by accident.
    blob = sql + "".join(str(v) for v in params.values())
    for protected in ("adaptive_state_telemetry", "engine_execution_telemetry",
                      "decision_input_version", "primary_demotion_reason"):
        assert protected not in blob, protected


# ---------------------------------------------- 15-16: the dry-run gate
class _RecordingDB:
    def __init__(self):
        self.executed = []
        self.committed = 0
        self.rolled_back = 0

    async def execute(self, stmt, *a, **kw):
        self.executed.append(stmt)
        raise AssertionError("dry-run must not execute a statement here")

    async def commit(self):
        self.committed += 1

    async def rollback(self):
        self.rolled_back += 1


@pytest.mark.asyncio
async def test_finalise_writes_nothing_in_dry_run():
    db = _RecordingDB()
    cand = type("C", (), {"id": "abc"})()
    await runner._finalise_undecidable(db, cand, SHADOW_REASON_DATA_UNAVAILABLE,
                                       dry_run=True)
    assert db.executed == []


@pytest.mark.asyncio
async def test_finalise_still_writes_when_asked_to():
    class Exec(_RecordingDB):
        async def execute(self, stmt, *a, **kw):
            self.executed.append(stmt)

    db = Exec()
    cand = type("C", (), {"id": "abc"})()
    await runner._finalise_undecidable(db, cand, SHADOW_REASON_DATA_UNAVAILABLE,
                                       dry_run=False)
    assert len(db.executed) == 1


def test_dry_run_is_the_default_and_writing_is_opt_in():
    src = textwrap.dedent(inspect.getsource(runner.main))
    tree = ast.parse(src)
    flags = {n.args[0].value for n in ast.walk(tree)
             if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "add_argument"
             and n.args and isinstance(n.args[0], ast.Constant)}
    assert "--write" in flags, "the write path must be opt-in by name"
    # dry_run is the inverse of --write, so no flag at all means no write.
    assert "dry_run = not args.write" in src

    # ...and both pass entry points default to dry_run=True.
    assert inspect.signature(runner.evaluate).parameters["dry_run"].default is True
    assert inspect.signature(runner._finalise_undecidable).parameters["dry_run"].default is True
    assert inspect.signature(runner.retire_permanent).parameters["dry_run"].default is False


class _Candidate:
    """Just the attributes evaluate() reads off a row."""
    def __init__(self, bar_time):
        self.id = "cand-1"
        self.symbol = "BTCUSDT"
        self.timeframe = "15m"
        self.evaluated_bar_time = bar_time
        self.engine_direction = "bullish"
        self.entry_zone_low = 99.0
        self.entry_zone_high = 101.0
        self.stop_loss = 95.0
        self.tp1, self.tp2, self.tp3 = 105.0, 110.0, 115.0


class _SelectResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_pass_b_issues_no_update_in_dry_run(monkeypatch):
    """End-to-end through evaluate(): a candidate that RESOLVES — the branch that
    actually has an UPDATE to suppress — must still write nothing.

    The earlier dry-run tests only covered _finalise_undecidable, which left the
    resolved-row write path unguarded by any test.
    """
    old = datetime.now(UTC) - timedelta(days=5)
    old = old.replace(minute=0, second=0, microsecond=0)
    cand = _Candidate(old)

    class DB:
        def __init__(self):
            self.statements = []
            self.commits = 0
            self.rollbacks = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, stmt, *a, **kw):
            self.statements.append(stmt)
            return _SelectResult([cand])

        async def commit(self):
            self.commits += 1

        async def rollback(self):
            self.rollbacks += 1

    db = DB()

    class Collector:
        async def fetch_ohlcv(self, symbol, timeframe, limit=100, end_time_ms=None):
            # Enters at the midpoint on bar 1, then runs to TP1 — a resolved walk.
            rows = [[100.0, 100.5, 99.5, 100.0]] + [[100.0, 106.0, 99.8, 105.5]] * 3
            idx = pd.DatetimeIndex([old + (i + 1) * TIMEFRAME_DURATIONS["15m"]
                                    for i in range(len(rows))])
            return pd.DataFrame(rows, index=idx,
                                columns=["open", "high", "low", "close"]).assign(volume=1.0)

        async def close(self):
            pass

    monkeypatch.setattr(runner, "async_session_factory", lambda: db)
    monkeypatch.setattr(runner, "BinanceCollector", Collector)

    stats = await runner.evaluate(10, dry_run=True)

    # The candidate really did resolve — otherwise the write branch was never
    # reached and this test would pass vacuously.
    assert sum(stats[k] for k in ("tp1", "tp2", "tp3", "stop", "expiry")) == 1, dict(stats)
    assert db.commits == 0
    assert db.rollbacks == 1
    for stmt in db.statements:
        assert str(stmt).strip().upper().startswith("SELECT"), str(stmt)[:100]


@pytest.mark.asyncio
async def test_pass_b_does_issue_the_update_when_writing(monkeypatch):
    """Teeth for the test above: with dry_run=False the same run MUST update, or
    the dry-run assertion proves nothing."""
    old = (datetime.now(UTC) - timedelta(days=5)).replace(minute=0, second=0, microsecond=0)
    cand = _Candidate(old)

    class DB:
        def __init__(self):
            self.statements = []
            self.commits = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, stmt, *a, **kw):
            self.statements.append(stmt)
            return _SelectResult([cand])

        async def commit(self):
            self.commits += 1

        async def rollback(self):
            raise AssertionError("write mode must commit, not roll back")

    db = DB()

    class Collector:
        async def fetch_ohlcv(self, symbol, timeframe, limit=100, end_time_ms=None):
            rows = [[100.0, 100.5, 99.5, 100.0]] + [[100.0, 106.0, 99.8, 105.5]] * 3
            idx = pd.DatetimeIndex([old + (i + 1) * TIMEFRAME_DURATIONS["15m"]
                                    for i in range(len(rows))])
            return pd.DataFrame(rows, index=idx,
                                columns=["open", "high", "low", "close"]).assign(volume=1.0)

        async def close(self):
            pass

    monkeypatch.setattr(runner, "async_session_factory", lambda: db)
    monkeypatch.setattr(runner, "BinanceCollector", Collector)

    await runner.evaluate(10, dry_run=False)

    updates = [s for s in db.statements if str(s).strip().upper().startswith("UPDATE")]
    assert len(updates) == 1
    assert db.commits == 1

    # The provenance must actually reach the statement — an UPDATE that writes
    # only the shadow_* columns would satisfy every other assertion here.
    from sqlalchemy.dialects import postgresql
    compiled = updates[0].compile(dialect=postgresql.dialect())
    touched = {c.name for c in updates[0]._values}
    assert "extra" in touched, touched
    assert touched - {"extra"} <= runner._WRITABLE, touched
    payload = "".join(str(v) for v in compiled.params.values())
    for key in ("policy_version", "fetch_window_start", "fetch_window_end",
                "requested_limit", "actual_bar_count", "execution_model",
                "candidate_evaluated_bar_time", "shadow_passb"):
        assert key in payload, key


def test_the_write_guard_covers_every_column_of_the_update():
    """`extra` is the widest column the statement touches. If the guard only ever
    sees the shadow_* payload, a sibling keyword argument can add a decision
    column past it — which is exactly what it exists to prevent."""
    # Bare payload: extra is not admitted unless asked for.
    with pytest.raises(RuntimeError):
        runner._assert_write_targets({"shadow_outcome": "stop", "extra": {}})
    # Admitted explicitly, and nothing else rides along with it.
    runner._assert_write_targets({"shadow_outcome": "stop", "extra": {}}, allow_extra=True)
    with pytest.raises(RuntimeError):
        runner._assert_write_targets(
            {"shadow_outcome": "stop", "extra": {}, "verdict": "published"},
            allow_extra=True)
    assert runner._WRITABLE_EXTRA == {"extra"}
    assert "extra" not in runner._WRITABLE

    # And the call site really does assert the full value set, not just payload.
    src = textwrap.dedent(inspect.getsource(runner.evaluate))
    assert "values = {**payload, \"extra\": extra_merge_expression(prov)}" in src
    assert "_assert_write_targets(values, allow_extra=True)" in src
    assert ".values(**values)" in src


@pytest.mark.asyncio
async def test_an_unsupported_timeframe_fails_one_row_not_the_batch():
    """historical_window raises for an unknown timeframe. The whole pass runs in
    one transaction, so letting that escape would discard every verdict already
    computed in the run."""
    class Collector:
        async def fetch_ohlcv(self, *a, **kw):
            raise AssertionError("must not reach the network for a bad timeframe")

    df, requested, failed = await runner._fetch_bars(
        Collector(), "BTCUSDT", "30m", BAR_TIME)
    assert df is None and failed is True and requested == 0


def test_the_maturity_gate_and_the_walk_horizon_are_the_same_48_hours():
    """A shorter MIN_AGE would queue candidates whose window has not finished,
    and every one of them would be judged on a truncated walk."""
    assert runner.MIN_AGE == SHADOW_HORIZON == timedelta(hours=48)
    src = textwrap.dedent(inspect.getsource(runner))
    assert "MIN_AGE = SHADOW_HORIZON" in src, (
        "MIN_AGE must be bound to the shadow horizon, not restated")
    # The retry window still sits between the horizon and the observation gate.
    assert SHADOW_HORIZON < runner.MAX_RETRY_AGE < timedelta(days=14)


def test_the_write_allowlist_was_not_widened():
    assert runner._WRITABLE == {
        "shadow_evaluated_at", "shadow_outcome", "shadow_detail_label",
        "shadow_return_pct", "shadow_r_multiple", "shadow_mfe_pct", "shadow_mae_pct",
        "shadow_bars_walked", "shadow_resolved_at", "shadow_resolution_path",
        "shadow_resolution_reason", "shadow_entry_reached", "shadow_entry_reached_at",
        "shadow_bars_to_entry", "shadow_never_entered", "shadow_max_zone_penetration_pct",
        "shadow_zone_far_edge_reached", "shadow_stop_before_valid_entry",
        "shadow_invalidated_before_entry",
    }
    with pytest.raises(RuntimeError):
        runner._assert_write_targets({"verdict": "published"})
    # intrabar_ambiguous is telemetry, not a column — it must be filtered out.
    assert "intrabar_ambiguous" not in runner._WRITABLE


# ------------------------------------- 17-19: nothing else moved
def test_the_evaluator_maths_is_untouched():
    from app.backtesting import resolution_core
    src = inspect.getsource(resolution_core)
    assert "def resolve_trade_path" in src
    assert 'execution_model: str = "conservative"' in src
    # shadow_eval must call it, not reimplement it.
    shadow_src = inspect.getsource(__import__("app.services.shadow_eval",
                                              fromlist=["x"]))
    assert "resolve_trade_path(" in shadow_src
    assert shadow_src.count("def _first_touch") == 1


def test_the_decision_path_contracts_are_unchanged():
    from app.engines.ai_decision.signal_generator import (BASE_ENGINE_WEIGHTS,
                                                          CONSENSUS_VOTE_ENGINES,
                                                          DECISION_INPUT_VERSION,
                                                          REQUIRED_CONSENSUS_VOTES)
    from app.models.decision_candidate import (CANDIDATE_POLICY_VERSION,
                                               CANDIDATE_SCHEMA_VERSION)
    assert len(CONSENSUS_VOTE_ENGINES) == 5
    assert REQUIRED_CONSENSUS_VOTES == 4
    assert len(BASE_ENGINE_WEIGHTS) == 9
    assert DECISION_INPUT_VERSION == "closed_candle_v1"
    assert (CANDIDATE_SCHEMA_VERSION, CANDIDATE_POLICY_VERSION) == (1, 1)


def test_no_geometry_is_ever_invented_for_a_hold_candidate():
    """dropped/not_actionable rows have no entry/SL. The predicate must exclude
    them, and the evaluator must refuse them — neither may substitute a default."""
    from app.models.decision_candidate import classify_birth_shadow
    assert classify_birth_shadow("neutral", None, None, None) == "no_direction"
    assert classify_birth_shadow("bullish", None, None, None) == "no_geometry"
    assert classify_birth_shadow("bullish", 99.0, 101.0, 95.0) is None

    src = textwrap.dedent(inspect.getsource(runner.evaluable_predicate))
    assert "entry_zone_low.isnot(None)" in src
    assert "stop_loss.isnot(None)" in src


def test_this_checkpoint_adds_no_migration():
    migrations = sorted(p.name for p in (BACKEND / "migrations").glob("*.sql"))
    assert migrations[-1] == "0010_candidate_log_rls.sql", migrations[-1]


def test_the_horizon_matches_the_signal_expiry_the_product_actually_stamps():
    """48h lives in two places by necessity — the shadow window and the signal's
    expires_at. A drift between them would silently measure a different trade
    than the one the platform published."""
    src = (BACKEND / "app" / "api" / "routes" / "signals.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    found = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "timedelta"
                and node.keywords and node.keywords[0].arg == "hours"):
            found.append(node.keywords[0].value.value)
    assert 48 in found, "signals.py no longer stamps a 48h expiry"
    assert SHADOW_HORIZON == timedelta(hours=48)
