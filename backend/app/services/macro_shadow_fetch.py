"""The ONE place a shadow FRED request is made. Stage 4 of the macro restore.

WHY IT IS NOT `MacroCollector`
    `MacroCollector` is what the production MacroEngine constructs on every
    candidate (engine.py:79). Reusing it would mean the shadow and the live
    decision share a client, a cache and — fatally — a kill-switch: opening one
    would open the other, reconnecting the decision to FRED and moving the
    publish gate by a measured +5.0 confidence. So this module owns its own
    client, its own cache namespace and its own flag, and the production one
    stays off.

WHAT IT GUARANTEES
    * At most ONE outbound request cycle per TTL, shared by every candidate and
      every overlapping job. Not "one per scan" — stronger: the TTL is the scan
      cadence, so 15m/1h/4h/1d sweeps all reuse the same snapshot.
    * Bounded. One `asyncio.timeout` covers both series; the ceiling is a small
      fraction of the 45 s per-asset budget, and a near-deadline call declines to
      start at all rather than relying on that ceiling.
    * No retry. The next natural scan is the retry — a retry loop here would
      multiply the request count the TTL exists to bound.
    * Fail-silent. It cannot raise, so it cannot cost a candidate or a scan. A
      failure becomes a snapshot that says what failed.
    * Immutable. Every caller gets a deep copy, so one candidate cannot mutate
      what the next one reads.
    * No secret anywhere. The key reaches exactly one expression — the request's
      query parameters — and nothing else: not a log line, not an exception, not
      a status, not the returned snapshot.

WHAT IT MUST NOT DO — enforced by tests
    Touch `_MACRO_CACHE`, construct a `MacroCollector`, build an `EngineResult`,
    reach `engine_results`, retry, raise, cache a failure, or return a shared
    mutable.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Tuple

import httpx

from app import log_redaction
from app.config import get_settings
from app.services import job_guard
from app.services.macro_shadow import (
    AUTH_FAILED,
    BUDGET_GUARD,
    EMPTY,
    FETCH_FAILED,
    HTTP_429,
    HTTP_4XX,
    INTERNAL_ERROR,
    NETWORK_ERROR,
    OK,
    PARSE_ERROR,
    SCORED_SERIES,
    STALE_CACHE,
    TIMEOUT,
)

logger = logging.getLogger(__name__)

FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"

# One `asyncio.timeout` covers BOTH series, which run concurrently. Six seconds
# against a 45 s per-asset budget (job_guard.PER_ASSET_BUDGET_SECONDS) is 13% of
# one asset's bound, and only the asset that refreshes the cache pays it.
SHADOW_FETCH_TIMEOUT_SECONDS = 6.0

# The 15m scan cadence. FEDFUNDS is published monthly and DGS10 daily, so a
# 15-minute window is already far fresher than anything the source can change;
# a shorter TTL would buy no freshness and multiply requests. Setting it EQUAL to
# the cadence is what makes "at most one request per scan" hold across the
# overlapping 15m/1h/4h/1d sweeps rather than per-job.
SHADOW_CACHE_TTL_SECONDS = 900.0

# How old a snapshot may be and still be served when a fetch FAILS. An hour of
# staleness on a monthly/daily series is harmless; the alternative is discarding
# a good observation because one request timed out. Always labelled `stale`.
SHADOW_STALE_MAX_AGE_SECONDS = 3600.0

# Decline to start when less than this remains of the job's budget. The timeout
# above bounds the request; this bounds the DECISION to make one at all, so a
# job already near its deadline is never pushed over by optional telemetry.
SHADOW_BUDGET_MARGIN_SECONDS = 4.0

# Separate from `macro_collector._MACRO_CACHE` by construction, not by
# convention: a different dict in a different module, keyed by a namespace that
# names the contract it serves.
SHADOW_CACHE_NAMESPACE = "macro_shadow_v1"
_SHADOW_CACHE: Dict[str, Dict[str, Any]] = {}

# Single-flight state, declared here with the rest of the module state; the
# mechanism and the reasoning live next to `_lock_for` further down.
_SHADOW_LOCKS: Dict[str, Tuple[Any, asyncio.Lock]] = {}
_SHADOW_CYCLES: Dict[str, Dict[str, Any]] = {}

CACHE_HIT = "hit"
CACHE_MISS = "miss"
CACHE_STALE = "stale"


def cache_key() -> str:
    """Namespace + the exact series set. A future stage that fetches a different
    set gets a different key rather than silently reading this one's snapshot."""
    return f"{SHADOW_CACHE_NAMESPACE}|{'+'.join(SCORED_SERIES)}"


