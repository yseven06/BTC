"""CP-SIGNAL-SHADOW-COST-CAPTURE-E — shadow execution-cost evidence.

WHAT THIS IS FOR. CP-D established that this system places no orders, so actual
fill price, commission and slippage are UNAVAILABLE and always will be for
historical rows. The one thing still capturable is the market's quoted state AT
PUBLICATION, going forward. This module records that, and nothing else.

WHAT IT MUST NEVER DO. It is evidence, not a filter. The predicates it stores are
evaluated and written; they are never consulted by any decision. Every test below
exists because the failure it describes would be invisible in ordinary use — a
shadow surface that quietly changed a published signal would look exactly like a
working one until somebody audited the trades.

TERMINOLOGY IS LOAD-BEARING and is asserted, not merely documented:
  MEASURED    live bid/ask/depth read at observation time
  DERIVED     sl_dist, ATR, entry geometry, later outcome
  ASSUMED     any fee rate — this system has no account and no fee tier
  UNAVAILABLE actual fill, actual commission, actual slippage
"""
from __future__ import annotations

import asyncio
import ast
import inspect
import pathlib
import subprocess
import time

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent


def _mod():
    from app.services import shadow_exec_cost as m
    return m


class _Sig:
    entry_zone_low = 100.0
    entry_zone_high = 101.0
    stop_loss = 99.0
    tp1, tp2, tp3 = 103.0, 105.0, 108.0
    confidence_score = 70.0
    timeframe = "M15"
    direction = "BULLISH"


def _fake_signal():
    return _Sig()


def _ok_collector():
    class OK:
        async def fetch_orderbook(self, symbol):
            return {"bids": [["100.00", "10"], ["99.99", "20"]],
                    "asks": [["100.05", "10"], ["100.06", "20"]]}
    return OK()


# ══ THE PREDICATES ARE FROZEN ══════════════════════════════════════════════
def test_the_frozen_thresholds_are_exactly_the_ones_cp_c_measured():
    """CP-C froze these by measuring them out-of-sample. Moving or adding one
    here would re-tune a threshold on data not yet collected, which is the
    exact overfitting this chain has avoided twice."""
    assert _mod().FROZEN_SL_DIST_THRESHOLDS == (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0, 1.2)


def test_predicates_are_evaluated_but_never_consulted_by_a_decision():
    """Structural: the module may COMPUTE would_keep, but nothing else in app/
    may branch on it. A shadow that gates is not a shadow."""
    hits = []
    for p in (BACKEND / "app").rglob("*.py"):
        if p.name == "shadow_exec_cost.py":
            continue
        src = p.read_text(encoding="utf-8", errors="ignore")
        if "would_keep" in src or "would_filter" in src:
            hits.append(p.name)
    assert hits == [], f"a shadow predicate is referenced outside its own module: {hits}"


# ══ NON-INTERFERENCE — the load-bearing set ════════════════════════════════
@pytest.mark.asyncio
async def test_a_snapshot_failure_returns_an_explicit_marker_and_never_raises():
    """Publication must survive a dead exchange, and the marker must be
    distinguishable from a genuine zero spread."""
    class Dead:
        async def fetch_orderbook(self, symbol):
            raise ConnectionError("exchange down")

    rec = await _mod().build_shadow_exec_cost(
        collector=Dead(), symbol="BTCUSDT", signal=_fake_signal(), atr_pct=0.4)
    assert rec is not None, "a failed snapshot must still produce evidence"
    assert rec["market"]["ok"] is False
    assert rec["market"]["spread_pct"] is None, "a failure must not look like zero spread"
    # The reason must NAME the fault, not merely be truthy. A generic
    # "unexpected" would mean the precise classifier had been bypassed and every
    # failure mode would collapse into one bucket — which defeats the purpose of
    # recording failures at all. (A sabotage run reached exactly that state by
    # deleting the inner handler and still passed a truthiness-only assertion.)
    reason = rec["market"]["failure_reason"]
    assert "ConnectionError" in reason, reason
    assert not reason.startswith("unexpected"), (
        "the precise failure classifier was bypassed; only the catch-all ran")


@pytest.mark.asyncio
async def test_a_hanging_exchange_cannot_stall_publication():
    """No retry, and a hard bound: an unbounded call here would hold the
    publication transaction open across the network."""
    class Hang:
        async def fetch_orderbook(self, symbol):
            await asyncio.sleep(30)

    t = time.perf_counter()
    rec = await _mod().build_shadow_exec_cost(
        collector=Hang(), symbol="BTCUSDT", signal=_fake_signal(), atr_pct=0.4)
    dt = time.perf_counter() - t
    assert dt < _mod().SNAPSHOT_TIMEOUT_SECONDS + 1.0, f"took {dt:.1f}s"
    assert rec["market"]["ok"] is False


