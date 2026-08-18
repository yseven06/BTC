"""CP-SIGNAL-SHADOW-OBSERVABILITY-V1 — publication-time observation evidence.

WHY THIS EXISTS. Most of the evidence this product needs is already captured:
`signal_decision_candidates` records every scored evaluation (published, dropped
and skipped) with its demotion reason, `signal_trade_path` already carries MAE /
MFE / first-touch, and `exec_cost` already measures the book at publication. Two
things were genuinely missing, and only two:

  1. HOW FAR PRICE HAD ALREADY RUN when the signal was published. The candidate
     log stores `last_close` per evaluation, so a lookback CAN be reconstructed
     by joining rows — but only at close granularity, and only while neighbouring
     rows survive. The analysis frame in memory at publication holds the TRUE
     intrabar highs and lows, so freezing the lookback there is both cheaper and
     strictly more accurate than reconstructing it later.

  2. WHETHER A DEPTH BAND WAS EVER MEASURABLE. `exec_cost` records
     `within_0.05pct.bid_notional = 0.0` for an asset whose tick is a quarter of
     a percent, which reads as "nobody is quoting" when the truth is "no price
     can exist in that band". Measured across the tracked universe, one tick
     exceeds 0.05% of price on 59% of symbols and 0.25% on 7%.

THE STANDARD THIS RECORD IS HELD TO. It is evidence, never a gate. It is built
from data already in memory, so it costs no network call and no query. It is a
PURE SYNCHRONOUS function: it cannot await, cannot open a client, and therefore
cannot leak one or delay a publication. And it must never state as measured
anything the product does not measure — this system places no orders, so fills,
commissions and slippage stay UNAVAILABLE forever.
"""
from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pandas as pd
import pytest

from app.services import scheduler as sched
from app.services.shadow_observation import (
    LOOKBACK_BARS,
    OBSERVATION_SCHEMA_VERSION,
    build_shadow_observation,
)

BACKEND = Path(__file__).resolve().parent.parent
MODULE = BACKEND / "app" / "services" / "shadow_observation.py"


class _Sig:
    entry_zone_low = 100.0
    entry_zone_high = 101.0
    stop_loss = 97.0
    tp1, tp2, tp3 = 104.0, 107.0, 111.0
    confidence_score = 71.0
    direction = "BULLISH"


def _frame(closes, *, start="2026-08-18 00:00", freq="15min"):
    """A frame shaped like the collector's: UTC index, OHLCV columns."""
    idx = pd.date_range(start, periods=len(closes), freq=freq, tz="UTC")
    return pd.DataFrame(
        {
            "open": [c for c in closes],
            "high": [c * 1.002 for c in closes],
            "low": [c * 0.998 for c in closes],
            "close": list(closes),
            "volume": [1000.0] * len(closes),
        },
        index=idx,
    )


def _rec(closes=None, **kw):
    closes = closes if closes is not None else [100.0 + i * 0.1 for i in range(60)]
    kw.setdefault("symbol", "TESTUSDT")
    kw.setdefault("timeframe", "15m")
    kw.setdefault("signal", _Sig())
    kw.setdefault("bars", _frame(closes))
    kw.setdefault("atr_pct", 0.5)
    return build_shadow_observation(**kw)


# ══ 7 · VERSIONING ═════════════════════════════════════════════════════════
def test_schema_version_is_present_and_stable():
    assert OBSERVATION_SCHEMA_VERSION == 1
    assert _rec()["schema_version"] == 1


def test_the_record_is_strict_json_without_a_custom_encoder():
    """It is written into a `json` column inside the OPEN publication
    transaction, so a value the serialiser chokes on would fail the commit and
    take the signal down with it.

    `allow_nan=False` is the load-bearing argument. Python's json emits bare
    `NaN` and `Infinity` by default — accepted by json.dumps, rejected by every
    strict JSON reader — so the permissive call would pass while writing a
    payload that cannot be read back.
    """
    import json

    json.dumps(_rec(), allow_nan=False)


