"""CP-MACRO-SHADOW-OBSERVATION-TIME-TELEMETRY — snapshot freshness, reported.

WHAT WAS WRONG
    Live verification of the reactivation showed `observation_time` and
    `observation_lag_s` null on every single row, while per-series
    `observation_date` was populated. Snapshot-level staleness was unreadable
    with the data to compute it sitting one level down.

WHAT THIS IS NOT
    Not a fetch change, not a cache change, not a decision change. The field was
    already in the contract, already required by `validate_macro_shadow`, and
    already wired through `build_macro_shadow_from_snapshot` — which reads
    `snapshot["observation_time"]` and derives the lag from it. The only thing
    that changed is that the fetcher now fills it.

THE TWO CHOICES THIS FILE PINS
    * STALEST, not newest. FEDFUNDS is monthly and DGS10 daily; reporting the
      newest would let a two-day-old DGS10 hide a two-month-old FEDFUNDS.
    * The DAY string FRED gave, never the retrieval clock. The endpoint has day
      granularity; a `T00:00:00` suffix would claim precision we never received,
      and `retrieved_at` is a different fact that must not wear this name.

No test here can reach the network.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.services import macro_shadow as ms
from app.services import macro_shadow_fetch as msf

SYNTHETIC_KEY = "synthetic-not-a-real-fred-key"

FEDFUNDS, DGS10 = ms.SERIES_FEDFUNDS, ms.SERIES_DGS10
OLD_DATE = "2026-06-01"        # monthly series — the stale one
NEW_DATE = "2026-07-30"        # daily series — the fresh one
DECISION = "2026-08-01T07:47:03+00:00"


class _Settings:
    MACRO_SHADOW_FETCH_ENABLED = True
    FRED_API_KEY = SYNTHETIC_KEY
    MACRO_FRED_FETCH_ENABLED = False


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    msf.reset_cache_for_tests()
    monkeypatch.setattr(msf.job_guard, "remaining_budget", lambda job_id: None)
    yield
    msf.reset_cache_for_tests()


def _install(monkeypatch, dates, settings=None):
    """Each series answers with its own observation date."""
    monkeypatch.setattr(msf, "get_settings", lambda: settings or _Settings())
    real = httpx.AsyncClient

    def _h(request: httpx.Request) -> httpx.Response:
        sid = request.url.params.get("series_id")
        date = dates.get(sid, dates.get("*"))
        if date is None:
            return httpx.Response(200, json={"observations": []})
        return httpx.Response(200, json={
            "observations": [{"date": date, "value": "4.33"}]})

    def _client(*a, **kw):
        kw.pop("timeout", None)
        return real(transport=httpx.MockTransport(_h), **kw)
    monkeypatch.setattr(msf.httpx, "AsyncClient", _client)


def _snapshot(monkeypatch, dates, settings=None):
    _install(monkeypatch, dates, settings)
    return asyncio.run(msf.get_shadow_macro_snapshot())


def _built(snapshot, decision_time=DECISION):
    return ms.build_macro_shadow_from_snapshot(
        decision_time=decision_time, snapshot=snapshot,
        production_macro_score=50.0, production_macro_bias="neutral",
        production_macro_confidence=25.0, production_total_confidence=62.0,
        engine_count=9, publish_threshold=65.0,
        production_publish_verdict="skipped")


# ══════════════════════════════════════════════════════════════════════════════
# 1 · THE REGRESSION ITSELF — the field is no longer null
# ══════════════════════════════════════════════════════════════════════════════
def test_the_snapshot_reports_an_observation_time(monkeypatch):
    """The exact defect found in production: this was None on every row."""
    snap = _snapshot(monkeypatch, {FEDFUNDS: OLD_DATE, DGS10: NEW_DATE})
    assert snap["observation_time"] is not None, "the live defect is back"
    assert snap["observation_time"] == OLD_DATE


def test_the_payload_reports_both_fields(monkeypatch):
    snap = _snapshot(monkeypatch, {FEDFUNDS: OLD_DATE, DGS10: NEW_DATE})
    p = _built(snap)
    assert p["observation_time"] == OLD_DATE
    assert p["observation_lag_s"] is not None, "the live defect is back"
    # 2026-06-01T00:00 UTC → 2026-08-01T07:47:03 UTC
    expected = (datetime.fromisoformat(DECISION)
                - datetime(2026, 6, 1, tzinfo=timezone.utc)).total_seconds()
    assert p["observation_lag_s"] == pytest.approx(expected)
    assert ms.validate_macro_shadow(p) == []


# ══════════════════════════════════════════════════════════════════════════════
# 2 · STALEST, NOT NEWEST
# ══════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("dates,expected", [
    ({FEDFUNDS: OLD_DATE, DGS10: NEW_DATE}, OLD_DATE),   # stale first
    ({FEDFUNDS: NEW_DATE, DGS10: OLD_DATE}, OLD_DATE),   # order reversed
    ({FEDFUNDS: NEW_DATE, DGS10: NEW_DATE}, NEW_DATE),   # both fresh
])
def test_the_stalest_series_sets_the_snapshot_freshness(monkeypatch, dates, expected):
    """Whichever series is stale, IT is the answer — the field is a floor on
    freshness, not a best case. Both orderings are driven so the result cannot
    come from iteration order."""
    snap = _snapshot(monkeypatch, dates)
    assert snap["observation_time"] == expected


def test_a_fresh_series_cannot_hide_a_stale_one(monkeypatch):
    """The failure this choice exists to prevent, stated as a lag."""
    snap = _snapshot(monkeypatch, {FEDFUNDS: OLD_DATE, DGS10: NEW_DATE})
    lag = _built(snap)["observation_lag_s"]
    two_days = timedelta(days=2).total_seconds()
    assert lag > timedelta(days=55).total_seconds(), \
        "the monthly series' staleness was masked by the daily one"
    assert lag > two_days


# ══════════════════════════════════════════════════════════════════════════════
# 3 · IT IS THE OBSERVATION, NEVER THE CLOCK
# ══════════════════════════════════════════════════════════════════════════════
def test_it_is_not_the_retrieval_clock(monkeypatch):
    """`retrieved_at` is a different fact. Filling this field with it would make
    a two-month-old figure look seconds old — the exact inversion of the metric.
    Asserted against the value actually recorded on the same snapshot, so it
    cannot pass by comparing against a stale constant."""
    snap = _snapshot(monkeypatch, {FEDFUNDS: OLD_DATE, DGS10: NEW_DATE})
    retrieved = snap["series"][FEDFUNDS]["retrieved_at"]
    assert retrieved is not None, "precondition: the fetch recorded a clock"
    assert snap["observation_time"] != retrieved
    assert snap["observation_time"] in (OLD_DATE, NEW_DATE)
    # And it is genuinely older than the moment we asked.
    assert (ms._as_dt(snap["observation_time"])
            < ms._as_dt(retrieved))


def test_it_is_a_day_string_not_a_widened_timestamp(monkeypatch):
    """FRED's series endpoint has DAY granularity. Reporting
    `2026-06-01T00:00:00+00:00` would claim a midnight we were never told."""
    snap = _snapshot(monkeypatch, {FEDFUNDS: OLD_DATE, DGS10: NEW_DATE})
    assert snap["observation_time"] == "2026-06-01"
    assert "T" not in snap["observation_time"]
    # It still parses, through the convention the contract already documents.
    assert ms._as_dt(snap["observation_time"]) == datetime(
        2026, 6, 1, tzinfo=timezone.utc)


# ══════════════════════════════════════════════════════════════════════════════
# 4 · THE LAG IS MEASURED AT DECISION TIME, SO IT GROWS
# ══════════════════════════════════════════════════════════════════════════════
def test_the_lag_grows_with_the_decision_time(monkeypatch):
    """One snapshot, two decisions an hour apart. A lag frozen at fetch time
    would report the same number twice and hide a cache ageing under it."""
    snap = _snapshot(monkeypatch, {FEDFUNDS: OLD_DATE, DGS10: NEW_DATE})
    early = _built(snap, "2026-08-01T07:00:00+00:00")["observation_lag_s"]
    late = _built(snap, "2026-08-01T08:00:00+00:00")["observation_lag_s"]
    assert late - early == pytest.approx(3600.0)


def test_a_cache_hit_keeps_the_observation_time(monkeypatch):
    """The observation date does not change while a snapshot sits in cache, so
    the second caller must see the same one — and the SAME snapshot, not a
    second fetch."""
    _install(monkeypatch, {FEDFUNDS: OLD_DATE, DGS10: NEW_DATE})
    first = asyncio.run(msf.get_shadow_macro_snapshot())
    second = asyncio.run(msf.get_shadow_macro_snapshot())
    assert second["cache_status"] == "hit", "precondition: this is the cached path"
    assert second["observation_time"] == first["observation_time"] == OLD_DATE


# ══════════════════════════════════════════════════════════════════════════════
# 5 · ABSENCE STAYS ABSENCE — no invented freshness
# ══════════════════════════════════════════════════════════════════════════════
def test_a_snapshot_with_no_observations_reports_no_time(monkeypatch):
    """An empty response carries no date. Inventing one here would put a
    freshness claim on a snapshot that has no data behind it."""
    snap = _snapshot(monkeypatch, {"*": None})
    assert snap["observation_time"] is None
    assert _built(snap)["observation_lag_s"] is None


def test_a_failure_snapshot_reports_no_time(monkeypatch):
    def _boom(request):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(msf, "get_settings", lambda: _Settings())
    real = httpx.AsyncClient
    monkeypatch.setattr(msf.httpx, "AsyncClient", lambda *a, **kw: real(
        transport=httpx.MockTransport(_boom)))
    snap = asyncio.run(msf.get_shadow_macro_snapshot())
    assert snap is not None, "a failure is recorded, not swallowed"
    assert snap["observation_time"] is None
    assert _built(snap)["observation_lag_s"] is None


def test_one_series_without_a_date_does_not_stop_the_other(monkeypatch):
    """A partial snapshot still has a freshness floor — the series that DID
    report one."""
    snap = _snapshot(monkeypatch, {FEDFUNDS: None, DGS10: NEW_DATE})
    assert snap["observation_time"] == NEW_DATE


@pytest.mark.parametrize("bad", ["", "   ", "not-a-date", "2026-13-45", "01/06/2026"])
def test_an_unparseable_date_is_not_a_freshness_claim(monkeypatch, bad):
    """A malformed date must not become `observation_time`, and must not raise:
    this runs inside a fail-silent telemetry path."""
    snap = _snapshot(monkeypatch, {FEDFUNDS: bad, DGS10: NEW_DATE})
    assert snap["observation_time"] == NEW_DATE


def test_every_date_unparseable_leaves_the_field_null(monkeypatch):
    snap = _snapshot(monkeypatch, {"*": "not-a-date"})
    assert snap["observation_time"] is None


def test_the_helper_survives_hostile_series_shapes():
    """It reads a dict the fetcher built, but a telemetry helper that raises
    would cost the snapshot it is describing."""
    for hostile in ({}, {"x": None}, {"x": "string"}, {"x": []},
                    {"x": {"observation_date": None}},
                    {"x": {"observation_date": 12345}},
                    {"x": {}}):
        assert msf._snapshot_observation_time(hostile) is None


# ══════════════════════════════════════════════════════════════════════════════
# 6 · TELEMETRY ONLY — nothing else moved
# ══════════════════════════════════════════════════════════════════════════════
def test_the_decision_facing_fields_are_untouched(monkeypatch):
    """The whole point of the checkpoint: a freshness field appeared and
    NOTHING that reaches a decision changed."""
    snap = _snapshot(monkeypatch, {FEDFUNDS: OLD_DATE, DGS10: NEW_DATE})
    p = _built(snap)
    assert p["production_macro_score"] == 50.0
    assert p["production_macro_bias"] == "neutral"
    assert p["production_macro_confidence"] == 25.0
    assert p["score_if_restored"] == 50.0
    assert p["confidence_if_restored"] == 70.0
    assert p["delta_score"] == 0.0
    assert p["delta_confidence"] == round((70.0 - 25.0) / 9, 6)
    assert p["would_change_composite"] is False
    assert p["decision_isolation_verified"] is True
    assert p["mode"] == ms.MACRO_SHADOW_MODE
    assert p["version"] == ms.MACRO_SHADOW_VERSION


def test_the_request_count_is_unchanged(monkeypatch):
    """A freshness field must not have cost an extra call."""
    calls = []
    monkeypatch.setattr(msf, "get_settings", lambda: _Settings())
    real = httpx.AsyncClient

    def _h(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.params.get("series_id"))
        return httpx.Response(200, json={
            "observations": [{"date": OLD_DATE, "value": "4.33"}]})
    monkeypatch.setattr(msf.httpx, "AsyncClient", lambda *a, **kw: real(
        transport=httpx.MockTransport(_h)))

    asyncio.run(msf.get_shadow_macro_snapshot())
    asyncio.run(msf.get_shadow_macro_snapshot())
    asyncio.run(msf.get_shadow_macro_snapshot())
    assert sorted(calls) == sorted(ms.SCORED_SERIES), calls
    assert len(calls) == 2, "one cycle per TTL, regardless of caller count"


def test_the_production_fetch_flag_is_still_off():
    from app.config import Settings
    assert Settings.model_fields["MACRO_FRED_FETCH_ENABLED"].default is False


def test_the_observation_time_never_carries_the_key(monkeypatch):
    """Belt and braces: the field is derived from a response body, but it is
    still a field on a payload that gets persisted."""
    snap = _snapshot(monkeypatch, {FEDFUNDS: OLD_DATE, DGS10: NEW_DATE})
    import json as _json
    blob = _json.dumps(_built(snap), default=str)
    assert SYNTHETIC_KEY not in blob
    assert "api_key" not in blob
