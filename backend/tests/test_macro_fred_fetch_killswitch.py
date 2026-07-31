"""CP-MACRO-FRED-FETCH-KILLSWITCH — the gate between a stored key and a real call.

Until this shipped, `FRED_API_KEY` was BOTH the credential and the on-switch: the
collector's only guard was `if not self._fred_key`, so writing the key into
.env.production would have restarted real FRED traffic on every candidate.
Measured on 7 239 live candidates (2026-07-31): macro's confidence goes 25.0 →
70.0, which is exactly +5.0 on the unweighted nine-engine mean, carrying 2 964
candidates over the 65 publish gate (33.1% → 74.0%) — 121 of them
engine-actionable, ~26/day newly published. Storing a credential must not move a
gate.

The tests are organised around four claims.

  1. With the flag OFF, a stored key is indistinguishable from no key on every
     code path — not merely in the result, but in the `_note` statuses, the
     snapshot dict and the cache. That is why the gate NEUTRALISES the key
     instead of adding a second condition beside each `if not self._fred_key`:
     one state, not three.

  2. Nothing about key presence reaches an HTTP response. `GET /macro/snapshot`
     serves the snapshot dict verbatim, so `fred_key_present` is instance state
     and a test pins it out of every returned mapping.

  3. The default is OFF, and it is off in the settings class itself — not merely
     absent from the environment.

  4. Telemetry stops lying: with a key stored and the fetch off, the reason is
     `fetch_disabled`, not `no_api_key`. It is a `fallback_reason`, never a
     `fetch_status`, so `worst_status`'s severity ordering is untouched.

No network: every test that could reach FRED runs with httpx armed to raise.
"""
import ast
import asyncio
import inspect
from pathlib import Path

import pandas as pd
import pytest

from app.collectors import macro_collector as mc
from app.collectors.macro_collector import FRED_FETCH_DISABLED_REASON, MacroCollector
from app.config import Settings
from app.engines.base import SignalBias
from app.engines.macro import engine as macro_engine_module
from app.engines.macro.engine import MacroEngine

BACKEND = Path(__file__).resolve().parents[1]
SERIES = ("FEDFUNDS", "CPIAUCSL", "DGS10", "DTWEXBGS")


