"""`macro_shadow_v1` — what the macro engine WOULD have produced, had FRED been
configured. Pure contract + arithmetic. Stage 1 of the shadow restore.

WHY THIS EXISTS
    CP-MACRO-FRED-REGRESSION-DIAGNOSIS established that `FRED_API_KEY` stopped
    reaching the application at the 2026-07-26 containerization boundary, and has
    been absent since 2026-07-27T00:34:01Z. Restoring it directly would raise every
    candidate's confidence by a measured +5.0 points and let ~437 more engine-
    actionable candidates clear the 65 publish gate — i.e. it would loosen the gate
    without anyone deciding to. So the restore is observed first and connected never
    (here).

WHAT THIS MODULE IS NOT
    It is not a second decision path. Nothing in it may be read by, called from, or
    merged into the live decision. It never constructs an `EngineResult`, never
    touches `engine_results`, and therefore cannot reach composite, confidence,
    disagreement or the consensus pool — those all read from that one list.

PURITY CONTRACT (enforced by tests/test_macro_shadow_contract.py)
    No DB session, no HTTP client, no scheduler, no settings/env, no secret, no
    global mutable state, no ORM object, no `EngineResult`. Deterministic in,
    JSON-serialisable out. Inputs are never mutated.

STAGE 1 SCOPE
    Contract + arithmetic + validation ONLY. There is deliberately no call site: a
    repo scan asserts no production module imports this one. Wiring, candidate
    persistence, secret presence and the real fetch are separate checkpoints.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from app.services.dependency_health import (
    EMPTY, INTERNAL_ERROR, NETWORK_ERROR, NOT_CONFIGURED, OK, PARSE_ERROR,
    STALE_CACHE, TIMEOUT,
)

# ── Contract identity ────────────────────────────────────────────────────────
MACRO_SHADOW_VERSION = "macro_shadow_v1"
MACRO_SHADOW_MODE = "shadow_observation_only"

# The macro engine's score/confidence rules are INLINE in
# app/engines/macro/engine.py:95-132 — they are not callable helpers, so reusing
# them would mean editing production code inside a checkpoint whose whole point is
# that production is byte-identical. They are therefore restated here, VERSIONED,
# and pinned to the real engine by an exhaustive boundary-equivalence test
# (test_macro_shadow_contract.py::test_*_matches_the_real_macro_engine). Drift
# turns that test red rather than silently producing a second truth. Bump these
# when engine.py's rules change.
MACRO_SCORE_RULE_VERSION = "macro_score_rule_1"
MACRO_CONFIDENCE_RULE_VERSION = "macro_conf_rule_1"

# Fixed counterfactual scope — these are facts about what CANNOT be replayed, not
# settings. Occupancy is recursive (the active-signal set changes as signals
# publish), so a full publish counterfactual is unavailable by construction.
PUBLISH_COUNTERFACTUAL_SCOPE = "gate_only_not_full_scheduler"
OCCUPANCY_REPLAY_AVAILABLE = False
FULL_PUBLISH_COUNTERFACTUAL_AVAILABLE = False

# ── Series ───────────────────────────────────────────────────────────────────
# The engine reads exactly two series (engine.py:88-89). The collector also fetches
# CPIAUCSL and DTWEXBGS (macro_collector.py:204-209) and never scores them — half
# the outbound calls are dead. The shadow does not request them; it records that
# they were deliberately skipped so the omission is legible rather than forgotten.
SERIES_FEDFUNDS = "FEDFUNDS"
SERIES_DGS10 = "DGS10"
SERIES_CPIAUCSL = "CPIAUCSL"
SERIES_DTWEXBGS = "DTWEXBGS"

SCORED_SERIES: Tuple[str, ...] = (SERIES_FEDFUNDS, SERIES_DGS10)
UNSCORED_SERIES: Tuple[str, ...] = (SERIES_CPIAUCSL, SERIES_DTWEXBGS)
ALL_SERIES: Tuple[str, ...] = SCORED_SERIES + UNSCORED_SERIES

NOT_READ_BY_ENGINE = "not_read_by_engine"

# Crypto consults exactly the two scored series (engine.py:148 → expected=2).
COMPONENTS_EXPECTED_CRYPTO = 2

# ── Vocabularies ─────────────────────────────────────────────────────────────
# Reuse dependency_health's statuses rather than minting a parallel dialect; only
# the states it has no word for are added here.
DISABLED = "disabled"
PARTIAL = "partial"
HTTP_4XX = "http_4xx"
HTTP_429 = "http_429"
BUDGET_GUARD = "budget_guard"

FETCH_STATUSES: Tuple[str, ...] = (
    NOT_CONFIGURED, DISABLED, OK, PARTIAL, EMPTY, HTTP_4XX, HTTP_429, TIMEOUT,
    NETWORK_ERROR, PARSE_ERROR, STALE_CACHE, INTERNAL_ERROR, BUDGET_GUARD,
)

NO_API_KEY = "no_api_key"
FETCH_DISABLED = "fetch_disabled"
AUTH_FAILED = "auth_failed"
RATE_LIMITED = "rate_limited"
FETCH_FAILED = "fetch_failed"
NO_DATA = "no_data"
PARTIAL_DATA = "partial_data"
LOOKAHEAD_VIOLATION = "lookahead_violation"
EXCEPTION = "exception"

FALLBACK_REASONS: Tuple[str, ...] = (
    NO_API_KEY, FETCH_DISABLED, AUTH_FAILED, RATE_LIMITED, FETCH_FAILED, NO_DATA,
    PARTIAL_DATA, LOOKAHEAD_VIOLATION, EXCEPTION, BUDGET_GUARD,
)

# No ALFRED/vintage endpoint is used, so every value is "whatever FRED served at
# retrieval time". FEDFUNDS and DGS10 are both revised, so a stored observation
# cannot be re-fetched identically later — the payload says so rather than
# implying a replay guarantee it cannot keep.
VINTAGE_REALTIME_LATEST = "realtime_latest"
REVISION_POSSIBLE: Dict[str, bool] = {
    SERIES_FEDFUNDS: True,
    SERIES_DGS10: True,
    SERIES_CPIAUCSL: True,
    SERIES_DTWEXBGS: True,
}

BIAS_NEUTRAL = "neutral"
BIAS_BULLISH = "bullish"
BIAS_BEARISH = "bearish"
BIAS_STRONG_BULLISH = "strong_bullish"
BIAS_STRONG_BEARISH = "strong_bearish"


# ── Pure primitives ──────────────────────────────────────────────────────────
def _finite(x: Any) -> Optional[float]:
    """Finite float or None. NaN/inf are rejected at the boundary so they can never
    reach the JSON payload, where they are not representable."""
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _text(x: Any) -> Optional[str]:
    """A JSON-safe string, or None.

    `bias` is the ONE non-numeric production value the payload carries, and every
    number already goes through `_finite` — this closes the matching hole on the
    string side. `SignalBias` is a `str` subclass whose member would round-trip as
    `SignalBias.NEUTRAL` through any reader that stringifies it, so `.value` is
    taken here, once. Anything that is neither a string nor an enum with a string
    value is NOT a bias: it degrades to None rather than to `str(object)`, which
    would write a memory address into ~7 200 rows a day and never repeat.
    """
    if x is None:
        return None
    value = getattr(x, "value", x)
    return value if isinstance(value, str) else None


def macro_score_from_components(
    fed_funds_rate: Optional[float], ten_year_yield: Optional[float]
) -> Tuple[float, int]:
    """(score, components) — mirrors engine.py:74-125 exactly.

    Starts at the neutral 50.0; each present series nudges it and increments the
    component count. Clamped to [0, 100] like the engine.
    """
    score = 50.0
    components = 0
    ff = _finite(fed_funds_rate)
    if ff is not None:
        if ff >= 5.0:
            score -= 10
        elif ff <= 2.0:
            score += 10
        components += 1
    y10 = _finite(ten_year_yield)
    if y10 is not None:
        if y10 >= 5.0:
            score -= 5
        elif y10 <= 3.0:
            score += 5
        components += 1
    return max(0.0, min(100.0, score)), components


def macro_confidence_from_components(components: int) -> float:
    """Mirrors engine.py:128-132. Zero components is 25.0, not `min(40, 85)` — the
    engine branches before the formula, and the difference is 15 points."""
    if components <= 0:
        return 25.0
    return float(min(40 + components * 15, 85))


def macro_bias_from_score(score: float) -> str:
    """Mirrors MacroEngine._score_to_bias (engine.py:197-203). Order matters: the
    >=70 and >=55 tests run before the <=30 and <=45 ones."""
    if score >= 70:
        return BIAS_STRONG_BULLISH
    if score >= 55:
        return BIAS_BULLISH
    if score <= 30:
        return BIAS_STRONG_BEARISH
    if score <= 45:
        return BIAS_BEARISH
    return BIAS_NEUTRAL


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _as_dt(value: Any) -> Optional[datetime]:
    """Parse a datetime or ISO string to an aware datetime, or None. A date-only
    string is anchored at midnight UTC — FRED observation dates are days."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ── Series entry ─────────────────────────────────────────────────────────────