def test_a_nan_price_cannot_reach_the_record():
    """Frames arrive with NaN more often than one would like: a gap, a fresh
    listing, a partial merge. The float coercion must turn that into an honest
    failure rather than a value that only looks like a number.

    THE LAST close is the one that must be NaN, and the choice is not arbitrary.
    A NaN buried mid-frame is silently skipped by max()/min() — every comparison
    against it is False — so it never reaches the record and proves nothing. The
    final close is read directly and flows into every derived statistic, so it is
    the only position that actually exercises the coercion.
    """
    import json

    import numpy as np

    f = _frame([100.0 + i for i in range(30)])
    f.iloc[-1, f.columns.get_loc("close")] = np.nan
    r = build_shadow_observation(symbol="T", timeframe="15m", signal=_Sig(),
                                 bars=f, atr_pct=0.5)
    json.dumps(r, allow_nan=False)
    assert r["lookback"]["ok"] is False
    assert r["lookback"]["failure_reason"] == "non_numeric_prices"


# ══ 11 · NO FUTURE LEAKAGE ═════════════════════════════════════════════════
def test_the_record_is_a_pure_function_of_the_bars_up_to_publication():
    """THE DECISIVE ANTI-LOOKAHEAD PROPERTY. Publishing at bar k must produce
    exactly the record you get by handing the function the frame truncated at k.
    If any statistic peeked past the last row, appending later bars would change
    the earlier answer — and it must not."""
    closes = [100.0 + i * 0.1 for i in range(60)]
    full = _frame(closes)
    for k in (20, 35, 59):
        early = build_shadow_observation(symbol="T", timeframe="15m", signal=_Sig(),
                                         bars=full.iloc[:k], atr_pct=0.5)
        later = build_shadow_observation(symbol="T", timeframe="15m", signal=_Sig(),
                                         bars=full.iloc[:k], atr_pct=0.5)
        assert early["lookback"] == later["lookback"]
        # And the same prefix embedded in a longer frame yields the same answer
        # for that prefix — proving the tail is never consulted.
        assert early["lookback"]["last_bar_time"] == str(full.index[k - 1])


def test_no_outcome_or_forward_field_can_appear_in_the_record():
    """Publication-time state and later enrichment must not be mixed. Anything
    resolvable only AFTER publication belongs in signal_trade_path."""
    flat = str(_rec())
    for forward in ("mfe", "mae", "hit_tp", "tp1_hit", "outcome", "realized",
                    "realised", "resolved", "win", "loss", "bars_to_outcome"):
        assert forward not in flat.lower(), f"a forward-looking field leaked: {forward}"


def test_the_module_cannot_reach_the_network_or_the_database():
    """Structural, not behavioural. A pure synchronous builder cannot await, so
    it cannot fetch, cannot open a client, and cannot hold the publication
    transaction open. This is what makes a timeout unnecessary rather than
    merely absent."""
    src = MODULE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    assert not [n for n in ast.walk(tree) if isinstance(n, (ast.Await, ast.AsyncFunctionDef))], \
        "the observation builder must stay synchronous"
    for banned in ("BinanceCollector", "httpx", "requests", "aiohttp", "select(",
                   "session", "execute(", "fetch_"):
        assert banned not in src, f"the observation module reached for {banned}"


# ══ 5 · TAXONOMY ═══════════════════════════════════════════════════════════
def test_every_reported_field_carries_an_exact_taxonomy_label():
    prov = _rec()["provenance"]
    assert set(prov.values()) <= {"MEASURED", "DERIVED", "ASSUMED", "UNAVAILABLE"}
    # Bars are measured; everything computed from them is derived. Saying the
    # extension is MEASURED would be a lie of exactly the kind this CP forbids.
    assert prov["lookback_high"] == "MEASURED"
    assert prov["lookback_low"] == "MEASURED"
    assert prov["extension_from_low_pct"] == "DERIVED"
    assert prov["extension_from_low_atr"] == "DERIVED"
    assert prov["range_position_pct"] == "DERIVED"


def test_execution_reality_stays_unavailable_forever():
    """6 · The product places no orders. There is no fill to report, and a
    zero or an estimate in these slots would be a fabrication."""
    prov = _rec()["provenance"]
    for never in ("actual_fill_price", "actual_commission", "actual_slippage"):
        assert prov[never] == "UNAVAILABLE"
    flat = str(_rec())
    assert "fee_rate" not in flat, "this record must not restate a fee assumption"


def test_an_atr_normalised_statistic_is_null_when_the_atr_was_substituted():
    """The risk engine substitutes 2% when ATR is NaN. Dividing by a substituted
    constant produces a number that LOOKS measured and is not — the same trap
    `atr_fallback_used` was introduced for in decision_input_telemetry."""
    r = _rec(atr_pct=2.0, atr_fallback_used=True)
    lb = r["lookback"]
    assert lb["extension_from_low_atr"] is None
    assert lb["extension_from_high_atr"] is None
    assert lb["extension_from_low_pct"] is not None, "the percentage is still honest"
    assert r["provenance"]["extension_from_low_atr"] == "UNAVAILABLE"