def reset_cache_for_tests() -> None:
    _SHADOW_CACHE.clear()
    # The single-flight state too. DEFENSIVE, not load-bearing: a sabotage run
    # proved that deleting these two lines changes no behaviour, because
    # `_lock_for` already replaces a lock whose loop has been retired and the
    # cycle counter is only ever compared RELATIVELY. Kept so state cannot grow
    # unbounded across a long run and so a reader is never asked to hold that
    # reasoning in their head — and described accurately here rather than
    # credited with a protection it does not provide.
    _SHADOW_LOCKS.clear()
    _SHADOW_CYCLES.clear()


def _now() -> float:
    return time.monotonic()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _classify(exc: BaseException) -> Tuple[str, str]:
    """(fetch_status, error_class) for a failed request.

    Only the exception's TYPE NAME is ever returned. `str(exc)` is never touched:
    httpx puts the request URL in its message, and that URL carries the api_key
    query parameter.
    """
    name = type(exc).__name__
    if isinstance(exc, (asyncio.TimeoutError, httpx.TimeoutException)):
        return TIMEOUT, name
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code == 429:
            return HTTP_429, name
        if code in (401, 403):
            return HTTP_4XX, name
        if 400 <= code < 500:
            return HTTP_4XX, name
        return NETWORK_ERROR, name
    if isinstance(exc, (httpx.TransportError, httpx.NetworkError, OSError)):
        return NETWORK_ERROR, name
    if isinstance(exc, (ValueError, KeyError, TypeError)):
        return PARSE_ERROR, name
    return INTERNAL_ERROR, name


def _reason_for(status: str, code: Optional[int]) -> Optional[str]:
    """The fetcher's OWN word on why, where it knows more than the status does.

    A 401/403 is `auth_failed`; any other 4xx is not — a 400 is a malformed
    request, and calling that an auth failure would send the next reader looking
    at the wrong thing. The contract's status→reason map cannot make that
    distinction because both are `http_4xx`.
    """
    if status == HTTP_429:
        return None                              # the map already says rate_limited
    if status == HTTP_4XX:
        return AUTH_FAILED if code in (401, 403) else FETCH_FAILED
    return None


def _series_entry(*, status: str, value=None, observation_date=None,
                  latency_ms=None, error_class=None,
                  cache_status: str = CACHE_MISS,
                  cache_age_s: Optional[float] = None) -> Dict[str, Any]:
    return {
        "value": value,
        "observation_date": observation_date,
        "fetch_status": status,
        "retrieved_at": _iso_now(),
        "cache_status": cache_status,
        "cache_age_s": cache_age_s,
        "latency_ms": latency_ms,
        "error_class": error_class,
    }