def _series_entry(
    series_id: str,
    raw: Optional[Mapping[str, Any]],
    *,
    decision_time: Optional[datetime],
    configured: bool,
    scored: bool,
) -> Dict[str, Any]:
    """One series' record. PURE — `raw` is read, never written."""
    raw = raw if isinstance(raw, Mapping) else {}
    obs_raw = raw.get("observation_date")
    obs_dt = _as_dt(obs_raw)
    value = _finite(raw.get("value"))
    fetch_status = raw.get("fetch_status")
    if fetch_status not in FETCH_STATUSES:
        fetch_status = NOT_CONFIGURED if not configured else INTERNAL_ERROR

    # A malformed date is NOT silently treated as "fine"; it is unusable, so the
    # series cannot be look-ahead-safe.
    date_ok = obs_dt is not None
    if not scored:
        available = None
        lookahead_safe = None
    elif not date_ok:
        available = False
        lookahead_safe = False
    elif decision_time is None:
        available = None
        lookahead_safe = None
    else:
        available = obs_dt <= decision_time
        lookahead_safe = available

    return {
        "series_id": series_id,
        "configured": bool(configured),
        "requested": bool(scored and configured),
        "fetch_status": fetch_status,
        "observation_date": _iso(obs_raw),
        # The observations endpoint used by the collector does not return a release
        # date, so this is null in v1 rather than guessed from the observation date.
        "release_date": _iso(raw.get("release_date")),
        "retrieved_at": _iso(raw.get("retrieved_at")),
        "source_vintage": VINTAGE_REALTIME_LATEST,
        "revision_possible": REVISION_POSSIBLE.get(series_id, True),
        "available_at_decision_time": available,
        "lookahead_safe": lookahead_safe,
        # Never true in v1: without a vintage pin, a revised series cannot be
        # re-fetched identically, so no stored row is replayable.
        "replayable": False,
        "value_present": value is not None,
        "used_by_macro_score": bool(scored),
        "excluded_from_score_reason": None if scored else NOT_READ_BY_ENGINE,
        "cache_status": raw.get("cache_status"),
        "cache_age_s": _finite(raw.get("cache_age_s")),
        "latency_ms": _finite(raw.get("latency_ms")),
        # Only an exception CLASS name — never a message, URL or response body,
        # any of which could carry the api_key query parameter.
        "error_class": raw.get("error_class"),
    }