def test_a_missing_atr_leaves_the_normalised_fields_null_rather_than_zero():
    lb = _rec(atr_pct=None)["lookback"]
    assert lb["extension_from_low_atr"] is None
    assert lb["extension_from_low_pct"] is not None


# ══ LOOKBACK CORRECTNESS ═══════════════════════════════════════════════════
def test_the_lookback_uses_true_intrabar_extremes_not_closes():
    """The whole reason to compute this at publication rather than reconstruct
    it from the candidate log later: the frame has real highs and lows."""
    closes = [100.0] * 30
    f = _frame(closes)
    f.iloc[10, f.columns.get_loc("low")] = 90.0     # a wick no close records
    f.iloc[20, f.columns.get_loc("high")] = 115.0
    lb = build_shadow_observation(symbol="T", timeframe="15m", signal=_Sig(),
                                  bars=f, atr_pct=0.5)["lookback"]
    assert lb["low"] == pytest.approx(90.0)
    assert lb["high"] == pytest.approx(115.0)


def test_extension_and_bars_since_locate_the_move_that_preceded_publication():
    """The MINAUSDT shape: a low early in the window, publication far above it."""
    closes = [100.0] * 10 + [95.0] + [100.0 + i for i in range(9)]
    f = _frame(closes)
    lb = build_shadow_observation(symbol="T", timeframe="15m", signal=_Sig(),
                                  bars=f, atr_pct=1.0)["lookback"]
    assert lb["bars_since_low"] == 9, lb
    assert lb["extension_from_low_pct"] > 13.0
    assert lb["extension_from_low_atr"] == pytest.approx(
        lb["extension_from_low_pct"] / 1.0, rel=1e-6)
    assert 95.0 <= lb["range_position_pct"] <= 100.0


def test_the_lookback_window_is_bounded():
    """A frame longer than the window must not silently widen the lookback —
    otherwise the statistic means something different on every timeframe."""
    lb = _rec([100.0 + i * 0.01 for i in range(400)])["lookback"]
    assert lb["bars_used"] == LOOKBACK_BARS


def test_a_degenerate_or_empty_frame_fails_closed_without_raising():
    """Fail-open at the call site depends on this never raising."""
    for bad in (pd.DataFrame(), _frame([]), None):
        r = build_shadow_observation(symbol="T", timeframe="15m", signal=_Sig(),
                                     bars=bad, atr_pct=0.5)
        assert r["lookback"]["ok"] is False
        assert r["lookback"]["failure_reason"]
        assert r["lookback"]["extension_from_low_pct"] is None
        assert r["schema_version"] == 1


def test_a_flat_frame_reports_zero_range_without_dividing_by_zero():
    lb = _rec([100.0] * 40)["lookback"]
    assert lb["ok"] is True
    assert lb["range_position_pct"] is None or 0.0 <= lb["range_position_pct"] <= 100.0


def test_the_builder_never_raises_on_hostile_input():
    for kw in ({"signal": None}, {"symbol": None}, {"atr_pct": "x"},
               {"bars": "not a frame"}, {"timeframe": None}):
        r = _rec(**kw)
        assert r["schema_version"] == 1


def test_a_frame_that_explodes_midway_still_fails_closed():
    """The shape checks at the top catch the easy cases, so they can hide a
    missing handler around the arithmetic below them. This frame passes every
    precondition and then throws on the first slice — which is what a real
    pandas version skew or an exotic index does.
    """
    class _Hostile:
        empty = False
        columns = ("high", "low", "close")
        index: list = []

        @property
        def iloc(self):
            raise RuntimeError("frame exploded")

    r = build_shadow_observation(symbol="T", timeframe="15m", signal=_Sig(),
                                 bars=_Hostile(), atr_pct=0.5)
    assert r["schema_version"] == 1
    assert r["lookback"]["ok"] is False
    assert r["lookback"]["failure_reason"] == "RuntimeError"


# ══ 10 · THE JOIN KEY ══════════════════════════════════════════════════════
def test_the_record_freezes_the_candidate_join_key():
    """Everything else worth knowing already lives in signal_decision_candidates.
    Rather than copy those columns, the record freezes the key needed to reach
    them — symbol, timeframe and the evaluated bar."""
    r = _rec(evaluated_bar_time="2026-08-18T13:00:00+00:00")
    link = r["link"]
    assert link["symbol"] == "TESTUSDT"
    assert link["timeframe"] == "15m"
    assert link["evaluated_bar_time"] == "2026-08-18T13:00:00+00:00"
    assert link["candidate_table"] == "signal_decision_candidates"


