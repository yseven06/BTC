"""CP-CMV2-M3 — the trade-management roll-up, attached to a similarity verdict.

WHAT THIS ADDS
    `app/services/similarity.py` answers "how did setups that LOOKED like this
    one RESOLVE?". It reads SignalSnapshot + SignalPerformance and has never
    read a trade path, so it cannot answer "and how was the trade MANAGED once
    it was open?". `tm_stats` already holds that answer for 234 of 705 live
    cells; until now nothing consumed it next to similarity.

WHAT IT DELIBERATELY DOES NOT TOUCH
    `similarity.py` is not modified — not one byte. The distance function, the
    candidate pool and MIN_SIMILAR_MATCHES are untouched, and the enrichment
    hangs off the returned dict. That is what lets "existing similarity
    behaviour is unchanged" be a structural claim rather than a hopeful one, and
    a test below pins the module's source hash to keep it that way.

THE GATE
    `MIN_TM_SAMPLES` — the SAME constant `compute_coin_tm_summary` enforces,
    applied to the SELECTED bucket's own `n`. A coin with 60 paths overall can
    still have 3 in `trending_bear`; reporting rates off 3 is exactly what the
    gate exists to prevent.

THE ALLOWLIST
    Regime buckets are named, not discovered. Measured live on 2026-08-02 over
    705 filled cells: `_all` 103 above threshold, `trending_bull` 44,
    `low_volume` 37, `trending_bear` 29, `ranging` 21, `volatile_high` **0**.

No test here touches a database, a network or a file.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest

from app.services import coin_memory as cm
from app.services.coin_memory import (
    CACHE_ABSENT, CACHE_EMPTY, CACHE_PRESENT,
    ENRICHMENT_ALL_BUCKET, ENRICHMENT_FIELDS, ENRICHMENT_REGIME_BUCKETS,
    ENRICH_ALL_BELOW_GATE, ENRICH_INTERNAL, ENRICH_NO_MEMORY,
    ENRICH_NO_SIMILARITY, ENRICH_NO_TM_CACHE, ENRICH_REGIME_BELOW_GATE,
    ENRICH_REGIME_NOT_ALLOWED,
    MIN_TM_SAMPLES, SIMILARITY_ENRICHMENT_VERSION,
    build_similarity_coin_memory_enrichment as enrich,
)

SIMILAR_OK = {"has_data": True, "match_count": 12, "wins": 7, "losses": 5,
              "win_rate": 58.3, "most_common_outcome": "tp1_then_sl"}
SIMILAR_EMPTY = {"has_data": False, "match_count": 3, "needed": 8}


def _bucket(n, *, tp1=None, tp2=0, tp3=0, give_back=0, tight_sl=0, sub1_rr=0):
    """A bucket shaped like the real fold output, with enough per-field N that
    the metric arithmetic produces non-None values."""
    tp1 = n // 2 if tp1 is None else tp1
    return {
        "n": n,
        "tp1": tp1, "tp2": tp2, "tp3": tp3, "give_back": give_back,
        "tight_sl": tight_sl, "sub1_rr": sub1_rr,
        "mfe_r_sum": 1.4 * n, "mfe_r_n": n, "mfe_r_sumsq": 2.6 * n,
        "mae_r_sum": -0.6 * n, "mae_r_n": n, "mae_r_sumsq": 0.5 * n,
        "mfe_atr_sum": 2.0 * n, "mfe_atr_n": n,
        "mae_atr_sum": -0.9 * n, "mae_atr_n": n,
        "realized_sum": 0.35 * n, "realized_n": n, "realized_sumsq": 0.9 * n,
        "planned_rr_tp1_sum": 1.8 * n, "planned_rr_tp1_n": n,
        "bars_to_tp1_sum": 9 * n, "bars_to_tp1_n": n,
        "bars_total_sum": 21 * n, "bars_total_n": n,
    }


def _sum_n(buckets):
    """Total samples across buckets — tolerant, because some tests deliberately
    pass corrupt buckets and the HARNESS must not be what raises."""
    total = 0
    for b in (buckets or {}).values():
        try:
            total += int((b or {}).get("n", 0) or 0)
        except (AttributeError, TypeError, ValueError):
            continue
    return total


def _mem(buckets, *, total_signals=40, updated_minutes_ago=5, sample_count=None):
    stats = dict(buckets)
    return NS(
        symbol="BTCUSDT", timeframe="15m",
        tm_stats=stats,
        tm_sample_count=sample_count if sample_count is not None else _sum_n(buckets),
        total_signals=total_signals, wins=0, losses=0,
        last_updated_at=datetime.now(timezone.utc)
        - timedelta(minutes=updated_minutes_ago),
    )


def _tel(out):
    """The function returns the enrichment block directly — `similar` is a
    SIBLING on the response and is never wrapped."""
    return out


# ══════════════════════════════════════════════════════════════════════════════
# 1 · THE GATE — above, below, absent
# ══════════════════════════════════════════════════════════════════════════════
def test_an_above_threshold_all_cell_produces_enrichment():
    out = enrich(SIMILAR_OK, _mem({ENRICHMENT_ALL_BUCKET: _bucket(MIN_TM_SAMPLES)}), None)
    t = _tel(out)
    assert t["coin_memory_enrichment_applied"] is True
    assert t["selected_bucket"] == ENRICHMENT_ALL_BUCKET
    assert t["cell_sample_count"] == MIN_TM_SAMPLES
    assert t["cell_threshold"] == MIN_TM_SAMPLES
    assert t["fields"], "enrichment claimed to apply but surfaced no field"
    assert t["enrichment_fields_used"] == len(t["fields"])
    assert t["enrichment_fields_available"] >= t["enrichment_fields_used"]
    assert t["fallback_reason"] is None
    assert t["legacy_fallback_used"] is False
    assert t["graceful_degradation_verified"] is True


def test_a_below_threshold_cell_produces_no_enrichment():
    """One sample under the gate is the whole difference — a rate computed off
    9 paths is exactly what the gate exists to suppress."""
    out = enrich(SIMILAR_OK,
                 _mem({ENRICHMENT_ALL_BUCKET: _bucket(MIN_TM_SAMPLES - 1)}), None)
    t = _tel(out)
    assert t["coin_memory_enrichment_applied"] is False
    assert t["selected_bucket"] is None
    assert t["fallback_reason"] == ENRICH_ALL_BELOW_GATE
    assert "fields" not in t
    assert t["enrichment_fields_used"] == 0


def test_the_gate_boundary_is_exact():
    below = _tel(enrich(SIMILAR_OK,
                        _mem({ENRICHMENT_ALL_BUCKET: _bucket(MIN_TM_SAMPLES - 1)}), None))
    at = _tel(enrich(SIMILAR_OK,
                     _mem({ENRICHMENT_ALL_BUCKET: _bucket(MIN_TM_SAMPLES)}), None))
    assert below["coin_memory_enrichment_applied"] is False
    assert at["coin_memory_enrichment_applied"] is True


def test_the_gate_is_the_same_constant_the_reader_enforces():
    """Two thresholds that drift apart would let the panel show a rate the
    reader refuses to."""
    assert cm.MIN_TM_SAMPLES is MIN_TM_SAMPLES
    below = cm.compute_coin_tm_summary(
        _mem({ENRICHMENT_ALL_BUCKET: _bucket(MIN_TM_SAMPLES - 1)}), None)
    assert below["below_cell_threshold"] is True
    assert below["metrics"] is None


# ══════════════════════════════════════════════════════════════════════════════
# 2 · THE FALLBACK CHAIN
# ══════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("regime", list(ENRICHMENT_REGIME_BUCKETS))
def test_an_allowlisted_regime_is_used_when_it_clears_the_gate(regime):
    """trending_bull / low_volume / trending_bear — each measured live with
    44 / 37 / 29 above-threshold cells."""
    out = enrich(SIMILAR_OK, _mem({
        ENRICHMENT_ALL_BUCKET: _bucket(80),
        regime: _bucket(MIN_TM_SAMPLES + 4),
    }), regime)
    t = _tel(out)
    assert t["coin_memory_enrichment_applied"] is True
    assert t["selected_bucket"] == regime, "the regime bucket was not preferred"
    assert t["selected_regime"] == regime
    assert t["cell_sample_count"] == MIN_TM_SAMPLES + 4
    assert t["fallback_reason"] is None


@pytest.mark.parametrize("regime", list(ENRICHMENT_REGIME_BUCKETS))
def test_an_allowlisted_regime_below_the_gate_falls_back_to_all(regime):
    out = enrich(SIMILAR_OK, _mem({
        ENRICHMENT_ALL_BUCKET: _bucket(60),
        regime: _bucket(MIN_TM_SAMPLES - 1),
    }), regime)
    t = _tel(out)
    assert t["coin_memory_enrichment_applied"] is True
    assert t["selected_bucket"] == ENRICHMENT_ALL_BUCKET
    assert t["fallback_reason"] == ENRICH_REGIME_BELOW_GATE, \
        "the fallback happened but did not say why"


@pytest.mark.parametrize("regime", ["ranging", "volatile_high"])
def test_an_excluded_regime_never_supplies_statistics(regime):
    """`volatile_high` had ZERO above-threshold cells live, `ranging` is out of
    this checkpoint's scope. Neither may be read even when its bucket is fat."""
    out = enrich(SIMILAR_OK, _mem({
        ENRICHMENT_ALL_BUCKET: _bucket(60),
        regime: _bucket(500),          # deliberately huge — must still be ignored
    }), regime)
    t = _tel(out)
    assert t["selected_bucket"] == ENRICHMENT_ALL_BUCKET, \
        f"{regime} was read despite being off the allowlist"
    assert t["fallback_reason"] == ENRICH_REGIME_NOT_ALLOWED
    assert t["cell_sample_count"] == 60, "the excluded bucket's n leaked through"