class _Armed(BaseException):
    """Raised by any outbound call that must be impossible while the gate is shut.

    A `BaseException`, deliberately: `fetch_fred_series` wraps its request in a
    broad `except Exception` that returns None, so an ordinary exception would be
    SWALLOWED — the gate-open test would report "did not raise", and every
    gate-shut test would pass whether or not a call had actually been attempted.
    This subclass cannot be caught by that handler, so a request either happens
    and the test knows, or it does not happen at all.
    """


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Every test in this file runs with the transport armed to explode."""
    def boom(*a, **k):
        raise _Armed("outbound call attempted")

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "get", boom)
    monkeypatch.setattr(httpx.AsyncClient, "post", boom)
    monkeypatch.setattr(httpx.AsyncClient, "request", boom)
    return True


@pytest.fixture(autouse=True)
def clean_cache():
    """The module caches FRED values globally; a leaked entry would let a later
    test read a value the gate should have prevented."""
    mc._MACRO_CACHE.clear()
    mc._MACRO_CACHE_EXPIRY.clear()
    yield
    mc._MACRO_CACHE.clear()
    mc._MACRO_CACHE_EXPIRY.clear()


def _collector(monkeypatch, *, key, enabled):
    """A collector built against an explicit (key, flag) pair. The key is a
    non-secret placeholder — no real credential is ever used in tests."""
    class _S:
        FRED_API_KEY = key
        MACRO_FRED_FETCH_ENABLED = enabled
    monkeypatch.setattr(mc, "get_settings", lambda: _S())
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    return MacroCollector()


PLACEHOLDER = "not-a-real-key-000"


# ══════════════════════════════════════════════════════════════════════════════
# 1 · THE DEFAULT IS OFF
# ══════════════════════════════════════════════════════════════════════════════
def test_the_flag_defaults_to_off_in_the_settings_class():
    """Not "absent from this environment" — off in the declaration, so a fresh
    deploy anywhere cannot fetch."""
    assert Settings.model_fields["MACRO_FRED_FETCH_ENABLED"].default is False


def test_the_flag_is_a_bool_not_a_string():
    assert Settings.model_fields["MACRO_FRED_FETCH_ENABLED"].annotation is bool


def test_todays_production_shape_is_no_key_and_no_fetch(monkeypatch):
    c = _collector(monkeypatch, key="", enabled=False)
    assert c.fred_key_present is False
    assert c.fred_fetch_enabled is False
    assert c._fred_key == ""


# ══════════════════════════════════════════════════════════════════════════════
# 2 · THE GATE — a stored key with the flag off behaves as no key at all
# ══════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("key,enabled,expect_present,expect_usable", [
    ("",             False, False, False),
    ("",             True,  False, False),
    (PLACEHOLDER,    False, True,  False),      # THE new state
    (PLACEHOLDER,    True,  True,  True),
    ("   ",          False, False, False),      # whitespace is not a key
    ("   ",          True,  False, False),
])
def test_presence_and_usability_are_separate_facts(monkeypatch, key, enabled,
                                                   expect_present, expect_usable):
    c = _collector(monkeypatch, key=key, enabled=enabled)
    assert c.fred_key_present is expect_present
    assert bool(c._fred_key) is expect_usable


def test_a_stored_key_with_the_gate_shut_takes_the_no_key_path(monkeypatch):
    """The load-bearing test. Same statuses, same dict, same absence of traffic."""
    shut = _collector(monkeypatch, key=PLACEHOLDER, enabled=False)
    none = _collector(monkeypatch, key="", enabled=False)
    a = asyncio.run(shut.fetch_us_macro_snapshot())
    b = asyncio.run(none.fetch_us_macro_snapshot())
    assert a == b
    assert a == {"fed_funds_rate": None, "cpi": None, "ten_year_yield": None,
                 "usd_broad_index": None, "configured": False}
    assert shut.last_status == none.last_status
    assert set(shut.last_status) == {f"fred_{s}" for s in SERIES}
    assert all(v["fetch_status"] == "not_configured"
               for v in shut.last_status.values())


def test_no_series_call_escapes_the_gate(monkeypatch):
    c = _collector(monkeypatch, key=PLACEHOLDER, enabled=False)
    for series in SERIES:
        assert asyncio.run(c.fetch_fred_series(series)) is None
    assert mc._MACRO_CACHE == {}


def test_the_gate_holds_with_the_transport_armed(monkeypatch):
    """`_Armed` never fires — proved by the call completing, not by inspection."""
    c = _collector(monkeypatch, key=PLACEHOLDER, enabled=False)
    assert asyncio.run(c.fetch_us_macro_snapshot())["configured"] is False


def test_opening_the_gate_would_reach_the_transport(monkeypatch):
    """The mirror image: with the flag ON the code DOES try to call out. Without
    this, every test above would pass just as well against a collector that can
    no longer fetch at all — which is not the property being claimed."""
    c = _collector(monkeypatch, key=PLACEHOLDER, enabled=True)
    assert c._fred_key == PLACEHOLDER
    with pytest.raises(_Armed):
        asyncio.run(c.fetch_fred_series("FEDFUNDS"))


def test_the_gate_is_the_only_thing_standing_between_a_key_and_a_call(monkeypatch):
    """Named for what it protects: flip ONLY the flag and traffic starts."""
    shut = _collector(monkeypatch, key=PLACEHOLDER, enabled=False)
    asyncio.run(shut.fetch_us_macro_snapshot())          # silent
    open_ = _collector(monkeypatch, key=PLACEHOLDER, enabled=True)
    with pytest.raises(_Armed):
        asyncio.run(open_.fetch_us_macro_snapshot())


# ══════════════════════════════════════════════════════════════════════════════
# 3 · NO SECRET-CONFIGURATION STATE ON ANY RETURNED MAPPING
# ══════════════════════════════════════════════════════════════════════════════
def test_key_presence_never_appears_in_the_snapshot_dict(monkeypatch):
    """`GET /api/v1/macro/snapshot` returns this dict verbatim
    (api/routes/macro.py:28-33)."""
    for enabled in (False, True):
        c = _collector(monkeypatch, key=PLACEHOLDER, enabled=enabled)
        if enabled:
            continue                     # the open path is covered above
        snap = asyncio.run(c.fetch_us_macro_snapshot())
        for banned in ("fred_key_present", "key_present", "fetch_enabled",
                       "MACRO_FRED_FETCH_ENABLED", "FRED_API_KEY"):
            assert banned not in snap, banned
        assert PLACEHOLDER not in str(snap)


SNAPSHOT_KEYS = {"fed_funds_rate", "cpi", "ten_year_yield", "usd_broad_index",
                 "configured"}


def test_the_snapshot_keys_are_exactly_what_they_were_gate_shut(monkeypatch):
    c = _collector(monkeypatch, key=PLACEHOLDER, enabled=False)
    assert set(asyncio.run(c.fetch_us_macro_snapshot())) == SNAPSHOT_KEYS


def test_the_snapshot_keys_are_exactly_what_they_were_gate_open(monkeypatch):
    """`fetch_us_macro_snapshot` has TWO return statements and they are different
    literals. Checking only the early return leaves the branch that actually runs
    once fetching is enabled — the one where a leak would matter most — untested.
    A sabotage that added `fetch_enabled` to the configured branch passed the
    shut-path check alone.
    """
    c = _collector(monkeypatch, key=PLACEHOLDER, enabled=True)

    async def _stub(series_id):
        return 4.25
    monkeypatch.setattr(c, "fetch_fred_series", _stub)
    snap = asyncio.run(c.fetch_us_macro_snapshot())
    assert set(snap) == SNAPSHOT_KEYS
    assert snap["configured"] is True
    for banned in ("fred_key_present", "key_present", "fetch_enabled",
                   "MACRO_FRED_FETCH_ENABLED", "FRED_API_KEY"):
        assert banned not in snap, banned
    assert PLACEHOLDER not in str(snap)


def test_both_snapshot_branches_return_the_same_key_set():
    """Asserted on the SOURCE too, so the two literals cannot drift apart in a
    way the two tests above happen not to reach."""
    tree = ast.parse((BACKEND / "app" / "collectors" / "macro_collector.py")
                     .read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef)
              and n.name == "fetch_us_macro_snapshot")
    returns = [n.value for n in ast.walk(fn)
               if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict)]
    assert len(returns) == 2, len(returns)
    for dict_node in returns:
        keys = {k.value for k in dict_node.keys if isinstance(k, ast.Constant)}
        assert keys == SNAPSHOT_KEYS, keys


def test_the_macro_route_still_serves_the_snapshot_verbatim():
    """If this ever stops being true the test above stops protecting anything."""
    src = (BACKEND / "app" / "api" / "routes" / "macro.py").read_text(encoding="utf-8")
    assert '"united_states": us' in src
    for banned in ("fred_key_present", "fred_fetch_enabled", "FRED_API_KEY",
                   "MACRO_FRED_FETCH_ENABLED"):
        assert banned not in src, banned


def test_no_api_route_reads_the_flag_or_the_key():
    for path in (BACKEND / "app" / "api").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for banned in ("FRED_API_KEY", "MACRO_FRED_FETCH_ENABLED",
                       "fred_key_present", "_fred_key"):
            assert banned not in text, f"{path.relative_to(BACKEND)}: {banned}"


KEY_BEARING_NAMES = {"raw_key", "_fred_key", "FRED_API_KEY"}


def _mentions_the_key(node):
    """Does this expression reference anything that carries the credential?"""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id in KEY_BEARING_NAMES:
            return True
        if isinstance(sub, ast.Attribute) and sub.attr in KEY_BEARING_NAMES:
            return True
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str) \
                and sub.value in KEY_BEARING_NAMES:
            return False        # the NAME as a lookup string is fine
    return False


def test_no_log_call_anywhere_receives_the_key():
    """Structural, not a pattern blacklist.

    The first version banned specific spellings (`logger.info(self._fred_key`,
    `str(self._fred_key)`, …). A sabotage that wrote
    `logger.info("fred key %s", str(raw_key))` walked straight past it — a
    different local, a different shape. This walks every `logger.*` call in the
    module and rejects any argument that references a key-bearing name at all,
    so renaming the variable or reformatting the message cannot dodge it.
    """
    tree = ast.parse((BACKEND / "app" / "collectors" / "macro_collector.py")
                     .read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_log = (isinstance(func, ast.Attribute)
                  and isinstance(func.value, ast.Name)
                  and func.value.id == "logger")
        is_print = isinstance(func, ast.Name) and func.id == "print"
        if not (is_log or is_print):
            continue
        for arg in list(node.args) + [kw.value for kw in node.keywords]:
            if _mentions_the_key(arg):
                offenders.append(ast.unparse(node)[:100])
    assert offenders == [], offenders


def test_the_key_is_never_measured_or_digested():
    """Length, prefix and hash are all disclosure. Only the boolean may exist."""
    tree = ast.parse((BACKEND / "app" / "collectors" / "macro_collector.py")
                     .read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in {"len", "str", "repr", "hash", "print"}:
            if any(_mentions_the_key(a) for a in node.args):
                offenders.append(ast.unparse(node)[:100])
        if isinstance(node, ast.Subscript) and _mentions_the_key(node.value):
            offenders.append(ast.unparse(node)[:100])
    assert offenders == [], offenders
    assert "hashlib" not in _code_only(mc)


def test_only_a_boolean_is_derived_from_the_key():
    """`fred_key_present` is the ONE fact the rest of the system may learn."""
    assert "self.fred_key_present = bool(raw_key)" in _code_only(mc)


def _code_only(obj):
    tree = ast.parse(inspect.getsource(obj))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)) and ast.get_docstring(node):
            node.body = node.body[1:]
    return ast.unparse(tree)


# ══════════════════════════════════════════════════════════════════════════════
# 4 · TELEMETRY TELLS THE TRUTH — and only telemetry moves
# ══════════════════════════════════════════════════════════════════════════════
def _df(n=60):
    idx = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")
    close = [100.0 + i * 0.3 for i in range(n)]
    return pd.DataFrame({"open": close, "high": [c * 1.01 for c in close],
                         "low": [c * 0.99 for c in close], "close": close,
                         "volume": [1000.0] * n}, index=idx)


class _FakeCollector:
    """Stands in for MacroCollector. No network, explicit gate state."""
    key_present = False

    def __init__(self):
        self.last_status = {f"fred_{s}": {"fetch_status": "not_configured",
                                          "served_from_cache": False,
                                          "data_freshness_s": None} for s in SERIES}
        self.fred_key_present = _FakeCollector.key_present
        self.fred_fetch_enabled = False

    async def fetch_us_macro_snapshot(self):
        return {"fed_funds_rate": None, "cpi": None, "ten_year_yield": None,
                "usd_broad_index": None, "configured": False}

    async def fetch_tcmb_usd_try(self):
        return None

    async def close(self):
        return None


def _run_engine(monkeypatch, *, key_present):
    _FakeCollector.key_present = key_present
    monkeypatch.setattr(macro_engine_module, "MacroCollector", _FakeCollector)
    eng = MacroEngine()
    result = asyncio.run(eng.analyze("BTCUSDT", "1h", _df()))
    return result, eng._dependency_health


def test_a_stored_key_with_the_gate_shut_reports_fetch_disabled(monkeypatch):
    """`no_api_key` would be a FALSE record once a key is stored."""
    _, health = _run_engine(monkeypatch, key_present=True)
    assert health["fallback_reason"] == FRED_FETCH_DISABLED_REASON == "fetch_disabled"
    assert health["configured"] is False


def test_no_key_still_reports_no_api_key(monkeypatch):
    """Today's production state — unchanged, byte for byte."""
    _, health = _run_engine(monkeypatch, key_present=False)
    assert health["fallback_reason"] == "no_api_key"