def test_the_module_cannot_place_an_order_or_touch_lifecycle():
    src = inspect.getsource(_mod())
    for banned in ("place_order", "create_order", "new_order",
                   "live_status", "WAITING_ENTRY", "confidence_score =",
                   "stop_loss =", "tp1 =", "entry_zone_low ="):
        assert banned not in src, f"shadow module references {banned!r}"


def test_the_module_never_writes_or_commits():
    """It BUILDS a record; the caller persists it inside the existing
    transaction. A commit here would split the publication write in two."""
    tree = ast.parse(inspect.getsource(_mod()))
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    for banned in ("commit", "rollback", "add", "flush", "execute", "delete"):
        assert banned not in called, f"shadow module calls db.{banned}"


def test_the_shared_production_collector_is_not_modified_by_this_cp():
    """The collector is frozen by Pass-B T14. This CP uses fetch_orderbook,
    which already existed; it must not have grown a new method."""
    out = subprocess.run(
        ["git", "diff", "--name-only", "b474db0", "--",
         "backend/app/collectors/binance_collector.py"],
        cwd=BACKEND.parent, capture_output=True, text=True).stdout.strip()
    assert out == "", f"the shared collector was modified: {out}"


# ══ INTEGRITY ══════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_measured_derived_and_assumed_cannot_masquerade_as_each_other():
    rec = await _mod().build_shadow_exec_cost(
        collector=_ok_collector(), symbol="BTCUSDT", signal=_fake_signal(), atr_pct=0.4)
    assert rec["provenance"]["bid"] == "MEASURED"
    assert rec["provenance"]["sl_dist_pct"] == "DERIVED"
    assert rec["provenance"]["fee_rate"] == "ASSUMED"
    assert rec["provenance"]["actual_fill_price"] == "UNAVAILABLE"
    assert "fill_price" not in rec["market"], "no fake fill may be introduced"


@pytest.mark.asyncio
async def test_no_fee_rate_is_baked_in():
    """This system has no account and no fee tier. Storing one would turn an
    assumption into an apparent measurement, and would freeze today's guess
    into tomorrow's analysis."""
    rec = await _mod().build_shadow_exec_cost(
        collector=_ok_collector(), symbol="BTCUSDT", signal=_fake_signal(), atr_pct=0.4)
    assert rec.get("assumed_fee_rate") is None
    assert rec.get("net_expectancy") is None, "cost must stay recomputable, not frozen"


@pytest.mark.asyncio
async def test_bid_never_exceeds_ask_and_spread_is_derived_from_both():
    rec = await _mod().build_shadow_exec_cost(
        collector=_ok_collector(), symbol="BTCUSDT", signal=_fake_signal(), atr_pct=0.4)
    m = rec["market"]
    assert m["ok"] is True and m["bid"] <= m["ask"]
    assert m["spread_pct"] == pytest.approx(
        100 * (m["ask"] - m["bid"]) / ((m["ask"] + m["bid"]) / 2))


@pytest.mark.asyncio
async def test_a_crossed_or_nonpositive_book_is_rejected_not_stored():
    class Crossed:
        async def fetch_orderbook(self, symbol):
            return {"bids": [["101", "5"]], "asks": [["100", "5"]]}

    rec = await _mod().build_shadow_exec_cost(
        collector=Crossed(), symbol="BTCUSDT", signal=_fake_signal(), atr_pct=0.4)
    assert rec["market"]["ok"] is False and rec["market"]["spread_pct"] is None


@pytest.mark.asyncio
async def test_predicates_reflect_the_signals_own_sl_distance():
    rec = await _mod().build_shadow_exec_cost(
        collector=_ok_collector(), symbol="BTCUSDT", signal=_fake_signal(), atr_pct=0.4)
    sd = rec["derived"]["sl_dist_pct"]
    for x in _mod().FROZEN_SL_DIST_THRESHOLDS:
        assert rec["predicates"][f"sl_dist_lt_{x}"] is (sd < x)


@pytest.mark.asyncio
async def test_the_record_is_deterministic_for_the_same_inputs():
    """Idempotency: the caller writes it once per signal, and rebuilding it
    must not produce a different shape."""
    a = await _mod().build_shadow_exec_cost(
        collector=_ok_collector(), symbol="BTCUSDT", signal=_fake_signal(), atr_pct=0.4)
    b = await _mod().build_shadow_exec_cost(
        collector=_ok_collector(), symbol="BTCUSDT", signal=_fake_signal(), atr_pct=0.4)
    a["observed_at"] = b["observed_at"] = None
    assert a == b


@pytest.mark.asyncio
async def test_timestamps_are_timezone_aware_utc():
    rec = await _mod().build_shadow_exec_cost(
        collector=_ok_collector(), symbol="BTCUSDT", signal=_fake_signal(), atr_pct=0.4)
    assert rec["observed_at"].endswith("+00:00"), rec["observed_at"]
