"""Candidate decision logging — the write side of P2.2-a.

Records EVERY scored evaluation, published or not, into
`signal_decision_candidates`. Deliberately a separate module from
`scheduler.py`: the live decision file gets three one-line calls and nothing
else, and this logic stays unit-testable without standing up a scheduler.

THREE GUARANTEES, IN ORDER OF IMPORTANCE
----------------------------------------
1. It cannot change a decision. Every call site passes an already-final verdict;
   the return value is discarded and no branch reads it.

2. It cannot break the caller. The whole body is inside try/except, and the
   INSERT itself runs in a SAVEPOINT. This is not defensive padding — the
   surrounding transaction may be holding a staged reversal close (the old
   signal's INVALIDATED outcome, its coin-memory fold, its lifecycle event,
   scheduler.py:368-402). A statement error without a savepoint aborts the whole
   PostgreSQL transaction, and the caller's `except` at scheduler.py:505 would
   then roll all of that back. That is the exact fail-open-becomes-fail-closed
   trap documented at tracker.py:44-52, reached from the other direction.

3. It cannot duplicate. `ON CONFLICT DO NOTHING` on
   (asset_id, timeframe, evaluated_bar_time, policy_version, source).
   Signal generation has NO single-writer guard — `max_instances=1` is per job
   id, so signals_1h and signals_15m routinely overlap, and `trigger_job_now`
   bypasses APScheduler entirely with a raw create_task. The database key, not
   an in-process flag, is what makes this write safe under that pre-existing
   race.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.decision_candidate import (
    CANDIDATE_POLICY_VERSION,
    CANDIDATE_SCHEMA_VERSION,
    CAPTURE_FULL,
    SHADOW_UNDECIDABLE,
    SIMILARITY_UNAVAILABLE,
    SOURCE_SCHEDULER,
    SignalDecisionCandidate,
    classify_birth_shadow,
)
from app.services.trade_geometry import dist_pct, planned_rr

logger = logging.getLogger(__name__)

# Engines whose supporting_data carries the geometry-side volume reading. Kept
# as a constant so the "which volume_ratio" question has exactly one answer here.
_VOLUME_ENGINE = "volume_analysis"


def _json_safe(value: Any, _depth: int = 0) -> Any:
    """Coerce a value into something json.dumps can handle.

    Engine payloads carry numpy scalars, pandas Timestamps and occasionally
    NaN — all of which either raise on serialisation or land in the column as
    something no reader can parse back. Anything unrecognised degrades to its
    string form rather than blowing up the insert; losing fidelity on one nested
    field is always better than losing the whole row.
    """
    if _depth > 6:                      # runaway nesting guard
        return str(value)
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        # NaN / ±inf are valid Python floats but not valid JSON.
        return value if value == value and abs(value) != float("inf") else None
    if isinstance(value, dict):
        return {str(k): _json_safe(v, _depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v, _depth + 1) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    # numpy scalars and anything else with a Python-native view
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _json_safe(item(), _depth + 1)
        except Exception:  # noqa: BLE001
            pass
    return str(value)


def _f(value: Any) -> Optional[float]:
    """Best-effort float, None on anything non-numeric or non-finite."""
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and abs(out) != float("inf") else None


def _bar_time(df) -> Optional[datetime]:
    """The last bar the engines actually scored, as tz-aware UTC.

    This is the idempotency key's time component. Wall clock deliberately is not:
    a retry, an APScheduler misfire replay and an admin trigger_job_now all
    produce a different `now` for the *same* evaluation, so `now` cannot identify
    one. The scored bar can.
    """
    try:
        if df is None or len(df) == 0:
            return None
        import pandas as pd

        stamp = pd.Timestamp(df.index[-1])
        stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
        return stamp.to_pydatetime()
    except Exception:  # noqa: BLE001
        return None


def _engine_scores(engine_results: Any) -> Optional[Dict[str, Any]]:
    """Reshape the engine result list into the same {name: {...}} object that
    SignalSnapshot.engine_scores already uses, so the two are directly joinable
    rather than needing a shape translation at analysis time."""
    if not isinstance(engine_results, list):
        return None
    out: Dict[str, Any] = {}
    for res in engine_results:
        if not isinstance(res, dict):
            continue
        name = res.get("engine_name")
        if not name:
            continue
        out[str(name)] = {
            "score": _f(res.get("score")),
            "bias": res.get("bias"),
            "confidence": _f(res.get("confidence")),
        }
    return out or None


def _volume_ratio_geometry(engine_results: Any) -> Optional[float]:
    """The VOLUME ENGINE's own ratio — a different measurement from the regime
    detector's bar-volume/20-bar-mean. Both are recorded, under distinct names,
    because they are not interchangeable and silently mixing them would corrupt
    every downstream comparison."""
    if not isinstance(engine_results, list):
        return None
    for res in engine_results:
        if isinstance(res, dict) and res.get("engine_name") == _VOLUME_ENGINE:
            support = res.get("supporting_data")
            if isinstance(support, dict):
                return _f(support.get("volume_trend_ratio"))
    return None


def _adaptive_state_entry(
    snapshot: Optional[Dict[str, Any]],
    decision: Any,
    evaluated_at: Any,
) -> Optional[Dict[str, Any]]:
    """Complete the decision-time weight snapshot with what only this layer knows.

    coin_memory builds the weight chain — it is the only place that still holds
    the memory row the decision read. Direction and the decision timestamp are
    added here, where they are authoritative; deriving them upstream would give
    the same fact two sources.

    A copy is taken because the caller's dict is reused across the three
    record_candidate sites in one sweep; mutating it here would let a later row
    change what an earlier one recorded.
    """
    if not snapshot:
        return None
    entry = dict(snapshot)
    direction = None
    if isinstance(decision, dict):
        direction = decision.get("direction")
    entry["direction"] = direction
    entry["decision_evaluated_at"] = (
        evaluated_at.isoformat() if hasattr(evaluated_at, "isoformat") else evaluated_at
    )
    return entry


def build_candidate_values(
    *,
    asset_id,
    symbol: Optional[str],
    timeframe: str,
    decision: Dict[str, Any],
    df,
    evaluated_at: datetime,
    verdict: str,
    demotion_reason: Optional[str],
    primary_demotion_reason: Optional[str] = None,
    final_signal_type: Optional[str] = None,
    final_direction: Optional[str] = None,
    regime_label: Optional[str] = None,
    regime_result: Any = None,
    engine_weights: Any = None,
    adaptive_active: Optional[bool] = None,
    adaptive_snapshot: Optional[Dict[str, Any]] = None,
    last_close: Optional[float] = None,
    signal_id=None,
    source: str = SOURCE_SCHEDULER,
    capture_status: str = CAPTURE_FULL,
) -> Optional[Dict[str, Any]]:
    """Assemble the column values for one candidate row.

    Pure: no DB, no I/O. Returns None when the row could not be keyed (an empty
    frame has no scored bar), so the caller never writes a NULL-key row.
    """
    bar_time = _bar_time(df)
    if bar_time is None:
        return None

    birth = decision.get("birth_telemetry") or {}
    consensus = decision.get("consensus_telemetry") or {}
    decision_input = decision.get("decision_input_telemetry") or {}
    engine_results = decision.get("engine_results")

    entry_low = _f(decision.get("entry_zone_low"))
    entry_high = _f(decision.get("entry_zone_high"))
    stop = _f(decision.get("stop_loss"))
    tp1 = _f(decision.get("tp1"))
    entry_mid = ((entry_low + entry_high) / 2.0) if (entry_low is not None and entry_high is not None) else None

    # Regime-side context. getattr rather than dict access: regime_result is a
    # dataclass-ish object, and a missing attribute must degrade to None instead
    # of raising inside a telemetry path.
    def _reg(name: str) -> Optional[float]:
        return _f(getattr(regime_result, name, None)) if regime_result is not None else None

    atr_pct_regime = _reg("atr_pct")
    atr_pct_median = _reg("atr_pct_median")
    volatility_ratio = (atr_pct_regime / atr_pct_median) if (atr_pct_regime and atr_pct_median) else None

    composite = _f(birth.get("composite_score"))

    values: Dict[str, Any] = {
        "asset_id": asset_id,
        "signal_id": signal_id,
        "symbol": symbol,
        "timeframe": timeframe,
        "evaluated_bar_time": bar_time,
        "evaluated_at": evaluated_at,
        "source": source,
        "policy_version": CANDIDATE_POLICY_VERSION,
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "capture_status": capture_status,

        "verdict": verdict,
        "demotion_reason": demotion_reason,
        "engine_signal_type": decision.get("signal_type"),
        "engine_direction": decision.get("direction"),
        "final_signal_type": final_signal_type,
        "final_direction": final_direction,

        "composite_score": composite,
        # A NULL composite from a failed telemetry build must be distinguishable
        # from a genuine absence — the reader cannot tell them apart otherwise.
        "composite_score_source": "birth_telemetry" if composite is not None else "unavailable",
        "confidence_score": _f(decision.get("confidence_score")),
        "probability_score": _f(decision.get("probability_score")),
        "risk_score": _f(decision.get("risk_score")),
        "risk_level": decision.get("risk_level"),

        "conflict_min_count": consensus.get("conflict_min_count"),
        "bull_count": consensus.get("bull_count"),
        "bear_count": consensus.get("bear_count"),
        "disagreement_penalty": _f(consensus.get("disagreement_penalty")),
        "mtf_penalty": _f(consensus.get("mtf_penalty")),

        "regime": regime_label,
        "adx": _reg("adx"),
        "atr_pct_regime": atr_pct_regime,
        "atr_pct_median": atr_pct_median,
        "volume_ratio_regime": _reg("volume_ratio"),
        "volatility_ratio": round(volatility_ratio, 4) if volatility_ratio is not None else None,
        "trend_direction": getattr(regime_result, "trend_direction", None),

        "atr_pct_geometry": _f(birth.get("atr_pct")),
        "volume_ratio_geometry": _volume_ratio_geometry(engine_results),

        "last_close": _f(last_close),
        "entry_zone_low": entry_low,
        "entry_zone_high": entry_high,
        "stop_loss": stop,
        "tp1": tp1,
        "tp2": _f(decision.get("tp2")),
        "tp3": _f(decision.get("tp3")),
        "planned_rr_tp1": planned_rr(entry_mid, stop, tp1),
        "sl_dist_pct": dist_pct(entry_mid, stop),

        # Not computed at decision time by design — the similarity engine needs
        # the candidate's own persisted snapshot, which a rejected candidate by
        # definition does not have. Left ready for offline enrichment rather than
        # bolting a per-candidate query onto a ~90-asset x 4-timeframe loop.
        "similarity_score": None,
        "similarity_status": SIMILARITY_UNAVAILABLE,

        "engine_scores": _json_safe(_engine_scores(engine_results)),
        "engine_weights": _json_safe(engine_weights),
        "mtf_trends": _json_safe(decision.get("mtf_trends")),
        "adaptive_active": adaptive_active,

        "extra": _json_safe({
            # `demotion_reason` above is the TERMINAL reason and later scheduler
            # sites overwrite it on purpose. This is the FIRST one that fired, so
            # a candidate rejected by the confidence gate that then also met an
            # active signal is not silently reclassified as duplicate_or_existing
            # — the confidence-gate rejection stays countable. Lives in `extra`
            # rather than a column so no migration is needed and no existing row
            # or query changes meaning.
            "primary_demotion_reason": primary_demotion_reason,
            # F1 — the decision-input contract. `decision_input_version` is the
            # cohort boundary: rows written before it exist were scored on a
            # candle that was still forming, and mixing the two populations in
            # one analysis compares different systems. The price pair is what
            # makes "closed bars pointed the right way but price had already
            # run" a countable case rather than an anecdote.
            **{k: decision_input.get(k) for k in (
                "decision_input_version",
                "candle_policy",
                "current_price",
                "decision_current_price_source",
                "analysis_close_price",
                "last_analysis_bar_open_time",
                "last_analysis_bar_close_time",
                "last_analysis_bar_closed",
                "current_vs_analysis_close_pct",
                "current_vs_analysis_close_atr",
            )},
            "threshold_signal_type": consensus.get("threshold_signal_type"),
            "threshold_direction": consensus.get("threshold_direction"),
            "engine_demoted": consensus.get("engine_demoted"),
            "entry_frame_caveat": (
                # build_entry_telemetry's docstring claims it mirrors the tracker's
                # df_after filter exactly; it does not — the tracker additionally
                # re-appends the still-forming birth candle (tracker.py:308-311).
                # Inherited, not fixed: correcting it would change the meaning of
                # existing extra["entry"] rows and needs a version bump.
                "reading_a_midpoint; birth-candle not re-appended"
            ),
            # F1-D — the base → regime → coin-memory chain as this decision
            # resolved it. Handed in already built; nothing is recomputed here,
            # because a second resolution could read a coin_memory row a later
            # fold had already overwritten and would then record weights the
            # decision never used. None on the older path or if the snapshot
            # could not be built — absent, never guessed.
            "adaptive_state_telemetry": _adaptive_state_entry(
                adaptive_snapshot, decision, evaluated_at),
        }),
    }

    # Birth-time shadow classification. Whether this row can EVER be
    # shadow-evaluated is fully determined by the direction and geometry just
    # written above — no bar, no waiting and no later query can change it. So a
    # permanently unevaluable candidate is stamped here rather than inserted
    # pending and retired by a separate UPDATE ~6 500 times a day.
    #
    # This is telemetry state only. It does not read or affect verdict,
    # demotion_reason, confidence, composite, direction, geometry or anything the
    # signal decision depends on — those are already final by the time this
    # function is called, and nothing here writes back to them.
    #
    # Only the three classification fields are set. Measurement columns (MFE,
    # MAE, R, return, entry-validity) stay NULL: this row is RETIRED, never
    # RESOLVED, and the report's scored/resolved filters exclude `undecidable`
    # precisely so a retired row cannot be counted as an observation.
    birth_reason = classify_birth_shadow(
        direction=values["engine_direction"],
        entry_zone_low=entry_low,
        entry_zone_high=entry_high,
        stop_loss=stop,
    )
    values["shadow_outcome"] = SHADOW_UNDECIDABLE if birth_reason else None
    values["shadow_resolution_reason"] = birth_reason
    # The decision's own timestamp, not wall clock: it is already tz-aware and it
    # keeps the row internally consistent with evaluated_at.
    values["shadow_evaluated_at"] = evaluated_at if birth_reason else None

    return values


async def record_candidate(db, **kwargs) -> bool:
    """Persist one candidate row. Returns True when this call wrote it.

    Fail-open and savepoint-isolated — see the module docstring. The boolean is
    returned for tests; production call sites discard it.
    """
    try:
        values = build_candidate_values(**kwargs)
        if values is None:
            logger.debug("[CandidateLog] no scored bar — nothing to key on, skipped")
            return False

        # Omit None so column defaults apply (id, created_at, and the
        # server_default'ed version columns) — the same reason as
        # tracker._persist_trade_path_once.
        payload = {k: v for k, v in values.items() if v is not None}

        stmt = (
            pg_insert(SignalDecisionCandidate.__table__)
            .values(**payload)
            .on_conflict_do_nothing(
                index_elements=["asset_id", "timeframe", "evaluated_bar_time",
                                "policy_version", "source"]
            )
            .returning(SignalDecisionCandidate.__table__.c.id)
        )

        # SAVEPOINT: a constraint or statement error aborts only this, leaving
        # the caller's transaction — which may hold a staged reversal close —
        # usable.
        async with db.begin_nested():
            written = (await db.execute(stmt)).scalar_one_or_none()

        # Summary only. Never the row, never connection params.
        logger.debug("[CandidateLog] %s verdict=%s reason=%s written=%s",
                     values.get("symbol"), values.get("verdict"),
                     values.get("demotion_reason"), written is not None)
        return written is not None
    except Exception as exc:  # noqa: BLE001 — telemetry must never break generation
        logger.warning("[CandidateLog] candidate not recorded (fail-open, ignored): %s", exc)
        return False
