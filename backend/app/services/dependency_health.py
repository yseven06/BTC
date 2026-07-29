"""Dependency health telemetry — CP-DEP-HEALTH-1.

WHY THIS EXISTS
---------------
CP-OPERATIONAL-COUPLING-FORENSIC measured that an infrastructure state changes
signal decisions materially and leaves no trace. On the frozen 12 539-candidate
cohort, `macro_analysis` ran with **zero** data components on 100% of rows
(`FRED_API_KEY` unset), which costs every candidate 4.85 points of final
confidence and drops 250 of the 788 gate-passing candidates below the 65 gate.
None of that is recoverable from the candidate log: `engine_scores` persists only
`{score, bias, confidence}`, and the engine's own `warnings` — the one place the
distinction lives — are never written.

Worse, the failure paths disagree with each other about direction. A data-source
outage lowers confidence (fail-closed); an MTF fetch failure returns "neutral",
which REMOVES a penalty (fail-open). Both are silent.

WHAT THIS IS — AND IS NOT
-------------------------
This module is pure bookkeeping. It records what the infrastructure did; it never
decides anything. Nothing in the decision path reads any value produced here, and
every producer is wrapped so that a telemetry failure cannot reach the decision.

It does NOT: add retries, change a timeout, change a cache TTL, change what any
collector returns, change any fallback value, or touch the confidence formula.

HONESTY ABOUT PRECISION
-----------------------
`classify_exception` reports a *supertype* wherever the code genuinely cannot
tell two causes apart, rather than inventing precision:

  * `http_429` / `http_5xx` / `http_4xx` are exact — but ONLY on call sites that
    invoke `raise_for_status()`. Every instrumented site does.
  * `timeout` is exact (`httpx.TimeoutException` covers connect/read/write/pool);
    the four sub-kinds are NOT separated, because no caller distinguishes them.
  * `network_error` is the honest supertype for every other transport failure
    (DNS, connection reset, protocol, proxy). It is not narrowed further.
  * `parse_error` covers "the body was not the shape we expected", which includes
    a JSON decode failure and a KeyError/TypeError while navigating the payload.
    These are not separated because the collectors do not separate them.
  * `internal_error` is the catch-all. If it appears, the classifier saw
    something none of the branches above matched — treat it as unclassified, not
    as a diagnosis.

No exception message, response body, URL or header is recorded anywhere in this
module. Only the exception's TYPE and, for HTTP errors, the numeric status code.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Iterable, Optional

DEPENDENCY_HEALTH_VERSION = "dependency_health_v1"

# ── fetch_status vocabulary ────────────────────────────────────────────────
OK = "ok"
NOT_CONFIGURED = "not_configured"
TIMEOUT = "timeout"
HTTP_429 = "http_429"
HTTP_5XX = "http_5xx"
HTTP_4XX = "http_4xx"          # not in the original design note; 4xx that is
                               # not 429 is a real, distinct and exactly known
                               # state, and folding it into 429 would be a lie.
NETWORK_ERROR = "network_error"
PARSE_ERROR = "parse_error"
EMPTY = "empty"
STALE_CACHE = "stale_cache"
INTERNAL_ERROR = "internal_error"
NOT_APPLICABLE = "not_applicable"   # the dependency is not consulted for this
                                    # asset class at all (e.g. TCMB FX on crypto)

_FAILURE_STATUSES = frozenset({
    NOT_CONFIGURED, TIMEOUT, HTTP_429, HTTP_5XX, HTTP_4XX,
    NETWORK_ERROR, PARSE_ERROR, EMPTY, STALE_CACHE, INTERNAL_ERROR,
})

# ── confidence_semantic_type vocabulary ────────────────────────────────────
CONVICTION = "conviction"
DATA_AVAILABILITY = "data_availability"
ENGINE_DEFAULT = "engine_default"
MIXED = "mixed"
UNKNOWN = "unknown"

# What each engine's `confidence` actually measures, read off the engine source.
# Recorded so a later reader does not have to reverse-engineer the formula the
# way CP-CONFIDENCE-FORMULA-FORENSIC had to.
CONFIDENCE_SEMANTICS: Dict[str, str] = {
    # variance of its own four sub-scores — genuine internal agreement
    "technical_analysis": CONVICTION,
    # presence of structure events (trend / BOS-CHoCH / swing count)
    "market_structure": CONVICTION,
    "smart_money_concepts": CONVICTION,
    "candle_range_theory": CONVICTION,
    "volume_analysis": CONVICTION,
    # literally `confidence = 90.0`, "risk parameters are deterministic"
    "risk_management": ENGINE_DEFAULT,
    # literally `confidence = 80.0`, "fundamentals change slowly"
    "fundamental_analysis": ENGINE_DEFAULT,
    # min(40 + components * N, cap) — a count of how many fields arrived
    "onchain_analysis": DATA_AVAILABILITY,
    "macro_analysis": DATA_AVAILABILITY,
}


def classify_exception(exc: BaseException) -> str:
    """Map an exception to a fetch_status. Pure; reads no message text.

    Import of httpx is local so this module stays importable (and testable)
    without the HTTP stack, and so a missing httpx degrades to `internal_error`
    rather than raising inside a telemetry path.
    """
    try:
        import httpx
    except Exception:  # pragma: no cover — httpx is a hard dependency in prod
        return INTERNAL_ERROR

    if isinstance(exc, httpx.HTTPStatusError):
        code = getattr(getattr(exc, "response", None), "status_code", None)
        if code == 429:
            return HTTP_429
        if isinstance(code, int) and 500 <= code <= 599:
            return HTTP_5XX
        if isinstance(code, int) and 400 <= code <= 499:
            return HTTP_4XX
        return INTERNAL_ERROR
    # TimeoutException is a TransportError subclass — test it first or every
    # timeout would be reported as a generic network error.
    if isinstance(exc, httpx.TimeoutException):
        return TIMEOUT
    if isinstance(exc, httpx.TransportError):
        return NETWORK_ERROR
    if isinstance(exc, (ValueError, KeyError, TypeError, IndexError)):
        # json.JSONDecodeError subclasses ValueError; the rest are payload
        # navigation failures. The collectors do not tell them apart, so neither
        # does this.
        return PARSE_ERROR
    return INTERNAL_ERROR


def is_failure(status: Optional[str]) -> bool:
    return status in _FAILURE_STATUSES


def worst_status(statuses: Iterable[Optional[str]]) -> str:
    """The most severe status in a fan-out, by a fixed precedence.

    `fetch_btc_network` queries three endpoints and merges whatever came back,
    caching the partial result as if it had succeeded. Reporting only "ok"
    there would hide exactly the case this module exists to surface.
    """
    order = [INTERNAL_ERROR, HTTP_5XX, HTTP_429, HTTP_4XX, TIMEOUT,
             NETWORK_ERROR, PARSE_ERROR, STALE_CACHE, EMPTY, NOT_CONFIGURED,
             NOT_APPLICABLE, OK]
    seen = [s for s in statuses if s]
    if not seen:
        return OK
    for candidate in order:
        if candidate in seen:
            return candidate
    return OK


class StatusMemory:
    """Remembers what produced each cached value, so a cache hit can be honest.

    The collectors cache FAILURES (`_ONCHAIN_CACHE[key] = fallback` with a 60 s
    expiry) and serve them back indistinguishably from real data. This is a
    parallel record — it never touches the value cache, its keys, its TTLs or
    its eviction. Removing this class would leave cache behaviour identical.
    """

    __slots__ = ("_by_key",)

    def __init__(self) -> None:
        self._by_key: Dict[str, Dict[str, Any]] = {}

    def record(self, key: str, status: str) -> None:
        self._by_key[key] = {"status": status, "at": time.time()}

    def lookup(self, key: str) -> Dict[str, Any]:
        """(status, age_seconds) for a cache hit on `key`.

        A hit whose stored status was a failure is reported as `stale_cache`:
        the caller is being handed a failure that happened up to a TTL ago.
        """
        entry = self._by_key.get(key)
        if not entry:
            # Cached by a path that predates this bookkeeping (or by another
            # process). Unknown is honest; `ok` would be a guess.
            return {"status": UNKNOWN, "age_s": None, "was_failure": None}
        age = max(0.0, time.time() - float(entry["at"]))
        was_failure = is_failure(entry["status"])
        return {
            "status": STALE_CACHE if was_failure else entry["status"],
            "age_s": round(age, 3),
            "was_failure": was_failure,
        }

    def clear(self) -> None:
        self._by_key.clear()


def engine_entry(
    *,
    configured: Optional[bool],
    fetch_status: str,
    fallback_used: bool,
    fallback_reason: Optional[str],
    input_completeness: Optional[int],
    input_expected: Optional[int],
    served_from_cache: bool,
    data_freshness_s: Optional[float],
    confidence_semantic_type: str,
    components: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """One engine's entry. Pure; every argument is already redacted by construction."""
    entry: Dict[str, Any] = {
        "configured": configured,
        "fetch_status": fetch_status,
        "fallback_used": bool(fallback_used),
        "fallback_reason": fallback_reason,
        "input_completeness": input_completeness,
        "input_expected": input_expected,
        "served_from_cache": bool(served_from_cache),
        "data_freshness_s": data_freshness_s,
        "confidence_semantic_type": confidence_semantic_type,
    }
    if components:
        entry["components"] = dict(components)
    return entry


