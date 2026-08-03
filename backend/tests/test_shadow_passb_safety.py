"""CP-SHADOW-PASSB-B-SAFETY — the three gates that must hold before Pass B writes.

BLOCKER 1  The walk used to start ON the entry bar. The fill instant is that
           bar's low (long) or high (short); the take profits are tested against
           the same bar's opposite extreme. OHLC has no intra-bar ordering, so a
           TP could be credited to movement that preceded the fill — and only in
           the profitable direction, because a stop on the entry bar is causally
           forced while a take profit is not.

BLOCKER 2  A window the exchange only partly covered still produced `expiry` and
           `never_entered`, both of which are claims about the bars that are
           MISSING.

BLOCKER 3  A transient 429/timeout on a row older than the retry age was promoted
           into a permanent, irreversible retirement — recording "there is nothing
           to find" when the truth was "we could not look".

Nothing here writes. The dry-run assertions are repeated because the whole point
of the checkpoint is that they still hold.
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
                                           SHADOW_REASON_INCOMPLETE_WINDOW,
                                           SHADOW_REASON_TRANSIENT_FETCH,
                                           SHADOW_RETRYABLE_REASONS,
                                           SHADOW_TERMINAL_REASONS,
                                           SHADOW_UNDECIDABLE)
from app.services.candle_window import TIMEFRAME_DURATIONS
# CP-ENTRY-ACTIVATION-GATE: `_walk_start` was PROMOTED out of shadow_eval into
# the shared entry_activation module so the live tracker and the shadow
# evaluator consume ONE implementation. Imported under the old local name so
# the behavioural assertions below keep testing the same function.
from app.services.entry_activation import walk_start as _walk_start
from app.services.shadow_eval import (SHADOW_HORIZON,
                                      evaluate_candidate_shadow,
                                      expected_horizon_bars,
                                      shadow_passb_provenance,
                                      window_is_complete)

BACKEND = pathlib.Path(__file__).resolve().parent.parent
UTC = timezone.utc
BAR = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def _load_runner():
    path = BACKEND / "scripts" / "p22a_shadow_eval.py"
    spec = importlib.util.spec_from_file_location("p22a_safety_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


runner = _load_runner()

LONG = dict(direction="bullish", entry_zone_low=99.0, entry_zone_high=101.0,
            stop_loss=95.0, tp1=105.0, tp2=110.0, tp3=115.0)          # mid 100
SHORT = dict(direction="bearish", entry_zone_low=99.0, entry_zone_high=101.0,
             stop_loss=105.0, tp1=95.0, tp2=90.0, tp3=85.0)           # mid 100


def bars(rows, timeframe="15m", n_pad=0):
    """Rows are (o, h, l, c) starting on the first post-decision bar."""
    rows = list(rows) + [[100.0, 100.1, 99.9, 100.0]] * n_pad
    idx = pd.DatetimeIndex([BAR + (i + 1) * TIMEFRAME_DURATIONS[timeframe]
                            for i in range(len(rows))])
    return pd.DataFrame(rows, index=idx,
                        columns=["open", "high", "low", "close"]).assign(volume=1000.0)


def full(rows, timeframe="15m"):
    """Pad to a complete 48h window so the blocker-2 gate is satisfied."""
    need = expected_horizon_bars(timeframe)
    return bars(rows, timeframe, n_pad=max(0, need - len(rows)))


# ══════════════════════════ BLOCKER 1 · entry-bar causality ══════════════════
def test_long_entry_bar_high_before_the_fill_is_not_a_take_profit():
    """The bar opens ABOVE the entry, spikes through TP1, then wicks down into
    the entry. Whether the spike preceded the fill is unknowable, so it may not
    be booked."""
    out = evaluate_candidate_shadow(**LONG, timeframe="15m", bar_time=BAR,
                                    df=full([[106.0, 116.0, 99.9, 100.2]]))
    assert out["entry_bar_walked"] is False
    assert out["entry_bar_tp_withheld"] is True
    assert out["shadow_outcome"] not in ("tp1", "tp2", "tp3"), out["shadow_outcome"]


def test_short_entry_bar_low_before_the_fill_is_not_a_take_profit():
    """Mirror of the long case: opens BELOW the entry, dips through TP1, then
    rallies into the entry."""
    out = evaluate_candidate_shadow(**SHORT, timeframe="15m", bar_time=BAR,
                                    df=full([[94.0, 100.1, 84.0, 99.8]]))
    assert out["entry_bar_walked"] is False
    assert out["entry_bar_tp_withheld"] is True
    assert out["shadow_outcome"] not in ("tp1", "tp2", "tp3"), out["shadow_outcome"]


@pytest.mark.parametrize("levels,bar", [
    (LONG, [99.0, 116.0, 98.0, 100.0]),     # opened at/below the entry
    (SHORT, [101.0, 102.0, 84.0, 100.0]),   # opened at/above the entry
])
def test_a_fill_certain_at_the_open_makes_the_whole_entry_bar_sound(levels, bar):
    """Exception 1, proved not assumed: if price was already through the entry at
    the first tick, the fill IS the open and everything after it is post-fill."""
    out = evaluate_candidate_shadow(**levels, timeframe="15m", bar_time=BAR,
                                    df=full([bar]))
    assert out["entry_bar_walked"] is True
    assert out["entry_bar_tp_withheld"] is False
    assert out["shadow_outcome"] in ("tp1", "tp2", "tp3"), out["shadow_outcome"]


@pytest.mark.parametrize("levels,bar", [
    (LONG, [106.0, 107.0, 94.0, 95.0]),     # sl 95 below mid 100
    (SHORT, [94.0, 106.0, 93.0, 105.0]),    # sl 105 above mid 100
])
def test_a_stop_on_the_entry_bar_is_causally_forced_and_is_booked(levels, bar):
    """Exception 2. The stop sits on the far side of the entry from the market,
    so reaching it REQUIRES having crossed the entry level first — the fill
    necessarily precedes it, wherever in the bar the extreme printed."""
    out = evaluate_candidate_shadow(**levels, timeframe="15m", bar_time=BAR,
                                    df=full([bar]))
    assert out["entry_bar_walked"] is True
    assert out["entry_bar_tp_withheld"] is False
    assert out["shadow_outcome"] == "stop"
    assert out["shadow_r_multiple"] == pytest.approx(-1.0, abs=1e-6)


def test_the_bias_is_one_sided_fabricated_losses_are_impossible():
    """The same ambiguous bar shape, with the stop swapped in for the take
    profit: the loss IS booked (it is provable) while the win is not."""
    win = evaluate_candidate_shadow(**LONG, timeframe="15m", bar_time=BAR,
                                    df=full([[106.0, 116.0, 99.9, 100.2]]))
    loss = evaluate_candidate_shadow(**LONG, timeframe="15m", bar_time=BAR,
                                     df=full([[106.0, 107.0, 94.0, 95.0]]))
    assert win["shadow_outcome"] not in ("tp1", "tp2", "tp3")
    assert loss["shadow_outcome"] == "stop"


def test_a_take_profit_on_the_bar_after_entry_is_booked_normally():
    out = evaluate_candidate_shadow(**LONG, timeframe="15m", bar_time=BAR,
                                    df=full([[106.0, 106.5, 99.9, 100.2],
                                             [100.2, 116.0, 100.0, 115.5]]))
    assert out["entry_bar_walked"] is False
    assert out["shadow_outcome"] in ("tp1", "tp2", "tp3")


def test_the_skipped_entry_bar_contributes_no_extrema():
    """Skipping must drop the bar entirely — a high that cannot be credited as a
    TP must not leak in through MFE either."""
    skipped = evaluate_candidate_shadow(**LONG, timeframe="15m", bar_time=BAR,
                                        df=full([[106.0, 116.0, 99.9, 100.2],
                                                 [100.2, 100.5, 100.0, 100.3]]))
    clean = evaluate_candidate_shadow(**LONG, timeframe="15m", bar_time=BAR,
                                      df=full([[106.0, 106.2, 99.9, 100.2],
                                               [100.2, 100.5, 100.0, 100.3]]))
    assert skipped["shadow_mfe_pct"] == clean["shadow_mfe_pct"]


def test_no_following_bar_after_an_ambiguous_entry_bar_is_undecidable():
    out = evaluate_candidate_shadow(**LONG, timeframe="15m", bar_time=BAR,
                                    df=bars([[106.0, 116.0, 99.9, 100.2]]))
    assert out["shadow_outcome"] == SHADOW_UNDECIDABLE
    assert out["shadow_resolution_reason"] in (
        "entry_bar_ambiguous_no_following_bars", SHADOW_REASON_INCOMPLETE_WINDOW)


def test_the_same_bar_tp_and_sl_conservative_rule_is_untouched():
    """A bar AFTER the entry that touches both: the conservative tie-break still
    books the stop and still flags the ambiguity."""
    out = evaluate_candidate_shadow(**LONG, timeframe="15m", bar_time=BAR,
                                    df=full([[99.0, 99.5, 98.5, 99.0],
                                             [99.0, 116.0, 94.0, 100.0]]))
    assert out["shadow_outcome"] == "stop"
    assert out["intrabar_ambiguous"] is True


def test_walk_start_is_symmetric_between_directions():
    """Same geometry mirrored around the entry must give the same decision."""
    for lo, sh in (
        ((99.0, 110.0, 98.0, 100.0), (101.0, 102.0, 90.0, 100.0)),      # fill at open
        ((106.0, 107.0, 94.0, 95.0), (94.0, 106.0, 93.0, 105.0)),       # stop forced
        ((106.0, 116.0, 99.9, 100.2), (94.0, 100.1, 84.0, 99.8)),       # ambiguous
    ):
        a = _walk_start(lo, 0, 100.0, 95.0, True)
        b = _walk_start(sh, 0, 100.0, 105.0, False)
        assert a == b, (lo, sh, a, b)


def test_walk_start_has_exactly_one_implementation():
    """The promotion must REMOVE the copy, not add a second one.

    Two functions with the same rule is how the live path and the shadow drift
    apart silently — each stays self-consistent while disagreeing with the other.
    """
    import app.services.shadow_eval as se
    import app.services.entry_activation as ea

    assert "def _walk_start(" not in inspect.getsource(se),         "shadow_eval still defines its own copy of the entry-bar rule"
    assert se.walk_start is ea.walk_start, "shadow_eval is not consuming the shared one"
    assert "def walk_start(" in inspect.getsource(ea)


def test_walk_start_is_total_and_pure():
    assert _walk_start(None, 7, 100.0, 95.0, True) == (7, False, False)
    src = inspect.getsource(_walk_start)
    for forbidden in ("await ", "datetime.now", "requests", "session", "db."):
        assert forbidden not in src, forbidden


# ══════════════════════════ BLOCKER 2 · window completeness ══════════════════
@pytest.mark.parametrize("timeframe,expected", [
    ("15m", 192), ("1h", 48), ("4h", 12), ("1d", 2),
])
def test_expected_horizon_bars_is_ceil_of_the_real_horizon(timeframe, expected):
    assert expected_horizon_bars(timeframe) == expected
    dur = TIMEFRAME_DURATIONS[timeframe]
    assert expected_horizon_bars(timeframe) == -(-SHADOW_HORIZON // dur)


def test_the_rounding_is_ceil_and_not_floor(monkeypatch):
    """Every scheduled timeframe divides 48h exactly (192 / 48 / 12 / 2), so floor
    and ceil agree today and no live case can tell them apart. That is precisely
    why it needs pinning: the first timeframe that does NOT divide evenly would
    silently accept a window one bar short of complete."""
    import app.services.shadow_eval as se

    patched = dict(TIMEFRAME_DURATIONS)
    patched["7h"] = timedelta(hours=7)            # 48 / 7 = 6.857...
    monkeypatch.setattr(se, "TIMEFRAME_DURATIONS", patched)

    assert se.expected_horizon_bars("7h") == 7    # ceil
    assert se.expected_horizon_bars("7h") != int(SHADOW_HORIZON / timedelta(hours=7))  # floor = 6

    # And a 6-bar window must not read as complete for it.
    idx = pd.DatetimeIndex([BAR + (i + 1) * timedelta(hours=7) for i in range(6)])
    six = pd.DataFrame(np.ones((6, 4)), index=idx,
                       columns=["open", "high", "low", "close"]).assign(volume=1.0)
    assert se.window_is_complete(six, "7h") is False


def test_expected_bars_is_not_the_padded_fetch_limit():
    """Judging completeness against the fetch limit (which carries safety slack)
    would let a genuinely short window look full."""
    from app.services.shadow_eval import SHADOW_FETCH_SAFETY_BARS, historical_window
    for tf in ("15m", "1h", "4h", "1d"):
        _s, _e, limit = historical_window(BAR, tf)
        assert limit == expected_horizon_bars(tf) + SHADOW_FETCH_SAFETY_BARS
        assert expected_horizon_bars(tf) < limit


def test_window_completeness_is_measured_not_assumed():
    assert window_is_complete(bars([[1.0, 1.0, 1.0, 1.0]] * 192), "15m") is True
    assert window_is_complete(bars([[1.0, 1.0, 1.0, 1.0]] * 191), "15m") is False
    assert window_is_complete(None, "15m") is False


def test_a_partial_window_cannot_produce_never_entered():
    """4 of 192 bars, price never near the entry. 'It never came back' is a claim
    about the 188 bars that are missing."""
    df = bars([[200.0, 205.0, 199.0, 204.0]] * 4)
    out = evaluate_candidate_shadow(**LONG, timeframe="15m", bar_time=BAR, df=df)
    assert out["shadow_outcome"] == SHADOW_UNDECIDABLE
    assert out["shadow_resolution_reason"] == SHADOW_REASON_INCOMPLETE_WINDOW


def test_a_partial_window_cannot_produce_expiry():
    """Entered and still open when the (short) data ran out — the remainder would
    be marked to a last close that is not the last close."""
    df = bars([[99.0, 100.5, 99.0, 100.0]] * 4)
    out = evaluate_candidate_shadow(**LONG, timeframe="15m", bar_time=BAR, df=df)
    assert out["shadow_outcome"] == SHADOW_UNDECIDABLE
    assert out["shadow_resolution_reason"] == SHADOW_REASON_INCOMPLETE_WINDOW


def test_a_partial_window_CAN_settle_a_stop_or_a_take_profit():
    """The event happened inside the bars we have; later bars cannot unhappen it."""
    stopped = evaluate_candidate_shadow(
        **LONG, timeframe="15m", bar_time=BAR,
        df=bars([[99.0, 99.5, 98.0, 99.0], [99.0, 99.2, 94.0, 95.0]]))
    assert stopped["shadow_outcome"] == "stop"
    won = evaluate_candidate_shadow(
        **LONG, timeframe="15m", bar_time=BAR,
        df=bars([[99.0, 99.5, 98.0, 99.0], [99.0, 116.0, 99.0, 115.0]]))
    assert won["shadow_outcome"] in ("tp1", "tp2", "tp3")


def test_a_complete_window_does_produce_the_terminal_outcome():
    ne = evaluate_candidate_shadow(**LONG, timeframe="15m", bar_time=BAR,
                                   df=bars([[200.0, 205.0, 199.0, 204.0]] * 192))
    assert ne["shadow_outcome"] == "never_entered"
    exp = evaluate_candidate_shadow(**LONG, timeframe="15m", bar_time=BAR,
                                    df=bars([[99.0, 100.5, 99.0, 100.0]] * 192))
    assert exp["shadow_outcome"] == "expiry"


def test_the_boundary_is_exact_at_the_expected_bar_count():
    at = bars([[200.0, 205.0, 199.0, 204.0]] * 192)
    one_short = bars([[200.0, 205.0, 199.0, 204.0]] * 191)
    assert evaluate_candidate_shadow(**LONG, timeframe="15m", bar_time=BAR,
                                     df=at)["shadow_outcome"] == "never_entered"
    assert evaluate_candidate_shadow(**LONG, timeframe="15m", bar_time=BAR,
                                     df=one_short)["shadow_outcome"] == SHADOW_UNDECIDABLE


def test_omitting_the_timeframe_keeps_the_old_permissive_behaviour():
    """The parameter is optional so existing callers are unchanged; the runner
    always passes it. A test pins that it does."""
    df = bars([[200.0, 205.0, 199.0, 204.0]] * 4)
    assert evaluate_candidate_shadow(**LONG, bar_time=BAR,
                                     df=df)["shadow_outcome"] == "never_entered"
    src = textwrap.dedent(inspect.getsource(runner.evaluate))
    assert "timeframe=cand.timeframe," in src


# ══════════════════════ BLOCKER 3 · transient vs permanent ═══════════════════
def test_the_two_reason_sets_are_disjoint():
    assert SHADOW_RETRYABLE_REASONS == {SHADOW_REASON_TRANSIENT_FETCH,
                                        SHADOW_REASON_INCOMPLETE_WINDOW}
    assert not (SHADOW_RETRYABLE_REASONS & SHADOW_TERMINAL_REASONS)
    assert SHADOW_REASON_DATA_UNAVAILABLE not in SHADOW_RETRYABLE_REASONS
    assert SHADOW_PERMANENT_REASONS < SHADOW_TERMINAL_REASONS


def test_age_no_longer_retires_anything():
    """`too_old` used to promote a failed fetch into a permanent stamp. Age is a
    fact about the market, not about the network."""
    src = textwrap.dedent(inspect.getsource(runner.evaluate))
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "_finalise_undecidable":
            names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            assert "too_old" not in names, ast.dump(node)[:200]
    # The variable itself is gone from the decision logic.
    assert "too_old = " not in src
    # MAX_RETRY_AGE survives only as a reporting threshold.
    assert 'stats["stale_beyond_retry_age"]' in src


@pytest.mark.asyncio
async def test_a_transient_fetch_error_is_never_terminal(monkeypatch):
    """A 429 on a row far past the retry age must still be retryable."""
    ancient = datetime.now(UTC) - timedelta(days=60)
    ancient = ancient.replace(minute=0, second=0, microsecond=0)

    class Cand:
        id = "c1"; symbol = "BTCUSDT"; timeframe = "15m"
        evaluated_bar_time = ancient
        engine_direction = "bullish"
        entry_zone_low, entry_zone_high, stop_loss = 99.0, 101.0, 95.0
        tp1, tp2, tp3 = 105.0, 110.0, 115.0

    class DB:
        def __init__(self):
            self.statements = []
            self.commits = self.rollbacks = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *e):
            return False

        async def execute(self, stmt, *a, **kw):
            self.statements.append(stmt)

            class R:
                def scalars(self_inner):
                    return self_inner

                def all(self_inner):
                    return [Cand()]
            return R()

        async def commit(self):
            self.commits += 1

        async def rollback(self):
            self.rollbacks += 1

    class Throttled:
        async def fetch_ohlcv(self, *a, **kw):
            raise RuntimeError("429 Too Many Requests")

        async def close(self):
            pass

    db = DB()
    monkeypatch.setattr(runner, "async_session_factory", lambda: db)
    monkeypatch.setattr(runner, "BinanceCollector", Throttled)

    stats = await runner.evaluate(5, dry_run=False)

    assert stats["transient_fetch_error_retry"] == 1
    assert stats["data_unavailable"] == 0
    assert stats["undecidable_terminal"] == 0
    assert stats["stale_beyond_retry_age"] == 1        # observed, not acted on
    updates = [s for s in db.statements if str(s).strip().upper().startswith("UPDATE")]
    assert updates == [], "a transient failure must not stamp the row"


def test_a_delisted_symbol_is_still_permanent():
    """The other half of the contract: a completed answer whose data ends before
    the window opens stays terminal."""
    old = datetime(2025, 1, 13, 2, 45, tzinfo=UTC)
    # The exchange answers, but its last kline predates the candidate entirely —
    # the delisting signature. Indexed off `old` itself so the relationship is
    # explicit rather than inherited from the module-level BAR.
    idx = pd.DatetimeIndex([old - timedelta(days=30) + i * TIMEFRAME_DURATIONS["15m"]
                            for i in range(5)])
    stale = pd.DataFrame(np.ones((5, 4)), index=idx,
                         columns=["open", "high", "low", "close"]).assign(volume=1.0)
    assert stale.index[-1] < old
    assert runner._exchange_has_nothing(stale, old, "15m") is True

    # A frame that DOES reach into the window is not the delisting case.
    live = pd.DataFrame(np.ones((5, 4)),
                        index=pd.DatetimeIndex([old + i * TIMEFRAME_DURATIONS["15m"]
                                                for i in range(1, 6)]),
                        columns=["open", "high", "low", "close"]).assign(volume=1.0)
    assert runner._exchange_has_nothing(live, old, "15m") is False
    assert runner._exchange_has_nothing(None, old, "15m") is False


def test_the_runner_routes_reasons_by_set_not_by_age():
    src = textwrap.dedent(inspect.getsource(runner.evaluate))
    assert "if reason in SHADOW_TERMINAL_REASONS:" in src
    assert "elif reason in SHADOW_RETRYABLE_REASONS:" in src


# ═════════════════════════ unchanged guarantees ══════════════════════════════
def test_dry_run_is_still_the_default_and_writes_nothing():
    assert inspect.signature(runner.evaluate).parameters["dry_run"].default is True
    assert inspect.signature(runner._finalise_undecidable).parameters["dry_run"].default is True
    src = textwrap.dedent(inspect.getsource(runner.main))
    assert "dry_run = not args.write" in src


def test_the_write_allowlist_and_extra_guard_are_intact():
    assert "extra" not in runner._WRITABLE
    assert runner._WRITABLE_EXTRA == {"extra"}
    with pytest.raises(RuntimeError):
        runner._assert_write_targets({"verdict": "published"}, allow_extra=True)
    src = textwrap.dedent(inspect.getsource(runner.evaluate))
    assert "_assert_write_targets(values, allow_extra=True)" in src


def test_the_fetch_window_from_passb_a_is_unbroken():
    from app.services.shadow_eval import historical_window
    assert {tf: historical_window(BAR, tf)[2]
            for tf in ("15m", "1h", "4h", "1d")} == {"15m": 212, "1h": 68, "4h": 32, "1d": 22}
    src = textwrap.dedent(inspect.getsource(runner._fetch_bars))
    assert "end_time_ms=int(window_end.timestamp() * 1000)" in src


def test_the_provenance_exposes_the_new_gates_and_leaks_nothing():
    df = bars([[100.0, 100.1, 99.9, 100.0]] * 10)
    prov = shadow_passb_provenance(bar_time=BAR, timeframe="15m", requested_limit=212,
                                   df=df, dry_run=True, intrabar_ambiguous=False,
                                   entry_bar_walked=False, entry_bar_tp_withheld=True)
    assert prov["expected_horizon_bars"] == 192
    assert prov["actual_bar_count"] == 10
    assert prov["window_complete"] is False
    assert prov["entry_bar_walked"] is False
    assert prov["entry_bar_tp_withheld"] is True
    import json
    blob = json.dumps(prov)
    for needle in ("postgres", "://", "token", "password", "Traceback", "http"):
        assert needle not in blob, needle


def test_the_live_decision_path_is_untouched():
    from app.backtesting import resolution_core
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
    # The shared walk is called, never reimplemented, and its default is intact.
    rc = inspect.getsource(resolution_core)
    assert 'execution_model: str = "conservative"' in rc
    se = inspect.getsource(__import__("app.services.shadow_eval", fromlist=["x"]))
    assert "resolve_trade_path(" in se

    # The live tracker and the shadow evaluator must resolve to the SAME function
    # object. Asserted by identity rather than by matching the import line: an
    # aliased re-export (`import resolve_trade_path as _rtp`) still contains that
    # line as a substring, so a textual check would pass while a real replacement
    # slipped through the same hole.
    import app.backtesting.tracker as tracker_mod
    import app.services.shadow_eval as shadow_mod
    from app.backtesting.resolution_core import resolve_trade_path as canonical
    assert tracker_mod.resolve_trade_path is canonical
    assert shadow_mod.resolve_trade_path is canonical


def test_the_evaluator_cannot_see_todays_state():
    """CP-SHADOW-PASSB-B parity depends on this: a verdict must be a function of
    (levels, bars) alone. If the evaluator could reach today's coin memory, regime
    or adaptive weights, replaying an old candidate would be look-ahead wearing a
    parity label."""
    import app.services.shadow_eval as se

    src = inspect.getsource(se)
    for forbidden in ("coin_memory", "detect_regime", "adaptive", "async_session_factory",
                      "BinanceCollector", "datetime.now", "utcnow", "requests"):
        assert forbidden not in src, forbidden

    sig = inspect.signature(se.evaluate_candidate_shadow)
    assert set(sig.parameters) == {
        "direction", "entry_zone_low", "entry_zone_high", "stop_loss",
        "tp1", "tp2", "tp3", "df", "bar_time", "timeframe"}

    # Same inputs, twice, in either order: identical verdict.
    df = full([[106.0, 106.5, 99.9, 100.2], [100.2, 116.0, 100.0, 115.5]])
    a = evaluate_candidate_shadow(**LONG, df=df, bar_time=BAR, timeframe="15m")
    b = evaluate_candidate_shadow(**LONG, df=df.copy(), bar_time=BAR, timeframe="15m")
    assert a == b


def test_the_cohort_marker_survives_so_the_two_can_be_kept_apart():
    """Parity is reported per cohort; mixing a pre-F1 candidate with a
    closed_candle_v1 one compares two different systems."""
    from app.engines.ai_decision.signal_generator import DECISION_INPUT_VERSION
    from app.services.candidate_log import build_candidate_values
    assert DECISION_INPUT_VERSION == "closed_candle_v1"
    src = inspect.getsource(build_candidate_values)
    assert '"decision_input_version"' in src


def test_this_checkpoint_adds_no_migration():
    migrations = sorted(p.name for p in (BACKEND / "migrations").glob("*.sql"))
    assert migrations[-1] == "0010_candidate_log_rls.sql", migrations[-1]


def test_an_unsupported_timeframe_still_fails_one_row_only():
    with pytest.raises(ValueError):
        expected_horizon_bars("30m")
    src = textwrap.dedent(inspect.getsource(runner._fetch_bars))
    assert "except ValueError as exc:" in src


def test_walk_start_promotion_is_behaviourally_identical_to_the_original():
    """Differential proof that the PROMOTION changed nothing.

    The original body is transcribed BY HAND below — deliberately not imported,
    so a change to the shared implementation cannot silently redefine what
    "unchanged" means. Exhaustive random inputs across both directions, including
    the boundary cases where each proved exception flips.
    """
    import random

    def original(entry_bar, entry_pos, entry_mid, sl, is_bull):
        if entry_bar is None:
            return entry_pos, False, False
        o, h, l, _c = entry_bar[0], entry_bar[1], entry_bar[2], entry_bar[3]
        if (o <= entry_mid) if is_bull else (o >= entry_mid):
            return entry_pos, True, False
        if (l <= sl) if is_bull else (h >= sl):
            return entry_pos, True, False
        return entry_pos + 1, False, True

    rnd = random.Random(20260803)
    for _ in range(200_000):
        mid = rnd.uniform(1.0, 1000.0)
        is_bull = rnd.random() < 0.5
        sl = mid * (0.97 if is_bull else 1.03)
        # Draw around the two decision boundaries so the branches are all hit.
        o = rnd.choice([mid, sl, mid * rnd.uniform(0.95, 1.05)])
        h = max(o, mid * rnd.uniform(1.0, 1.06))
        l = min(o, mid * rnd.uniform(0.94, 1.0))
        pos = rnd.randrange(0, 50)
        assert _walk_start((o, h, l, o), pos, mid, sl, is_bull) == \
            original((o, h, l, o), pos, mid, sl, is_bull), (o, h, l, mid, sl, is_bull)
    assert _walk_start(None, 3, 100.0, 95.0, True) == original(None, 3, 100.0, 95.0, True)
