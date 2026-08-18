"""CP-F2 — the collector handed to the shadow capture must be ALIVE.

THE DEFECT THIS EXISTS FOR. The first deployment wired the shadow call to the
canonical `binance` instance, and every record it produced in production read
`market.ok = false` with "Cannot send a request, as the client has been closed."
The collector is created at the top of `_generate_signal`, used for one kline
fetch, and closed in a `finally` eleven lines later; the shadow call sits ~424
lines further on. Nothing was wrong with the identifier — `collector=binance` was
genuinely the in-scope name — so the AST guard passed while the feature collected
nothing at all.

WHY THE OLD GUARDS COULD NOT SEE IT. They asserted shape: that a name was passed,
that it was not a fresh construction. Liveness is not a property of the name, it
is a property of the object at the moment of the call, and every unit test
injected a freshly-built fake. The lesson is recorded in the repository because
it generalises: structural correctness is not working integration.

WHAT IS ASSERTED HERE. First, behaviourally against the REAL collector class,
that a closed client produces exactly the failure production saw — so the failure
mode stays reproducible rather than becoming folklore. Second, that on the path
which reaches the shadow call, no close of the collector being passed has already
executed. The second is a control-flow property of the real function, not an
identifier match, and it is what fails on the broken bytes.
"""
from __future__ import annotations

import ast
import inspect

import pytest

from app.collectors.binance_collector import BinanceCollector
from app.services import scheduler as sched
from app.services.shadow_exec_cost import build_shadow_exec_cost


class _Sig:
    entry_zone_low = 100.0
    entry_zone_high = 101.0
    stop_loss = 99.0
    tp1, tp2, tp3 = 103.0, 105.0, 108.0
    confidence_score = 70.0
    timeframe = "M15"
    direction = "BULLISH"


# ══ THE PRODUCTION FAILURE, REPRODUCED AGAINST THE REAL CLASS ══════════════
@pytest.mark.asyncio
async def test_a_closed_real_collector_reproduces_the_production_failure():
    """Not a fake: the actual BinanceCollector, actually closed. This is the
    exact record production wrote, and it must keep being recognisable."""
    c = BinanceCollector()
    await c.close()

    rec = await build_shadow_exec_cost(collector=c, symbol="BTCUSDT",
                                       signal=_Sig(), atr_pct=0.4)
    assert rec["market"]["ok"] is False
    assert "closed" in rec["market"]["failure_reason"].lower(), \
        rec["market"]["failure_reason"]
    assert rec["market"]["spread_pct"] is None
    # Fail-open is unaffected by the defect: evidence is still produced.
    assert rec["predicates"] and rec["provenance"]["bid"] == "MEASURED"


@pytest.mark.asyncio
async def test_a_live_real_collector_is_not_reported_as_closed():
    """The complement. Without this, a mutant that always reports 'closed'
    would satisfy the test above."""
    c = BinanceCollector()
    try:
        rec = await build_shadow_exec_cost(collector=c, symbol="BTCUSDT",
                                           signal=_Sig(), atr_pct=0.4)
    finally:
        await c.close()
    reason = (rec["market"]["failure_reason"] or "")
    assert "has been closed" not in reason, reason


# ══ THE LIFETIME SEAM — this is what fails on the broken bytes ═════════════
def _collector_closed_before_shadow_call() -> bool:
    """Does a close() of the object passed to the shadow call already execute
    before that call, on the path that reaches it?

    Control flow, not identifier matching. The function body is walked in
    source order; a `close()` on the same name that is later handed to
    `build_shadow_exec_cost` counts as a prior close only if it appears earlier
    AND that name is not rebound in between.
    """
    fn = ast.parse(inspect.getsource(sched._generate_signal).lstrip()).body[0]

    shadow = [n for n in ast.walk(fn)
              if isinstance(n, ast.Call)
              and getattr(n.func, "id", "") == "build_shadow_exec_cost"]
    assert len(shadow) == 1, "expected exactly one shadow call"
    passed = {k.value.id for k in shadow[0].keywords
              if k.arg == "collector" and isinstance(k.value, ast.Name)}
    if not passed:
        return False                     # constructed inline -> cannot be stale
    name = passed.pop()
    shadow_line = shadow[0].lineno

    closes = [n.lineno for n in ast.walk(fn)
              if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "close"
              and isinstance(getattr(n.func, "value", None), ast.Name)
              and n.func.value.id == name and n.lineno < shadow_line]
    if not closes:
        return False
    # A rebinding of the same name after the close would revive it.
    rebinds = [n.lineno for n in ast.walk(fn)
               if isinstance(n, ast.Assign)
               and any(getattr(t, "id", "") == name for t in n.targets)
               and min(closes) < n.lineno < shadow_line]
    return not rebinds


def test_the_collector_handed_to_the_shadow_call_has_not_already_been_closed():
    """THE RED TEST. On the broken bytes this is True: `binance.close()` runs in
    a finally at relative line 11 and the shadow call at ~435 receives that same,
    dead object. Any repair must make it False — either by giving the call a
    collector closed only afterwards, or by handing it one that is constructed
    fresh at the call site."""
    assert not _collector_closed_before_shadow_call(), (
        "the shadow call receives a collector whose client is already closed - "
        "this is the defect that made every production exec_cost record "
        "market.ok=false")


def test_every_collector_the_function_builds_is_closed_on_some_path():
    """No leak. Each `BinanceCollector()` construction must be matched by at
    least one close() of the name it is bound to."""
    src = inspect.getsource(sched._generate_signal)
    fn = ast.parse(src.lstrip()).body[0]
    built = {}
    for n in ast.walk(fn):
        if (isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)
                and getattr(n.value.func, "id", "") == "BinanceCollector"):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    built[t.id] = n.lineno
    assert built, "no collector is constructed"
    closed = {n.func.value.id for n in ast.walk(fn)
              if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "close"
              and isinstance(getattr(n.func, "value", None), ast.Name)}
    leaked = sorted(set(built) - closed)
    assert not leaked, f"collector(s) constructed but never closed: {leaked}"


def test_every_constructed_collector_is_closed_in_a_finally():
    """Not merely "closed somewhere" — closed on a guaranteed path. An exchange
    error during the shadow capture must not leak an httpx client on every
    published signal, and a close that only runs on the happy path would."""
    fn = ast.parse(inspect.getsource(sched._generate_signal).lstrip()).body[0]
    built = {t.id for n in ast.walk(fn)
             if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)
             and getattr(n.value.func, "id", "") == "BinanceCollector"
             for t in n.targets if isinstance(t, ast.Name)}
    assert built, "no collector is constructed"
    finally_closed = set()
    for t in ast.walk(fn):
        if isinstance(t, ast.Try) and t.finalbody:
            for n in ast.walk(ast.Module(body=t.finalbody, type_ignores=[])):
                if (isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "close"
                        and isinstance(getattr(n.func, "value", None), ast.Name)):
                    finally_closed.add(n.func.value.id)
    missing = sorted(built - finally_closed)
    assert not missing, f"collector(s) not closed in a finally: {missing}"