def _is_degraded(entry: Dict[str, Any]) -> bool:
    if entry.get("fallback_used"):
        return True
    if is_failure(entry.get("fetch_status")):
        return True
    completeness, expected = entry.get("input_completeness"), entry.get("input_expected")
    if isinstance(completeness, int) and isinstance(expected, int) and expected > 0:
        return completeness < expected
    return False


def build_dependency_health(
    *,
    engines: Dict[str, Dict[str, Any]],
    mtf: Optional[Dict[str, str]] = None,
    engine_execution_telemetry: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Assemble the candidate-level record. Pure; no I/O, no clock beyond ages.

    `engine_execution_status` is DERIVED from the existing
    `engine_execution_telemetry` rather than recomputed, so the two can never
    disagree about whether an engine crashed.
    """
    engines = {k: v for k, v in (engines or {}).items() if v}
    degraded = sorted(name for name, e in engines.items() if _is_degraded(e))

    exec_status = UNKNOWN
    if engine_execution_telemetry is not None:
        failed = engine_execution_telemetry.get("failed_engine_count")
        if isinstance(failed, int):
            exec_status = "all_ok" if failed == 0 else "degraded"

    mtf_map = dict(mtf or {})
    mtf_degraded = any(is_failure(s) for s in mtf_map.values())

    return {
        "version": DEPENDENCY_HEALTH_VERSION,
        "degraded_input": bool(degraded) or mtf_degraded or exec_status == "degraded",
        "degraded_engines": degraded,
        "engines": engines,
        "mtf": mtf_map,
        "engine_execution_status": exec_status,
    }