def test_the_join_key_defaults_to_the_last_closed_bar():
    """candidate_log stamps `evaluated_bar_time` from the final index of the very
    same closed frame, so the default lands on the matching row rather than
    leaving the key null and the join impossible."""
    closes = [100.0 + i for i in range(30)]
    f = _frame(closes)
    r = build_shadow_observation(symbol="T", timeframe="15m", signal=_Sig(), bars=f)
    assert r["link"]["evaluated_bar_time"] == str(f.index[-1])
    assert r["link"]["evaluated_bar_time"] == r["lookback"]["last_bar_time"]


def test_the_join_key_is_null_rather_than_invented_when_the_frame_is_unusable():
    r = build_shadow_observation(symbol="T", timeframe="15m", signal=_Sig(), bars=None)
    assert r["link"]["evaluated_bar_time"] is None


def test_no_authoritative_column_is_duplicated_into_the_record():
    """Duplication is how two sources of truth are born. Geometry, scores and
    regime are already columns on the candidate row and on the signal itself."""
    flat = str(_rec()).lower()
    for owned in ("composite_score", "confidence_score", "engine_scores",
                  "engine_weights", "stop_loss", "planned_rr", "sl_dist_pct",
                  "entry_zone_low", "tp1", "regime", "adx"):
        assert owned not in flat, f"{owned} is authoritative elsewhere and was copied"


# ══ 2 · 8 · 9 — EVIDENCE, NEVER A GATE ═════════════════════════════════════
def test_the_observation_is_never_consulted_by_the_runtime():
    """8 · Nothing anywhere may branch on this evidence."""
    hits = []
    for p in (BACKEND / "app").rglob("*.py"):
        if p.name in ("shadow_observation.py", "shadow_exec_cost.py"):
            continue
        src = p.read_text(encoding="utf-8", errors="ignore")
        for token in ("shadow_observation_v1", "extension_from_low_atr",
                      "range_position_pct", "bars_since_low"):
            if token in src and p.name != "scheduler.py":
                hits.append(f"{p.name}:{token}")
    assert hits == [], f"observation evidence leaked into the runtime: {hits}"


def _observation_block() -> str:
    """The observation's own try/except, unparsed — NOT the rest of the function.

    Scoping matters: splitting the source at the key and reading the tail would
    sweep in the commit and the log line that follow, and fail on code that has
    nothing to do with this evidence.
    """
    tree = ast.parse(inspect.getsource(sched._generate_signal).lstrip()).body[0]
    call = [n for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and getattr(n.func, "id", "") == "build_shadow_observation"]
    assert len(call) == 1, "expected exactly one observation call"
    line = call[0].lineno
    owning = [t for t in ast.walk(tree)
              if isinstance(t, ast.Try)
              and any(getattr(n, "lineno", None) == line for n in ast.walk(t))]
    assert owning, "the observation call sits inside no try block"
    return ast.unparse(min(owning, key=lambda t: line - t.body[0].lineno))


def test_the_scheduler_only_writes_the_observation_and_never_reads_it_back():
    """2 · 9 · The publication path may store the record. It may not consult it,
    and it may not derive a second decision from it."""
    block = _observation_block()
    for banned in ("if shadow_observation", "new_sig.confidence_score", "new_sig.stop_loss",
                   "new_sig.tp1", "new_sig.entry_zone_low", "new_sig.entry_zone_high",
                   "new_sig.live_status", "new_sig.is_active", "decision["):
        assert banned not in block, f"the observation path touches {banned}"


def test_the_builder_is_pure_and_cannot_mutate_the_signal_it_is_shown():
    before = {k: v for k, v in vars(_Sig).items() if not k.startswith("_")}
    s = _Sig()
    build_shadow_observation(symbol="T", timeframe="15m", signal=s,
                             bars=_frame([100.0] * 30), atr_pct=0.5)
    after = {k: v for k, v in vars(_Sig).items() if not k.startswith("_")}
    assert before == after


def test_the_frame_it_is_handed_is_not_mutated():
    """It is the same object the engines and the snapshot builder use."""
    f = _frame([100.0 + i for i in range(30)])
    snapshot = f.copy(deep=True)
    build_shadow_observation(symbol="T", timeframe="15m", signal=_Sig(),
                             bars=f, atr_pct=0.5)
    pd.testing.assert_frame_equal(f, snapshot)