async def _fetch_one(client: httpx.AsyncClient, series_id: str,
                     api_key: str) -> Tuple[Dict[str, Any], Optional[int]]:
    """One series. Never raises; returns (entry, http_status_code_or_None)."""
    started = time.perf_counter()
    try:
        response = await client.get(
            FRED_OBSERVATIONS_URL,
            params={"series_id": series_id, "api_key": api_key,
                    "file_type": "json", "sort_order": "desc", "limit": 1},
        )
        latency = round((time.perf_counter() - started) * 1000.0, 2)
        response.raise_for_status()
        observations = response.json().get("observations", [])
        if not observations:
            return _series_entry(status=EMPTY, latency_ms=latency), response.status_code
        raw_value = observations[0].get("value")
        if raw_value in (None, ".", ""):
            return _series_entry(status=EMPTY, latency_ms=latency), response.status_code
        # Our OWN request line: method, host, path, status, latency. No query
        # string at any point — this is the record httpx's own line is silenced
        # in favour of, and it cannot carry a credential because it never holds
        # one to begin with.
        logger.info("[MacroShadowFetch] GET %s%s -> %s in %sms",
                    response.request.url.host, response.request.url.path,
                    response.status_code, latency)
        return _series_entry(
            status=OK, value=float(raw_value),
            observation_date=observations[0].get("date"),
            latency_ms=latency,
        ), response.status_code
    except asyncio.CancelledError:
        # NOT swallowed. `asyncio.timeout` above and the scheduler's own shutdown
        # both cancel cooperatively, and a handler that catches this would fight
        # its own bound — the request would be "cancelled" while this coroutine
        # kept running to build a tidy result. Re-raised so the timeout is real.
        raise
    except BaseException as exc:  # noqa: BLE001 — a shadow may never raise upward
        latency = round((time.perf_counter() - started) * 1000.0, 2)
        status, error_class = _classify(exc)
        code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        # Only the class name and, for an HTTP error, the numeric status. Never
        # `str(exc)` — httpx embeds the request URL, and the URL holds the key.
        logger.debug("[MacroShadowFetch] %s -> %s (%s)", series_id, status, error_class)
        return _series_entry(status=status, latency_ms=latency,
                             error_class=error_class), code


def _snapshot_observation_time(series: Mapping[str, Any]) -> Optional[str]:
    """The STALEST observation date present, exactly as FRED reported it.

    WHY THE STALEST, NOT THE NEWEST
        A snapshot is only as fresh as its stalest input. FEDFUNDS is monthly and
        DGS10 is daily, so reporting the newest would let a two-day-old DGS10
        stand in front of a two-month-old FEDFUNDS — the opposite of what a
        freshness field is for. Per-series `observation_date` still carries the
        breakdown for anyone who needs it.

    WHY A DAY STRING AND NOT A TIMESTAMP
        The `series/observations` endpoint has DAY granularity. Widening
        "2026-06-01" to "2026-06-01T00:00:00+00:00" here would claim a precision
        we never received. `_as_dt` in the contract already anchors a date-only
        string at midnight UTC (macro_shadow.py:252-254), so `observation_lag_s`
        is derived from a convention that is written down rather than invented at
        this call site.

    This replaces a hardcoded `None`. That was not an oversight — the earlier
    reasoning was that no ALFRED/vintage endpoint is used, so there is no
    observation TIME distinct from each series' observation DATE, and filling the
    field with the retrieval clock would have been a different fact wearing this
    field's name. That still holds: the retrieval clock is NOT what goes here.
    What was missed is that the observation DATE is itself a legitimate answer,
    and leaving the field null made snapshot-level staleness unreadable while the
    data to compute it was sitting one level down.
    """
    oldest_key: Optional[datetime] = None
    oldest_raw: Optional[str] = None
    for entry in series.values():
        if not isinstance(entry, Mapping):
            continue
        raw = entry.get("observation_date")
        if not isinstance(raw, str) or not raw.strip():
            continue
        try:
            key = datetime.fromisoformat(raw.strip())
        except ValueError:
            continue                      # unparseable date is not a freshness claim
        if key.tzinfo is None:
            key = key.replace(tzinfo=timezone.utc)
        if oldest_key is None or key < oldest_key:
            oldest_key, oldest_raw = key, raw.strip()
    return oldest_raw


def _snapshot(*, configured: bool, fetch_status: str, series: Dict[str, Any],
              cache_status: str, cache_age_s: Optional[float] = None,
              request_latency_ms: Optional[float] = None,
              fallback_reason: Optional[str] = None) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "configured": configured,
        "fetch_status": fetch_status,
        "cache_status": cache_status,
        "cache_age_s": cache_age_s,
        "request_latency_ms": request_latency_ms,
        # The stalest observation date among the series — see
        # `_snapshot_observation_time`. Still never the retrieval clock.
        "observation_time": _snapshot_observation_time(series),
        "series": series,
    }
    if fallback_reason is not None:
        out["fallback_reason"] = fallback_reason
    return out


