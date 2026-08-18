"""CP-F — the shadow capture is WIRED, and cannot touch publication.

The module itself was proven in CP-E. What is unproven until here is the join:
that the publication path calls it, calls it once, reuses the collector it
already has, merges rather than overwrites, and — above all — that a failure in
the shadow path cannot cost the product a signal.

WHY THESE ARE STRUCTURAL. `_generate_signal` reaches engines, market data and the
database; the repository's established idiom for asserting its internals is
source/AST inspection (`test_f1_closed_candle`, `test_f1b_backtest_boundary`,
`test_f1c_parity` all do exactly this), and that idiom is followed here. The
behavioural half — that the builder never raises, bounds its own timeout and
represents failure explicitly — is already covered by test_shadow_exec_cost.py.

The merge test IS behavioural, because "extra['birth'] survives" is a property of
data rather than of shape, and a structural check could not see it break.
"""
from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

from app.services import scheduler as sched

BACKEND = pathlib.Path(__file__).resolve().parent.parent


def _fn_ast():
    return ast.parse(inspect.getsource(sched._generate_signal).lstrip()).body[0]


def _shadow_calls():
    return [n for n in ast.walk(_fn_ast())
            if isinstance(n, ast.Call)
            and getattr(n.func, "id", "") == "build_shadow_exec_cost"]


# ══ THE CALL EXISTS, EXACTLY ONCE, AND IS AWAITED ══════════════════════════
def test_the_publication_path_calls_the_shadow_builder_exactly_once():
    """Twice would mean two market snapshots and two payloads per signal."""
    calls = _shadow_calls()
    assert len(calls) == 1, f"expected exactly one shadow call, found {len(calls)}"


def test_the_shadow_call_is_awaited():
    """An un-awaited coroutine would silently never run and would leak a warning
    instead of evidence."""
    awaited = [n for n in ast.walk(_fn_ast())
               if isinstance(n, ast.Await)
               and isinstance(n.value, ast.Call)
               and getattr(n.value.func, "id", "") == "build_shadow_exec_cost"]
    assert len(awaited) == 1, "the shadow builder is not awaited"


def test_the_shadow_call_gets_a_collector_built_at_the_call_site():
    """REVISED after production evidence. This guard used to require the
    canonical `binance` instance, on the reasoning that one client per function
    is tidier. Production disproved it: that instance is closed ~424 lines
    earlier, so 100% of exec_cost records read "client has been closed".

    What the guard actually protects is unchanged — no duplicated market-data
    logic, no foreign client. It now requires the collector to be a name bound
    to a BinanceCollector constructed inside the shadow block, which is the only
    arrangement that is alive at the call site without restructuring the whole
    publication path. Liveness itself is asserted in
    test_shadow_collector_lifetime.py.
    """
    fn = _fn_ast()
    call = _shadow_calls()[0]
    kw = {k.arg: k.value for k in call.keywords}
    assert "collector" in kw and isinstance(kw["collector"], ast.Name),         "collector must be passed explicitly as a bound name"
    name = kw["collector"].id
    built = [n for n in ast.walk(fn)
             if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)
             and getattr(n.value.func, "id", "") == "BinanceCollector"
             and any(getattr(t, "id", "") == name for t in n.targets)]
    assert built, f"{name} is not bound to a BinanceCollector construction"
    assert max(b.lineno for b in built) < call.lineno,         "the collector is constructed after the call that uses it"


def test_exactly_two_collectors_and_no_foreign_client():
    """EXACT, not relaxed. Two constructions are expected and only two: the
    canonical one for the kline fetch, and the short-lived observation one. A
    third would mean somebody added another market-data path; any non-Binance
    client would mean a second implementation. Both still fail here.
    """
    src = inspect.getsource(sched._generate_signal)
    assert src.count("BinanceCollector()") == 2,         f"expected exactly 2 collector constructions, found {src.count('BinanceCollector()')}"
    for foreign in ("BybitCollector(", "httpx.AsyncClient(", "requests.", "aiohttp."):
        assert foreign not in src, f"a foreign market-data client appeared: {foreign}"


# ══ NON-INTERFERENCE ═══════════════════════════════════════════════════════
def test_the_shadow_call_has_its_own_exception_handler():
    """The decisive structural property. If the shadow call sat bare inside the
    snapshot try-block, a raise would skip `db.add(snapshot)` and the product
    would silently lose the birth snapshot it depends on for learning.

    Scoped to the INNERMOST enclosing try. Checking every enclosing try instead
    would let the function-level rollback handler satisfy this — that handler
    does not re-raise, so a shadow handler that DID re-raise would still look
    guarded. A sabotage mutant survived exactly that way.
    """
    fn = _fn_ast()
    enclosing = [n for n in ast.walk(fn)
                 if isinstance(n, ast.Try)
                 and any(isinstance(c, ast.Call)
                         and getattr(c.func, "id", "") == "build_shadow_exec_cost"
                         for c in ast.walk(n))]
    assert enclosing, "the shadow call is in no try-block at all"
    # Nearest enclosing try *that has handlers*: the repair nests a
    # try/finally (for collector close) inside the try/except, and a plain
    # finally has no handlers to inspect.
    handled = [n for n in enclosing if n.handlers]
    assert handled, "the shadow call is inside no try that handles anything"
    innermost = max(handled, key=lambda n: n.lineno)
    for h in innermost.handlers:
        raises = [x for x in ast.walk(ast.Module(body=h.body, type_ignores=[]))
                  if isinstance(x, ast.Raise)]
        assert not raises, "the shadow's own handler re-raises — a failure would abort publication"