@pytest.mark.parametrize("regime", ["ranging", "volatile_high"])
def test_an_excluded_regime_with_no_all_bucket_yields_nothing(regime):
    out = enrich(SIMILAR_OK, _mem({regime: _bucket(500)}), regime)
    t = _tel(out)
    assert t["coin_memory_enrichment_applied"] is False
    assert t["selected_bucket"] is None
    assert "fields" not in t


def test_the_allowlist_excludes_the_two_regimes_by_name():
    assert "ranging" not in ENRICHMENT_REGIME_BUCKETS
    assert "volatile_high" not in ENRICHMENT_REGIME_BUCKETS
    assert set(ENRICHMENT_REGIME_BUCKETS) == {
        "trending_bull", "low_volume", "trending_bear"}


def test_no_coin_memory_at_all_degrades_by_name():
    t = _tel(enrich(SIMILAR_OK, None, "trending_bull"))
    assert t["coin_memory_enrichment_applied"] is False
    assert t["fallback_reason"] == ENRICH_NO_MEMORY
    assert t["cache_status"] == CACHE_ABSENT
    assert t["cache_age_s"] is None


def test_a_row_without_tm_stats_flags_the_legacy_fallback():
    """192 live rows, 20 of them with no tm_stats. Those still carry the pre-CM2
    aggregate, which the response already serves under `coin_memory` — this
    flags it rather than copying it, because two copies of one number is how
    they start disagreeing."""
    mem = _mem({}, total_signals=31)
    mem.tm_stats = None
    t = _tel(enrich(SIMILAR_OK, mem, "trending_bull"))
    assert t["coin_memory_enrichment_applied"] is False
    assert t["fallback_reason"] == ENRICH_NO_TM_CACHE
    assert t["legacy_fallback_used"] is True
    assert t["cache_status"] == CACHE_EMPTY
    assert "fields" not in t, "the legacy path must not fabricate v2 fields"