def _failure_snapshot(status: str, *, series: Optional[Dict[str, Any]] = None,
                      fallback_reason: Optional[str] = None,
                      request_latency_ms: Optional[float] = None) -> Dict[str, Any]:
    series = series if series is not None else {
        sid: _series_entry(status=status) for sid in SCORED_SERIES}
    return _snapshot(configured=True, fetch_status=status, series=series,
                     cache_status=CACHE_MISS, fallback_reason=fallback_reason,
                     request_latency_ms=request_latency_ms)


def _cached(now: float) -> Optional[Tuple[Dict[str, Any], float]]:
    entry = _SHADOW_CACHE.get(cache_key())
    if not entry:
        return None
    return entry["snapshot"], now - entry["stored_at"]


def _from_cache(cached: Tuple[Dict[str, Any], float]) -> Dict[str, Any]:
    """A caller's own copy of a cached snapshot, marked as the hit it is."""
    snapshot, age = cached
    fresh = copy.deepcopy(snapshot)
    fresh["cache_status"] = CACHE_HIT
    fresh["cache_age_s"] = round(age, 3)
    return fresh


# ── Single flight ────────────────────────────────────────────────────────────
# The cache is written AFTER a cycle completes, so concurrent callers that arrive
# while it is cold all miss and all fetch. Measured in production on 2026-08-01:
# the 15m and 4h sweeps started 1.0 s apart on a cold container and produced FOUR
# requests in 64 ms — two cycles, not one. The TTL bounds the steady state; it
# never bounded the cold start, and the module's "shared by every overlapping
# job" guarantee only ever held once the cache was warm.

# `_SHADOW_LOCKS` holds one lock per cache key per running loop; `_SHADOW_CYCLES`
# holds the last COMPLETED cycle per key with a counter that ticks once per
# cycle. The latter is NOT a second cache — see `_share_completed_cycle` for who
# may read it and why a later caller never can.


def _lock_for(key: str) -> asyncio.Lock:
    """The lock for one cache key on the running loop.

    NOT a single global lock: a later stage that fetches a different series set
    gets a different key and must not queue behind this one.

    The loop is part of the identity because `asyncio.Lock` binds itself to the
    loop it first CONTENDS on and raises "bound to a different event loop"
    afterwards. Production has one loop for the process lifetime so this never
    fires there; `asyncio.run` creates a fresh loop per call, so without this the
    guard would work in production and explode under a test that drives it twice.

    Never awaits, so two coroutines cannot interleave inside it and both build a
    lock for the same key.
    """
    loop = asyncio.get_running_loop()
    entry = _SHADOW_LOCKS.get(key)
    if entry is None or entry[0] is not loop:
        entry = (loop, asyncio.Lock())
        _SHADOW_LOCKS[key] = entry
    return entry[1]


def _cycle_seq(key: str) -> int:
    entry = _SHADOW_CYCLES.get(key)
    return int(entry["seq"]) if entry else 0


def _record_cycle(key: str, snapshot: Dict[str, Any]) -> None:
    _SHADOW_CYCLES[key] = {"seq": _cycle_seq(key) + 1,
                           "snapshot": copy.deepcopy(snapshot)}