def test_the_engine_result_is_identical_either_way(monkeypatch):
    """THE decision-isolation claim. Only `fallback_reason` may differ, and that
    lives on the instance channel which never enters EngineResult."""
    a, ha = _run_engine(monkeypatch, key_present=False)
    b, hb = _run_engine(monkeypatch, key_present=True)
    assert a.model_dump() == b.model_dump()
    assert (a.score, a.bias, a.confidence) == (50.0, SignalBias.NEUTRAL, 25.0)
    assert ha["fallback_reason"] != hb["fallback_reason"]
    assert {k: v for k, v in ha.items() if k != "fallback_reason"} == \
           {k: v for k, v in hb.items() if k != "fallback_reason"}


def test_the_reason_is_not_a_fetch_status(monkeypatch):
    """A new `fetch_status` would enter `worst_status`'s fixed severity
    precedence, and "switched off" is not a severity."""
    from app.services import dependency_health as dh
    assert FRED_FETCH_DISABLED_REASON not in (
        dh.OK, dh.NOT_CONFIGURED, dh.TIMEOUT, dh.NETWORK_ERROR, dh.PARSE_ERROR,
        dh.EMPTY, dh.STALE_CACHE, dh.INTERNAL_ERROR, dh.NOT_APPLICABLE)
    src = inspect.getsource(dh.worst_status)
    assert FRED_FETCH_DISABLED_REASON not in src
    _, health = _run_engine(monkeypatch, key_present=True)
    assert health["fetch_status"] == "not_configured"       # unchanged
    assert all(v == "not_configured" for v in health["components"].values())