def test_a_row_with_neither_tm_stats_nor_history_claims_no_legacy():
    mem = _mem({}, total_signals=0)
    mem.tm_stats = {}
    t = _tel(enrich(SIMILAR_OK, mem, None))
    assert t["legacy_fallback_used"] is False


def test_the_cm_v2_namespace_is_never_read_as_a_regime():
    """`v1_tm_buckets` strips it; without that a caller passing regime='cm_v2'
    would be served the contract blob as though it were trade statistics."""
    mem = _mem({ENRICHMENT_ALL_BUCKET: _bucket(40)})
    mem.tm_stats[cm.CM_V2_NAMESPACE] = {"n": 9999, "last_fold": "x"}
    t = _tel(enrich(SIMILAR_OK, mem, cm.CM_V2_NAMESPACE))
    assert t["selected_bucket"] == ENRICHMENT_ALL_BUCKET
    assert t["cell_sample_count"] == 40, "the cm_v2 blob was read as a bucket"


def test_a_cell_holding_only_the_cm_v2_namespace_reads_as_an_EMPTY_cache():
    """WHERE `v1_tm_buckets` IS ACTUALLY LOAD-BEARING.

    The allowlist already stops `cm_v2` being selected as a regime, so the
    regime path alone does not prove the strip matters. It matters HERE: a cell
    that has been through the v2 fold but never through a v1 fold carries only
    the namespace. Without the strip that cell looks POPULATED, and the reason
    reported becomes "the bucket is below the gate" instead of "there is no
    rollup at all" — a materially different diagnosis for the same cell, and the
    one that would send the next reader looking in the wrong place.
    """
    mem = _mem({}, total_signals=17)
    mem.tm_stats = {cm.CM_V2_NAMESPACE: {"n": 9999, "last_fold": "x"}}
    t = _tel(enrich(SIMILAR_OK, mem, None))
    assert t["fallback_reason"] == ENRICH_NO_TM_CACHE, \
        "a cm_v2-only cell was mistaken for a populated rollup"
    assert t["cache_status"] == CACHE_EMPTY
    assert t["legacy_fallback_used"] is True
    assert t["cell_sample_count"] == 0