# ONE rule for `series`: an entry exists only for a series that was actually
# examined. Nothing examined → `series` is `{}`.
#
# The alternative — a full map of placeholder entries — is a CONSTANT when nothing
# was fetched: configured=False, requested=False, fetch_status=not_configured and
# seventeen nulls, byte-identical on every row. Storing it would write 1 883 bytes
# of that constant onto ~7 200 candidate rows a day (measured: 3 061 B with the
# map, 1 178 B without; +63.0% vs +24.3% against a 4 856 B average `extra`).
# Nothing per-row is lost: which series exist is in SCORED_SERIES/UNSCORED_SERIES,
# how many were expected is `components_expected`, and `executed=False` already
# says none was read.
#
# NOT a version bump. No row has ever carried `macro_shadow_v1` (verified 0 on
# production before wiring) and no reader exists, so there is no earlier shape for
# this to be incompatible with. A bump would falsely imply v1 data is out there.
EXAMINED_SERIES_ONLY = True


# ── Payload builders ─────────────────────────────────────────────────────────
def _base_payload(
    *,
    decision_time: Any,
    production_macro_score: Any,
    production_macro_bias: Any,
    production_macro_confidence: Any,
    production_publish_verdict: Optional[str],
    components_expected: int,
) -> Dict[str, Any]:
    return {
        "version": MACRO_SHADOW_VERSION,
        "mode": MACRO_SHADOW_MODE,
        "score_rule_version": MACRO_SCORE_RULE_VERSION,
        "confidence_rule_version": MACRO_CONFIDENCE_RULE_VERSION,
        "configured": False,
        "executed": False,
        "fetch_status": NOT_CONFIGURED,
        "fallback_reason": NO_API_KEY,
        "decision_time": _iso(decision_time),
        "observation_time": None,
        "observation_lag_s": None,
        "cache_status": None,
        "cache_age_s": None,
        "request_latency_ms": None,
        "components_expected": int(components_expected),
        "components_available": 0,
        "components_used": 0,
        "score_if_restored": None,
        "bias_if_restored": None,
        "confidence_if_restored": None,
        "production_macro_score": _finite(production_macro_score),
        "production_macro_bias": _text(production_macro_bias),
        "production_macro_confidence": _finite(production_macro_confidence),
        "delta_score": None,
        "delta_confidence": None,
        "would_change_direction": None,
        "would_change_composite": None,
        "would_change_confidence": None,
        "would_cross_publish_threshold": None,
        "production_publish_verdict": production_publish_verdict,
        "shadow_publish_gate_result": None,
        "publish_counterfactual_scope": PUBLISH_COUNTERFACTUAL_SCOPE,
        "occupancy_replay_available": OCCUPANCY_REPLAY_AVAILABLE,
        "full_publish_counterfactual_available": FULL_PUBLISH_COUNTERFACTUAL_AVAILABLE,
        # Whether the confidence counterfactual is exact. The production confidence
        # is clamped to [20, 98] (signal_generator.py:319); at a clamp boundary the
        # delta cannot be applied linearly, and saying so beats a wrong number.
        "confidence_counterfactual_exact": None,
        "decision_isolation_verified": True,
        "replayable": False,
        "series": {},
        "errors": [],
    }