def _share_completed_cycle(key: str, seq_before: int) -> Optional[Dict[str, Any]]:
    """The result of a cycle that finished WHILE THIS CALLER WAS QUEUEING, if
    there was one and it left the cache cold — otherwise None.

    WHY THIS EXISTS
        A failed cycle is deliberately never cached, so the second check above
        cannot see it. Without this, a lock alone would make failure strictly
        WORSE than no lock: today a hundred concurrent callers meeting a dead
        upstream run a hundred cycles CONCURRENTLY and are done in one timeout;
        serialised behind a lock they would run a hundred cycles END TO END and
        burn every job budget in the process. The lock must not buy correctness
        on the happy path by paying for it with a ten-minute stall on the sad
        one.

        It is also what "no retry — the next natural scan is the retry" already
        says. A caller that queued behind a cycle and then repeated it the
        instant it failed IS a retry, just one wearing a different hat.

    WHY IT IS NOT A SECOND CACHE
        The only caller that can read it is one whose `seq_before` predates the
        recorded cycle — i.e. one that was already waiting when that cycle ran.
        A caller arriving afterwards reads the CURRENT seq, sees no change, and
        fetches for itself. So a failure is shared across one in-flight window
        and never served again, which is exactly the difference between sharing
        a result and caching one.
    """
    if _cycle_seq(key) == seq_before:
        return None
    entry = _SHADOW_CYCLES.get(key)
    if not entry:
        return None
    return copy.deepcopy(entry["snapshot"])


async def get_shadow_macro_snapshot(*, job_id: Optional[str] = None
                                    ) -> Optional[Dict[str, Any]]:
    """An immutable FRED snapshot for the shadow, or None to keep it disabled.

    None means "do not run the observation path" — the flag is off or there is no
    credential. A dict means the path runs, INCLUDING when the fetch failed: the
    failure is then part of the record rather than an absence.

    Never raises.
    """
    try:
        settings = get_settings()
        if not bool(getattr(settings, "MACRO_SHADOW_FETCH_ENABLED", False)):
            return None
        api_key = (getattr(settings, "FRED_API_KEY", "") or "").strip()
        if not api_key:
            # A flag without a credential is not an error; it is the same
            # "nothing to fetch" the disabled path already describes correctly.
            return None

        now = _now()
        cached = _cached(now)
        if cached is not None and cached[1] < SHADOW_CACHE_TTL_SECONDS:
            return _from_cache(cached)

        # Budget is checked BEFORE queueing, exactly as before. A caller already
        # near its deadline declines to start rather than spending what is left
        # waiting for someone else's request.
        if job_id:
            remaining = job_guard.remaining_budget(job_id)
            if (remaining is not None
                    and remaining < SHADOW_FETCH_TIMEOUT_SECONDS
                    + SHADOW_BUDGET_MARGIN_SECONDS):
                return _failure_snapshot(BUDGET_GUARD, fallback_reason=BUDGET_GUARD)

        key = cache_key()
        # Read BEFORE queueing. If this number has moved by the time the lock is
        # ours, a full cycle ran while we waited — see below.
        seq_before = _cycle_seq(key)

        # `async with` releases on return, on exception, on timeout and on
        # cancellation. Nothing here catches CancelledError: a caller cancelled
        # while queueing must stay cancelled, and it leaves nothing behind
        # because it never entered the body.
        async with _lock_for(key):
            now = _now()
            cached = _cached(now)
            # THE SECOND CHECK. The holder may have completed a cycle and filled
            # the cache while we queued; without this, every waiter would fetch
            # again the moment it woke and the lock would buy nothing.
            if cached is not None and cached[1] < SHADOW_CACHE_TTL_SECONDS:
                return _from_cache(cached)

            shared = _share_completed_cycle(key, seq_before)
            if shared is not None:
                return shared

            snapshot = await _fetch_fresh(api_key, now, cached)
            _record_cycle(key, snapshot)
            return snapshot
    except asyncio.CancelledError:
        # NOT swallowed. A cancellation is not a failure to be reported — it is
        # the caller being torn down, and the only correct answer is to stop.
        # Absorbing it here returned None and let `_generate_signal` walk on into
        # its database block, so a scan the guard had already given up on could
        # still write a candidate — the opposite of what
        # `run_asset_with_deadline` documents ("no candidate is written and
        # nothing is fabricated"). This mirrors `_fetch_one`, which re-raises for
        # the same reason one frame down.
        raise
    except BaseException as exc:  # noqa: BLE001 — telemetry may never break a scan
        logger.warning("[MacroShadowFetch] snapshot unavailable (ignored): %s",
                       type(exc).__name__)
        return None