def test_the_cm_v2_namespace_literal_is_pinned():
    """Pinned as a LITERAL on purpose. A sabotage run renamed the constant and
    `tests/test_cmv2a_contract.py` stayed green — that suite pins the payload
    SHAPE but never the namespace string itself. This enrichment depends on the
    strip finding it, so the name is pinned where the dependency lives.
    """
    assert cm.CM_V2_NAMESPACE == "cm_v2"
    assert cm.v1_tm_buckets({"cm_v2": {"x": 1}, "_all": {"n": 3}}) == {"_all": {"n": 3}}


# ══════════════════════════════════════════════════════════════════════════════
# 3 · CACHE BEHAVIOUR
# ══════════════════════════════════════════════════════════════════════════════
def test_cache_status_and_age_are_reported():
    out = enrich(SIMILAR_OK,
                 _mem({ENRICHMENT_ALL_BUCKET: _bucket(30)}, updated_minutes_ago=7),
                 None)
    t = _tel(out)
    assert t["cache_status"] == CACHE_PRESENT
    assert t["cache_age_s"] == pytest.approx(7 * 60, abs=30)


def test_a_naive_timestamp_is_treated_as_utc_not_dropped():
    mem = _mem({ENRICHMENT_ALL_BUCKET: _bucket(30)})
    mem.last_updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    t = _tel(enrich(SIMILAR_OK, mem, None))
    assert t["cache_age_s"] is not None
    assert abs(t["cache_age_s"]) < 120


def test_an_unusable_timestamp_reports_no_age_rather_than_a_wrong_one():
    mem = _mem({ENRICHMENT_ALL_BUCKET: _bucket(30)})
    mem.last_updated_at = "not-a-datetime"
    t = _tel(enrich(SIMILAR_OK, mem, None))
    assert t["cache_age_s"] is None
    assert t["coin_memory_enrichment_applied"] is True, \
        "a missing clock must not cost the enrichment"


def test_a_rebuilt_cache_is_read_without_special_casing():
    """tm_stats is a derivable cache over signal_trade_path; drop-and-rebuild is
    safe, so a freshly rebuilt bucket must read identically to a folded one."""
    folded = _tel(enrich(SIMILAR_OK, _mem({ENRICHMENT_ALL_BUCKET: _bucket(25)}), None))
    rebuilt = _tel(enrich(SIMILAR_OK, _mem({ENRICHMENT_ALL_BUCKET: _bucket(25)},
                                           updated_minutes_ago=0), None))
    assert folded["fields"] == rebuilt["fields"]
    assert folded["cell_sample_count"] == rebuilt["cell_sample_count"]


@pytest.mark.parametrize("broken", [
    {"_all": None},
    {"_all": "not-a-dict"},
    {"_all": []},
    {"_all": {"n": "many"}},
    {"_all": {"n": -5}},
    {"_all": {}},
])
def test_a_corrupt_cache_degrades_gracefully(broken):
    t = _tel(enrich(SIMILAR_OK, _mem(broken), None))
    assert t["coin_memory_enrichment_applied"] is False
    assert t["fallback_reason"] is not None
    assert isinstance(t["cell_threshold"], int)