def build_disabled_macro_shadow(
    *,
    decision_time: Any = None,
    production_macro_score: Any,
    production_macro_bias: Any,
    production_macro_confidence: Any,
    production_publish_verdict: Optional[str] = None,
    components_expected: int = COMPONENTS_EXPECTED_CRYPTO,
    fetch_status: str = NOT_CONFIGURED,
    fallback_reason: str = NO_API_KEY,
) -> Dict[str, Any]:
    """The payload when no shadow computation ran — today's permanent state.

    Production macro values are ARGUMENTS, never constants: the payload records what
    production actually produced, so a future change to the engine shows up here
    instead of being masked by a hard-coded 50/neutral/25.

    `series` is deliberately EMPTY here — see EXAMINED_SERIES_ONLY. The snapshot
    builder still emits the full map, so the enabled path is unaffected.
    """
    out = _base_payload(
        decision_time=decision_time,
        production_macro_score=production_macro_score,
        production_macro_bias=production_macro_bias,
        production_macro_confidence=production_macro_confidence,
        production_publish_verdict=production_publish_verdict,
        components_expected=components_expected,
    )
    out["fetch_status"] = fetch_status if fetch_status in FETCH_STATUSES else NOT_CONFIGURED
    out["fallback_reason"] = fallback_reason if fallback_reason in FALLBACK_REASONS else NO_API_KEY
    out["configured"] = False
    out["executed"] = False
    out["series"] = {}
    return out