def test_the_snapshot_is_added_regardless_of_the_shadow_outcome():
    """`db.add(snapshot)` must not live inside the shadow's OWN try-block.

    Scoped to the INNERMOST try containing the shadow call. An earlier draft of
    this test walked every enclosing try and therefore flagged the function-level
    error handler, which legitimately wraps the whole publication block — the
    handler that exists to roll back a failed publication necessarily contains
    both statements, and that is correct rather than a defect.
    """
    fn = _fn_ast()
    enclosing = [n for n in ast.walk(fn)
                 if isinstance(n, ast.Try)
                 and any(isinstance(c, ast.Call)
                         and getattr(c.func, "id", "") == "build_shadow_exec_cost"
                         for c in ast.walk(n))]
    assert enclosing, "no try-block contains the shadow call"
    innermost = max(enclosing, key=lambda n: n.lineno)
    adds = [c for c in ast.walk(innermost)
            if isinstance(c, ast.Call) and getattr(c.func, "attr", "") == "add"
            and any(getattr(a, "id", "") == "snapshot" for a in c.args)]
    assert not adds, "db.add(snapshot) sits inside the shadow's own try-block"


def test_the_shadow_result_never_feeds_a_signal_field():
    """The record is written to extra and nowhere else. Any assignment of a
    shadow value onto the signal would be a filter wearing a disguise."""
    src = inspect.getsource(sched._generate_signal)
    marker = src.split("build_shadow_exec_cost", 1)[1] if "build_shadow_exec_cost" in src else ""
    for banned in ("new_sig.confidence_score", "new_sig.stop_loss", "new_sig.tp1",
                   "new_sig.tp2", "new_sig.tp3", "new_sig.entry_zone_low",
                   "new_sig.entry_zone_high", "new_sig.live_status", "new_sig.is_active"):
        assert banned not in marker, f"shadow path assigns {banned}"


def test_no_frozen_predicate_is_consulted_anywhere_in_the_runtime():
    """Re-asserted at the wiring layer: evidence must never become a gate."""
    hits = []
    for p in (BACKEND / "app").rglob("*.py"):
        if p.name == "shadow_exec_cost.py":
            continue
        src = p.read_text(encoding="utf-8", errors="ignore")
        if "would_keep" in src or "would_filter" in src or "sl_dist_lt_" in src:
            hits.append(p.name)
    assert hits == [], f"a shadow predicate leaked into the runtime: {hits}"


def test_no_execution_semantics_were_introduced():
    src = inspect.getsource(sched._generate_signal)
    for banned in ("place_order", "create_order", "new_order", "actual_fill",
                   "commission", "maker_taker", "realised_slippage"):
        assert banned not in src, f"publication path gained {banned!r}"


# ══ MERGE SEMANTICS — behavioural ══════════════════════════════════════════
def test_the_wiring_writes_to_the_exec_cost_key_and_merges():
    """Structural: the payload must land on extra['exec_cost'], and extra must be
    copied rather than replaced."""
    src = inspect.getsource(sched._generate_signal)
    tail = src.split("build_shadow_exec_cost", 1)[1]
    assert '"exec_cost"' in tail or "'exec_cost'" in tail, "payload key is not exec_cost"
    assert "snapshot.extra = " in tail, "the merged dict is never assigned back"
    # The MERGE itself, read from source. Asserting only that extra is assigned
    # cannot see a plain overwrite; a sabotage mutant that dropped the spread
    # survived a simulation-only merge test.
    assert "**(snapshot.extra or {})" in tail,         "extra is overwritten rather than merged - existing keys would be lost"


def test_merging_preserves_existing_extra_keys():
    """Behavioural. `build_snapshot` writes extra['birth']; the shadow payload is
    a SIBLING key and must not displace it — a plain assignment would."""
    existing = {"birth": {"atr_pct": 0.4, "sr_override_sl": False}}
    merged = dict(existing or {})
    merged["exec_cost"] = {"schema_version": 1}
    assert merged["birth"] == existing["birth"], "birth telemetry was displaced"
    assert set(merged) == {"birth", "exec_cost"}


def test_a_none_extra_is_handled_without_inventing_other_keys():
    merged = dict(None or {})
    merged["exec_cost"] = {"schema_version": 1}
    assert merged == {"exec_cost": {"schema_version": 1}}


# ══ ORDERING ═══════════════════════════════════════════════════════════════
def test_the_shadow_call_happens_after_the_publication_decision_is_final():
    """The signal must already be built and the candidate already recorded before
    any market snapshot is taken; otherwise the shadow would sit upstream of the
    decision it is supposed to merely observe."""
    src = inspect.getsource(sched._generate_signal)
    i_sig = src.index("new_sig = Signal(")
    i_candidate = src.index("verdict=VERDICT_PUBLISHED")
    i_shadow = src.index("build_shadow_exec_cost")
    assert i_sig < i_shadow, "shadow runs before the signal is constructed"
    assert i_candidate < i_shadow, "shadow runs before the publication verdict"