def test_a_hostile_tm_stats_object_never_raises():
    class _Hostile(dict):
        def items(self):
            raise RuntimeError("hostile items()")

    mem = _mem({})
    # Deliberately NON-EMPTY: `v1_tm_buckets` does `(tm or {}).items()`, so an
    # empty hostile dict is falsy and never gets its `items()` called — the test
    # would then pass while exercising nothing.
    mem.tm_stats = _Hostile({ENRICHMENT_ALL_BUCKET: {"n": 30}})
    t = _tel(enrich(SIMILAR_OK, mem, None))
    assert t["fallback_reason"] == ENRICH_INTERNAL
    assert t["graceful_degradation_verified"] is False, \
        "the exception guard fired but reported a clean run"


# ══════════════════════════════════════════════════════════════════════════════
# 4 · NO SHARED STATE, NO CROSS-CELL LEAKAGE
# ══════════════════════════════════════════════════════════════════════════════
def test_the_input_similarity_dict_is_never_mutated():
    original = dict(SIMILAR_OK)
    out = enrich(SIMILAR_OK, _mem({ENRICHMENT_ALL_BUCKET: _bucket(30)}), None)
    assert SIMILAR_OK == original, "the caller's dict was mutated"
    assert out is not SIMILAR_OK
    assert set(SIMILAR_OK) == set(original), "a key was added to the caller's dict"


def test_the_memory_object_is_never_mutated():
    mem = _mem({ENRICHMENT_ALL_BUCKET: _bucket(30), "trending_bull": _bucket(15)})
    import copy as _copy
    before = _copy.deepcopy(mem.tm_stats)
    enrich(SIMILAR_OK, mem, "trending_bull")
    assert mem.tm_stats == before, "tm_stats was mutated by a read-only path"


def test_two_calls_share_no_mutable_state():
    mem = _mem({ENRICHMENT_ALL_BUCKET: _bucket(30)})
    a = _tel(enrich(SIMILAR_OK, mem, None))
    b = _tel(enrich(SIMILAR_OK, mem, None))
    assert a is not b
    assert a["fields"] is not b["fields"]
    a["fields"]["poisoned"] = True
    assert "poisoned" not in b["fields"]


def test_different_coins_do_not_bleed_into_each_other():
    btc = _mem({ENRICHMENT_ALL_BUCKET: _bucket(40, tp1=40)})
    eth = _mem({ENRICHMENT_ALL_BUCKET: _bucket(40, tp1=0)})
    t_btc = _tel(enrich(SIMILAR_OK, btc, None))
    t_eth = _tel(enrich(SIMILAR_OK, eth, None))
    assert t_btc["fields"]["tp1_rate"] == 100.0
    assert t_eth["fields"]["tp1_rate"] == 0.0


def test_regime_cells_do_not_bleed_into_each_other():
    mem = _mem({
        ENRICHMENT_ALL_BUCKET: _bucket(60, tp1=0),
        "trending_bull": _bucket(20, tp1=20),
        "trending_bear": _bucket(20, tp1=10),
    })
    bull = _tel(enrich(SIMILAR_OK, mem, "trending_bull"))
    bear = _tel(enrich(SIMILAR_OK, mem, "trending_bear"))
    all_ = _tel(enrich(SIMILAR_OK, mem, None))
    assert bull["fields"]["tp1_rate"] == 100.0
    assert bear["fields"]["tp1_rate"] == 50.0
    assert all_["fields"]["tp1_rate"] == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# 5 · SIMILARITY ITSELF IS UNCHANGED
# ══════════════════════════════════════════════════════════════════════════════
def test_the_similarity_payload_is_returned_to_the_caller_untouched():
    """The STRONGEST form of the parity claim: the enrichment is a SIBLING, so
    `similar` is not copied, wrapped or extended — it comes back to the response
    exactly as `find_similar_setups` produced it.

    This is what the frontend asymmetry demands. `similar_setups` is typed at
    frontend/src/lib/api.ts:402 and narrowed at IntelligencePanel.tsx:211, so a
    key added there would have to be argued safe; a key that never lands there
    needs no argument.
    """
    for payload in (SIMILAR_OK, SIMILAR_EMPTY):
        snapshot = dict(payload)
        out = enrich(payload, _mem({ENRICHMENT_ALL_BUCKET: _bucket(30)}), None)
        assert payload == snapshot, "the similarity payload was modified"
        assert "has_data" not in out, \
            "the enrichment absorbed similarity's own keys — it must stay a sibling"
        assert "match_count" not in out
        assert out is not payload