def build_macro_shadow_from_snapshot(
    *,
    decision_time: Any,
    snapshot: Optional[Mapping[str, Any]],
    production_macro_score: Any,
    production_macro_bias: Any,
    production_macro_confidence: Any,
    production_total_confidence: Any,
    engine_count: int,
    publish_threshold: Any,
    production_publish_verdict: Optional[str] = None,
    components_expected: int = COMPONENTS_EXPECTED_CRYPTO,
) -> Dict[str, Any]:
    """PURE: an immutable FRED snapshot + the production decision's own numbers →
    the `macro_shadow_v1` payload.

    `engine_count` is a required argument rather than a literal 9: the confidence
    mean's divisor is `len(engine_results)` (signal_generator.py:318), so hard-coding
    it here would silently drift the day an engine is added or removed.

    Never raises: any structural problem lands in `errors` and leaves
    `executed=False`, because a telemetry helper that can throw is a telemetry
    helper that can take down a scan.
    """
    dt = _as_dt(decision_time)
    out = _base_payload(
        decision_time=decision_time,
        production_macro_score=production_macro_score,
        production_macro_bias=production_macro_bias,
        production_macro_confidence=production_macro_confidence,
        production_publish_verdict=production_publish_verdict,
        components_expected=components_expected,
    )
    errors: list = []

    if not isinstance(snapshot, Mapping):
        out["fetch_status"] = DISABLED
        out["fallback_reason"] = FETCH_DISABLED
        out["series"] = {}          # nothing was examined — EXAMINED_SERIES_ONLY
        out["errors"] = errors
        return out

    configured = bool(snapshot.get("configured", True))
    out["configured"] = configured
    out["cache_status"] = snapshot.get("cache_status")
    out["cache_age_s"] = _finite(snapshot.get("cache_age_s"))
    out["request_latency_ms"] = _finite(snapshot.get("request_latency_ms"))
    out["observation_time"] = _iso(snapshot.get("observation_time"))

    obs_time = _as_dt(snapshot.get("observation_time"))
    if obs_time is not None and dt is not None:
        out["observation_lag_s"] = round((dt - obs_time).total_seconds(), 3)

    raw_series = snapshot.get("series")
    raw_series = raw_series if isinstance(raw_series, Mapping) else {}
    series = {
        sid: _series_entry(sid, raw_series.get(sid), decision_time=dt,
                           configured=configured, scored=sid in SCORED_SERIES)
        for sid in ALL_SERIES
    }
    out["series"] = series

    # A series whose observation post-dates the decision would inject the future
    # into a past decision. It is dropped from the computation AND recorded.
    usable: Dict[str, Optional[float]] = {}
    for sid in SCORED_SERIES:
        entry = series[sid]
        raw = raw_series.get(sid) if isinstance(raw_series.get(sid), Mapping) else {}
        value = _finite(raw.get("value"))
        if value is not None and entry["lookahead_safe"] is False:
            errors.append({"series_id": sid, "error": LOOKAHEAD_VIOLATION})
            value = None
        usable[sid] = value

    available = sum(1 for sid in SCORED_SERIES if series[sid]["value_present"])
    out["components_available"] = available

    if not configured:
        out["fetch_status"] = NOT_CONFIGURED
        out["fallback_reason"] = NO_API_KEY
        out["errors"] = errors
        return out

    score, components_used = macro_score_from_components(
        usable.get(SERIES_FEDFUNDS), usable.get(SERIES_DGS10))
    confidence = macro_confidence_from_components(components_used)
    bias = macro_bias_from_score(score)

    out["executed"] = True
    out["components_used"] = components_used
    out["score_if_restored"] = round(score, 2)
    out["bias_if_restored"] = bias
    out["confidence_if_restored"] = round(confidence, 2)

    snap_status = snapshot.get("fetch_status")
    if snap_status in FETCH_STATUSES:
        out["fetch_status"] = snap_status
    elif components_used == len(SCORED_SERIES):
        out["fetch_status"] = OK
    elif components_used > 0:
        out["fetch_status"] = PARTIAL
    else:
        out["fetch_status"] = EMPTY

    if any(e.get("error") == LOOKAHEAD_VIOLATION for e in errors):
        out["fallback_reason"] = LOOKAHEAD_VIOLATION
    elif components_used == 0:
        out["fallback_reason"] = NO_DATA
    elif components_used < len(SCORED_SERIES):
        out["fallback_reason"] = PARTIAL_DATA
    else:
        out["fallback_reason"] = None

    # ── counterfactual ────────────────────────────────────────────────────────
    prod_macro_conf = _finite(production_macro_confidence)
    prod_total = _finite(production_total_confidence)
    prod_score = _finite(production_macro_score)
    threshold = _finite(publish_threshold)

    if prod_score is not None:
        out["delta_score"] = round(score - prod_score, 4)
        moved = abs(score - prod_score) > 1e-9
        out["would_change_composite"] = bool(moved)
        # Macro is not a consensus voter, so its ONLY route to the signal's
        # direction is the composite. If its contribution is identical, the
        # composite is identical and so is the direction — that much is certain.
        # If the score DID move, the new direction depends on the other eight
        # engines and the disagreement penalty, which this module deliberately does
        # not recompute. `None` is the honest answer there, not a guess.
        out["would_change_direction"] = None if moved else False

    n = int(engine_count) if isinstance(engine_count, int) and engine_count > 0 else 0
    if prod_macro_conf is not None and n > 0:
        delta = (confidence - prod_macro_conf) / n
        out["delta_confidence"] = round(delta, 6)
        out["would_change_confidence"] = bool(abs(delta) > 1e-9)
        if prod_total is not None:
            # signal_generator.py:319 clamps to [20, 98]; at a boundary the delta
            # cannot be added linearly, so the counterfactual is flagged inexact
            # rather than reported as if it were sound.
            exact = not (abs(prod_total - 20.0) < 1e-9 or abs(prod_total - 98.0) < 1e-9)
            out["confidence_counterfactual_exact"] = exact
            shadow_total = max(20.0, min(98.0, prod_total + delta))
            if threshold is not None:
                crossed = prod_total < threshold <= shadow_total
                out["would_cross_publish_threshold"] = bool(crossed)
                out["shadow_publish_gate_result"] = (
                    "pass" if shadow_total >= threshold else "fail")

    out["errors"] = errors
    return out