async def _fetch_fresh(api_key: str, now: float,
                       cached: Optional[Tuple[Dict[str, Any], float]]
                       ) -> Dict[str, Any]:
    """One bounded request cycle. No retry — the next scan is the retry."""
    # Armed BEFORE the first request, not only from `app.main`. A worker, a
    # script or a test that reaches this module without importing the FastAPI
    # entrypoint must still be covered — the leak happened in the library, so the
    # guard has to be present wherever the library can be called. Idempotent.
    log_redaction.install()

    started = time.perf_counter()
    series: Dict[str, Any] = {}
    codes: Dict[str, Optional[int]] = {}
    try:
        async with httpx.AsyncClient(timeout=SHADOW_FETCH_TIMEOUT_SECONDS) as client:
            async with asyncio.timeout(SHADOW_FETCH_TIMEOUT_SECONDS):
                results = await asyncio.gather(
                    *(_fetch_one(client, sid, api_key) for sid in SCORED_SERIES))
        for sid, (entry, code) in zip(SCORED_SERIES, results):
            series[sid] = entry
            codes[sid] = code
    except asyncio.CancelledError:
        # NOT swallowed, and this is the frame that actually mattered.
        # `_fetch_one` already re-raises, but this handler caught it one frame
        # up and `_classify` labelled it `internal_error` / `CancelledError` on
        # BOTH series — an internal failure that never happened, written to a
        # candidate. Cancellation is control flow, not telemetry.
        #
        # The 6 s bound is UNAFFECTED: `asyncio.timeout` converts its OWN expiry
        # to `TimeoutError` before it leaves the block, so that path still lands
        # in `_classify` as `timeout` and never reaches this clause.
        raise
    except BaseException as exc:  # noqa: BLE001
        status, error_class = _classify(exc)
        latency = round((time.perf_counter() - started) * 1000.0, 2)
        stale = _serve_stale(cached, status)
        if stale is not None:
            return stale
        return _failure_snapshot(
            status, request_latency_ms=latency,
            series={sid: _series_entry(status=status, error_class=error_class)
                    for sid in SCORED_SERIES})

    latency = round((time.perf_counter() - started) * 1000.0, 2)
    ok_count = sum(1 for e in series.values() if e["fetch_status"] == OK)
    worst = next((e["fetch_status"] for e in series.values()
                  if e["fetch_status"] != OK), OK)
    overall = OK if ok_count == len(SCORED_SERIES) else worst
    reason = _reason_for(overall, next((codes[s] for s in SCORED_SERIES
                                        if series[s]["fetch_status"] == overall), None))

    if ok_count == 0:
        # Nothing usable arrived. A stale-but-real observation beats an empty
        # one, and a failure is NEVER cached — so the next scan retries for free.
        stale = _serve_stale(cached, overall)
        if stale is not None:
            return stale
        return _failure_snapshot(overall, series=series, fallback_reason=reason,
                                 request_latency_ms=latency)

    snapshot = _snapshot(configured=True, fetch_status=overall, series=series,
                         cache_status=CACHE_MISS, request_latency_ms=latency,
                         fallback_reason=reason)
    _SHADOW_CACHE[cache_key()] = {"snapshot": copy.deepcopy(snapshot),
                                  "stored_at": now}
    return snapshot


def _serve_stale(cached: Optional[Tuple[Dict[str, Any], float]],
                 failed_status: str) -> Optional[Dict[str, Any]]:
    """A previous good snapshot, if one is recent enough to still mean something.

    Labelled `stale_cache` on both channels so no reader mistakes it for a live
    read, and the age is carried so they can judge it themselves.
    """
    if cached is None:
        return None
    snapshot, age = cached
    if age > SHADOW_STALE_MAX_AGE_SECONDS:
        return None
    out = copy.deepcopy(snapshot)
    out["cache_status"] = CACHE_STALE
    out["cache_age_s"] = round(age, 3)
    out["fetch_status"] = STALE_CACHE
    logger.debug("[MacroShadowFetch] serving stale snapshot after %s", failed_status)
    return out