def test_the_enrichment_never_reports_similaritys_verdict():
    """It must not be able to make an empty similarity look answered, and the
    only way to guarantee that is to carry none of its fields."""
    rich = enrich(SIMILAR_EMPTY, _mem({ENRICHMENT_ALL_BUCKET: _bucket(500)}), None)
    poor = enrich(SIMILAR_OK, _mem({ENRICHMENT_ALL_BUCKET: _bucket(500)}), None)
    for key in ("has_data", "match_count", "needed", "wins", "losses",
                "win_rate", "most_common_outcome"):
        assert key not in rich, f"similarity key {key} leaked into the enrichment"
    # Identical coin memory ⇒ identical enrichment, whatever similarity said.
    assert rich["selected_bucket"] == poor["selected_bucket"]
    assert rich["cell_sample_count"] == poor["cell_sample_count"]
    assert rich["fields"] == poor["fields"]


def test_similarity_module_source_is_untouched():
    """A structural pin, not a style rule: this checkpoint's parity claim rests
    on `similarity.py` not being edited. If this fails, the claim needs
    re-deriving — do not just update the hash."""
    import hashlib
    import inspect
    from app.services import similarity as sim
    src = inspect.getsource(sim).encode("utf-8").replace(b"\r\n", b"\n")
    assert hashlib.sha256(src).hexdigest() == (
        "01acf804b2b9243619ac5cabb58f6c2637a808e9af0144b53581a38c034b0440"), \
        "similarity.py changed — re-derive the parity claim before updating this"


def test_the_similarity_gate_constant_is_unchanged():
    from app.services import similarity as sim
    assert sim.MIN_SIMILAR_MATCHES == 8
    assert sim.TOP_K == 50
    assert sim.MAX_DISTANCE == 1.0


def test_the_enrichment_produces_no_decision_surface():
    """It is descriptive. A score/recommendation/direction key here would be a
    decision leaking into a read-only panel."""
    t = _tel(enrich(SIMILAR_OK, _mem({ENRICHMENT_ALL_BUCKET: _bucket(40)}), None))
    banned = ("score", "recommendation", "action", "direction", "signal",
              "weight", "confidence", "publish", "verdict", "adjust")
    for key in list(t) + list(t.get("fields") or {}):
        low = key.lower()
        for b in banned:
            assert b not in low, f"decision-shaped key in enrichment: {key}"


# ══════════════════════════════════════════════════════════════════════════════
# 6 · TELEMETRY CONTRACT
# ══════════════════════════════════════════════════════════════════════════════
REQUIRED_TELEMETRY = (
    "coin_memory_enrichment_applied", "selected_bucket", "selected_regime",
    "cell_sample_count", "cell_threshold", "fallback_reason",
    "legacy_fallback_used", "enrichment_fields_available",
    "enrichment_fields_used", "cache_status", "cache_age_s",
    "graceful_degradation_verified",
)


@pytest.mark.parametrize("case", [
    ("applied", {ENRICHMENT_ALL_BUCKET: _bucket(30)}, None),
    ("below-gate", {ENRICHMENT_ALL_BUCKET: _bucket(2)}, None),
    ("excluded-regime", {ENRICHMENT_ALL_BUCKET: _bucket(30)}, "volatile_high"),
    ("regime-hit", {ENRICHMENT_ALL_BUCKET: _bucket(30),
                    "low_volume": _bucket(14)}, "low_volume"),
])
def test_every_telemetry_key_is_always_present(case):
    _, buckets, regime = case
    t = _tel(enrich(SIMILAR_OK, _mem(buckets), regime))
    for key in REQUIRED_TELEMETRY:
        assert key in t, f"missing telemetry key: {key}"
    assert t["version"] == SIMILARITY_ENRICHMENT_VERSION


def test_telemetry_is_present_even_with_no_inputs_at_all():
    for args in ((None, None, None), (SIMILAR_OK, None, None), (None, None, "x")):
        t = _tel(enrich(*args))
        for key in REQUIRED_TELEMETRY:
            assert key in t


def test_a_non_mapping_similarity_payload_is_named_not_swallowed():
    for bad in (None, [], "x", 7):
        t = _tel(enrich(bad, _mem({ENRICHMENT_ALL_BUCKET: _bucket(30)}), None))
        assert t["fallback_reason"] == ENRICH_NO_SIMILARITY