def test_the_engine_never_reads_the_flag_itself():
    """One gate, in one place. A second condition in the engine would be a second
    thing to get wrong."""
    code = _code_only(macro_engine_module)
    for banned in ("MACRO_FRED_FETCH_ENABLED", "fred_fetch_enabled", "_fred_key",
                   "FRED_API_KEY", "get_settings"):
        assert banned not in code, banned


def test_the_collector_reads_the_flag_exactly_once():
    code = _code_only(mc)
    assert code.count("MACRO_FRED_FETCH_ENABLED") == 1
    assert code.count("self._fred_key = ") == 1


def test_nothing_outside_the_collector_touches_the_key(monkeypatch):
    """`_fred_key` is private to the collector; a second reader or writer would
    reopen the hole this checkpoint closed.

    Scanned on CODE: config.py's comment legitimately QUOTES the old
    `if not self._fred_key` guard when explaining why the flag exists, and a
    substring scan cannot tell an explanation from a reference.
    """
    touchers = []
    for path in (BACKEND / "app").rglob("*.py"):
        if "__pycache__" in path.parts or path.name == "macro_collector.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)) and ast.get_docstring(node):
                node.body = node.body[1:]
        if "_fred_key" in ast.unparse(tree):
            touchers.append(path.relative_to(BACKEND).as_posix())
    assert touchers == [], touchers