# ══ WIRING · 1 · 3 · 4 · 13 · 14 ═══════════════════════════════════════════
def _sched_src() -> str:
    return inspect.getsource(sched._generate_signal)


def test_the_observation_is_merged_additively_and_destroys_nothing():
    """3 · 4 · birth and exec_cost must both survive. The merge must spread the
    existing dict, exactly as the exec_cost write does."""
    src = _sched_src()
    seg = src.split("shadow_observation_v1", 1)[0]
    tail = seg[-400:]
    assert "**(snapshot.extra or {})" in tail, \
        "the observation must be merged onto the existing extra, not assigned over it"


def test_the_observation_has_its_own_exception_handler():
    """1 · A failure here must not take down publication — nor the exec_cost
    capture that precedes it. Its nearest enclosing try must have handlers."""
    tree = ast.parse(inspect.getsource(sched._generate_signal).lstrip()).body[0]
    call = [n for n in ast.walk(tree)
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "build_shadow_observation"]
    assert len(call) == 1, "expected exactly one observation call"
    line = call[0].lineno
    guarded = [t for t in ast.walk(tree)
               if isinstance(t, ast.Try) and t.handlers
               and t.body and t.body[0].lineno <= line <= max(
                   getattr(n, "lineno", t.body[0].lineno) for n in ast.walk(t) if hasattr(n, "lineno"))]
    assert guarded, "the observation call is not inside a try that has handlers"
    innermost = min(guarded, key=lambda t: line - t.body[0].lineno)
    assert innermost.handlers, "the observation call's nearest try has no handler"

    # HAVING a handler is not the property that matters — SWALLOWING is. A
    # handler whose body is `raise` satisfies every structural check above and
    # still takes the publication down with it, which is precisely the mutant
    # that survived the first version of this guard.
    for h in innermost.handlers:
        raises = [n for n in ast.walk(ast.Module(body=h.body, type_ignores=[]))
                  if isinstance(n, ast.Raise)]
        assert not raises, \
            "the observation's handler re-raises: a capture failure would abort publication"
        assert any(isinstance(n, ast.Call) and "warning" in ast.unparse(n.func)
                   for n in ast.walk(ast.Module(body=h.body, type_ignores=[]))), \
            "a swallowed failure must at least be logged, or it is invisible"


def test_the_observation_call_adds_no_collector_and_no_await():
    """13 · Nothing to clean up, because nothing is acquired. This is stronger
    than a cleanup guard: there is no client to leak."""
    src = _sched_src()
    assert src.count("BinanceCollector()") == 2, \
        "the observation must not introduce a third market-data client"
    call_line = [l for l in src.splitlines() if "build_shadow_observation(" in l]
    assert call_line, "no observation call found"
    assert not any("await build_shadow_observation" in l for l in src.splitlines()), \
        "the observation builder is synchronous and must not be awaited"


def test_the_observation_is_written_once_per_signal():
    """14 · One snapshot, one record. Two writes would double the payload and
    make 'which one is true' unanswerable."""
    src = _sched_src()
    assert src.count("build_shadow_observation(") == 1
    assert src.count('"shadow_observation_v1"') == 1


def test_the_observation_reads_the_closed_analysis_frame():
    """10 · The full frame's last candle is still FORMING. A lookback taken from
    it would mix a partial bar into a bar statistic and would not reproduce: the
    same publication re-derived a minute later would give a different high.

    Read off the call's keyword, not a string split — `atr_pct` is passed as a
    parenthesised expression, so splitting on the first ')' is accidental.
    """
    tree = ast.parse(_sched_src().lstrip()).body[0]
    call = [n for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and getattr(n.func, "id", "") == "build_shadow_observation"][0]
    bars = [k.value for k in call.keywords if k.arg == "bars"]
    assert bars, "the observation is not given a bars argument"
    assert getattr(bars[0], "id", None) == "df_closed", \
        f"the observation must read df_closed, got {ast.dump(bars[0])[:80]}"


def test_no_migration_is_required():
    """15 · extra is an existing JSON column; a new top-level key needs no DDL."""
    mig = BACKEND / "migrations"
    if mig.exists():
        recent = sorted(p.name for p in mig.glob("*.sql"))
        assert not any("observation" in n for n in recent), \
            "no migration should have been added for an additive extra key"