# ── Validation ───────────────────────────────────────────────────────────────
REQUIRED_TOP_LEVEL: Tuple[str, ...] = (
    "version", "mode", "score_rule_version", "confidence_rule_version",
    "configured", "executed", "fetch_status", "fallback_reason", "decision_time",
    "observation_time", "observation_lag_s", "cache_status", "cache_age_s",
    "request_latency_ms", "components_expected", "components_available",
    "components_used", "score_if_restored", "bias_if_restored",
    "confidence_if_restored", "production_macro_score", "production_macro_bias",
    "production_macro_confidence", "delta_score", "delta_confidence",
    "would_change_direction", "would_change_composite", "would_change_confidence",
    "would_cross_publish_threshold", "production_publish_verdict",
    "shadow_publish_gate_result", "publish_counterfactual_scope",
    "occupancy_replay_available", "full_publish_counterfactual_available",
    "confidence_counterfactual_exact", "decision_isolation_verified", "replayable",
    "series", "errors",
)

REQUIRED_SERIES_FIELDS: Tuple[str, ...] = (
    "series_id", "configured", "requested", "fetch_status", "observation_date",
    "release_date", "retrieved_at", "source_vintage", "revision_possible",
    "available_at_decision_time", "lookahead_safe", "replayable", "value_present",
    "used_by_macro_score", "excluded_from_score_reason", "cache_status",
    "cache_age_s", "latency_ms", "error_class",
)


def validate_macro_shadow(payload: Any) -> Sequence[str]:
    """Structural problems with a payload, as a list of strings (empty = valid).

    Returns rather than raises: a validator that throws inside a fail-open telemetry
    path would defeat the fail-open.
    """
    problems: list = []
    if not isinstance(payload, Mapping):
        return ["payload is not a mapping"]

    for key in REQUIRED_TOP_LEVEL:
        if key not in payload:
            problems.append(f"missing top-level key: {key}")
    if payload.get("version") != MACRO_SHADOW_VERSION:
        problems.append(f"bad version: {payload.get('version')!r}")
    if payload.get("mode") != MACRO_SHADOW_MODE:
        problems.append(f"bad mode: {payload.get('mode')!r}")
    if payload.get("fetch_status") not in FETCH_STATUSES:
        problems.append(f"bad fetch_status: {payload.get('fetch_status')!r}")
    fr = payload.get("fallback_reason")
    if fr is not None and fr not in FALLBACK_REASONS:
        problems.append(f"bad fallback_reason: {fr!r}")
    if payload.get("occupancy_replay_available") is not False:
        problems.append("occupancy_replay_available must be False")
    if payload.get("full_publish_counterfactual_available") is not False:
        problems.append("full_publish_counterfactual_available must be False")
    if payload.get("publish_counterfactual_scope") != PUBLISH_COUNTERFACTUAL_SCOPE:
        problems.append("publish_counterfactual_scope must be gate-only")
    if payload.get("replayable") is not False:
        problems.append("replayable must be False while no vintage is pinned")

    series = payload.get("series")
    if not isinstance(series, Mapping):
        problems.append("series is not a mapping")
    else:
        for sid, entry in series.items():
            if not isinstance(entry, Mapping):
                problems.append(f"series[{sid}] is not a mapping")
                continue
            for key in REQUIRED_SERIES_FIELDS:
                if key not in entry:
                    problems.append(f"series[{sid}] missing: {key}")
            if entry.get("replayable") is not False:
                problems.append(f"series[{sid}].replayable must be False")

    for key, value in payload.items():
        if isinstance(value, float) and not math.isfinite(value):
            problems.append(f"non-finite value at {key}")
    return problems