def test_available_never_undercounts_used():
    mem = _mem({ENRICHMENT_ALL_BUCKET: _bucket(30)})
    t = _tel(enrich(SIMILAR_OK, mem, None))
    assert t["enrichment_fields_available"] >= t["enrichment_fields_used"]
    assert t["enrichment_fields_used"] <= len(ENRICHMENT_FIELDS)


def test_the_telemetry_carries_no_secret_or_identifier():
    t = _tel(enrich(SIMILAR_OK, _mem({ENRICHMENT_ALL_BUCKET: _bucket(30)}), None))
    import json
    blob = json.dumps(t, default=str).lower()
    for banned in ("api_key", "apikey", "token", "secret", "password",
                   "authorization", "http", "://"):
        assert banned not in blob, f"telemetry leaked {banned}"


# ══════════════════════════════════════════════════════════════════════════════
# 7 · READ-ONLY: NO WRITE, NO DDL, NO MIGRATION
# ══════════════════════════════════════════════════════════════════════════════
def test_the_enrichment_touches_no_database_api():
    """A pure function over an already-loaded row. If it ever grows a session
    argument or a query, that is a different checkpoint."""
    import inspect
    src = inspect.getsource(cm.build_similarity_coin_memory_enrichment)
    for banned in ("db.execute", "session", "await ", "commit", "flush",
                   "insert", "update(", "delete(", "ALTER", "CREATE"):
        assert banned not in src, f"enrichment reaches for {banned}"
    assert "async def" not in src, "enrichment became async — it takes no I/O"


def test_the_enrichment_signature_takes_no_session():
    import inspect
    params = list(inspect.signature(cm.build_similarity_coin_memory_enrichment)
                  .parameters)
    assert params == ["similar", "mem", "regime"]


def test_the_route_adds_no_query_for_the_enrichment():
    """`mem` and `regime` are already loaded by the intelligence route, so the
    enrichment must reuse them rather than fetch again."""
    import inspect
    from app.api.routes import signals as route_mod
    src = inspect.getsource(route_mod.signal_intelligence)
    assert "build_similarity_coin_memory_enrichment(similar, mem, regime)" in src, \
        "the enrichment is not wired, or does not reuse the loaded mem/regime"
    assert '"similar_setups_coin_memory": similar_coin_memory,' in src, \
        "the enrichment is not served as a SIBLING key"
    assert "similar = build_similarity_coin_memory_enrichment" not in src, \
        "the similarity payload is being rebound instead of left alone"
    # Exactly the pre-existing selects: Signal, SignalSnapshot, CoinMemory.
    assert src.count("await db.execute") == 3, \
        "the intelligence route gained or lost a query"


def test_the_similarity_payload_reaches_the_response_unrebound():
    """`similar_setups` must still be the object `find_similar_setups` returned.
    A rebind is what the frontend asymmetry rules out."""
    import inspect
    from app.api.routes import signals as route_mod
    src = inspect.getsource(route_mod.signal_intelligence)
    assert '"similar_setups": similar,' in src

    # AST, not substring matching. A sabotage run slipped
    # `similar.update(similar_coin_memory)` past a line-prefix check, because a
    # method call is not an assignment — the very weakness this walk removes.
    import ast
    import textwrap
    tree = ast.parse(textwrap.dedent(src))

    rebinds, mutations = [], []
    for node in ast.walk(tree):
        # `similar = ...`
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "similar":
                    rebinds.append(ast.unparse(node))
                # `similar[...] = ...`
                if isinstance(tgt, ast.Subscript) and \
                        isinstance(tgt.value, ast.Name) and tgt.value.id == "similar":
                    mutations.append(ast.unparse(node))
        # `similar.update(...)`, `similar.setdefault(...)`, `similar.pop(...)` …
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and isinstance(node.func.value, ast.Name) \
                and node.func.value.id == "similar":
            mutations.append(ast.unparse(node))

    assert mutations == [], f"the similarity payload is mutated in the route: {mutations}"
    # Both rebinds predate this checkpoint: the engine call and the route's own
    # except-fallback. Nothing this checkpoint added may appear here.
    assert len(rebinds) == 2, f"`similar` is assigned {len(rebinds)} times: {rebinds}"
    assert "find_similar_setups" in rebinds[0]
    assert "has_data" in rebinds[1]
    assert not any("coin_memory" in r for r in rebinds), \
        "the enrichment rebinds the similarity payload"
