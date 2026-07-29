"""
Coin Memory + Adaptive Weight Engine.

Two jobs:

  1. RESOLVE the engine weights to use for a given (symbol, timeframe) right
     now, by tilting the static base mix two ways:
       • by market regime (deterministic, always-on rules — e.g. trend markets
         lean on Technical/Structure, ranges lean on SMC/CRT/S-R, panic leans
         on Risk/Volume);
       • by what this specific coin has actually learned (engines that have
         historically called THIS asset correctly get more say).

  2. UPDATE that learned memory when a signal resolves: per-engine hit rate,
     per-regime win rate, outcome-label distribution, and a fresh set of
     adaptive weights.

Overfitting guards are central, not afterthoughts:
  • learned weights only kick in past a minimum sample size;
  • each engine's learned weight is clamped to a band around its base, so no
    single engine can run away or vanish on a lucky/unlucky streak;
  • everything is renormalised so weights always sum to 1.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backtesting import labels
from app.backtesting.trade_path import is_legacy_contradictory_live_sl
from app.services.trade_geometry import planned_rr, safe_div
from app.engines.ai_decision.signal_generator import BASE_ENGINE_WEIGHTS
from app.engines.base import SignalBias
from app.models.asset import Asset
from app.models.decision_candidate import SignalDecisionCandidate
from app.models.intelligence import CoinMemory, SignalSnapshot, SignalTradePath
from app.models.signal import Signal, SignalOutcome, SignalPerformance

logger = logging.getLogger(__name__)

# ── Learning guards ──────────────────────────────────────────────────────────
# Don't let learned weights influence anything until the coin has resolved at
# least this many signals — below it, the sample is noise.
MIN_SAMPLES_FOR_ADAPTIVE = 20
# Per-engine minimum before that engine's win-rate is trusted to move its weight.
MIN_ENGINE_SAMPLES = 12
# A learned engine weight may not stray beyond this band around its base, so a
# hot/cold streak can tilt the mix but never dominate or silence an engine.
ADAPTIVE_BAND_LOW = 0.55   # min 55% of base
ADAPTIVE_BAND_HIGH = 1.75  # max 175% of base


# ── Regime tilt rules ────────────────────────────────────────────────────────
# Multipliers applied to base weights per regime. Anything omitted = 1.0.
# Deliberately mild (0.6–1.4) — the regime should nudge emphasis, not rewrite
# the strategy. Renormalised after applying, so absolute values don't matter,
# only ratios.
_REGIME_TILTS: Dict[str, Dict[str, float]] = {
    "trending_bull": {
        "technical_analysis": 1.30, "market_structure": 1.30,
        "smart_money_concepts": 0.85, "candle_range_theory": 0.75,
        "macro_analysis": 1.10,
    },
    "trending_bear": {
        "technical_analysis": 1.30, "market_structure": 1.30,
        "smart_money_concepts": 0.85, "candle_range_theory": 0.75,
        "macro_analysis": 1.10,
    },
    "ranging": {
        "smart_money_concepts": 1.35, "candle_range_theory": 1.35,
        "market_structure": 1.10, "technical_analysis": 0.75,
        "macro_analysis": 0.80,
    },
    "volatile_high": {
        "risk_management": 1.60, "volume_analysis": 1.30,
        "technical_analysis": 0.80, "candle_range_theory": 0.80,
        "fundamental_analysis": 0.70,
    },
    "low_volume": {
        "volume_analysis": 1.40, "risk_management": 1.25,
        "technical_analysis": 0.85, "smart_money_concepts": 0.90,
    },
    "breakout": {
        "volume_analysis": 1.45, "market_structure": 1.25,
        "candle_range_theory": 1.15, "fundamental_analysis": 0.75,
    },
}


def _normalize(weights: Dict[str, float]) -> Dict[str, float]:
    """Scale weights so they sum to 1.0 (no-op safe on empty/zero)."""
    total = sum(weights.values())
    if total <= 0:
        return dict(BASE_ENGINE_WEIGHTS)
    return {k: v / total for k, v in weights.items()}


def regime_weights(regime: Optional[str]) -> Dict[str, float]:
    """Base weights tilted for a market regime, renormalised to sum 1.0."""
    base = dict(BASE_ENGINE_WEIGHTS)
    tilt = _REGIME_TILTS.get(regime or "", {})
    if not tilt:
        return base
    tilted = {k: base[k] * tilt.get(k, 1.0) for k in base}
    return _normalize(tilted)


def _decision_adaptive_weights(memory: Optional[CoinMemory]) -> Optional[Dict[str, float]]:
    """The learned multipliers the DECISION should use, derived from the feature at
    read time rather than read from the stored cache (F0-L2).

    memory.adaptive_weights is a cache the fold writes; it stays for telemetry and
    the API. But the decision now recomputes from engine_stats — the source of
    truth — so the weights are always as fresh as the feature, even if a fold was
    skipped or ran late (the F0-1 downtime case). Byte-identical to reading the
    cache while the two agree, which the L1 invariant locks and 1225/1225 live
    (cell × regime) combinations confirmed. Returns None below the sample gate or
    when no engine has crossed MIN_ENGINE_SAMPLES.
    """
    if memory is None or memory.total_signals < MIN_SAMPLES_FOR_ADAPTIVE:
        return None
    return _recompute_adaptive_weights(getattr(memory, "engine_stats", None) or {})


# ── F1-D: decision-time weight-chain snapshot ────────────────────────────────
# The layers below already existed as locals inside get_effective_weights; only
# the final dict came out, so a candidate recorded WHICH mix was used but never
# HOW it was reached. That is why backtest adaptive parity is not_applied: the
# coin_memory row is overwritten on every fold (no version, valid_from or as_of
# column), so the state that produced a past decision cannot be recovered
# afterwards. Capturing it at decision time is the only non-look-ahead way to
# get it, and this is forward-only — nothing is backfilled.

ADAPTIVE_TELEMETRY_VERSION = "adaptive_state_v1"
ADAPTIVE_CAPTURE_POLICY = "decision_time_snapshot"
ADAPTIVE_HISTORY_POLICY = "forward_only"

# Why the coin-learned layer did not apply. None means it did.
FALLBACK_NO_MEMORY = "no_memory_row"
FALLBACK_BELOW_MIN_SAMPLES = "below_min_samples"
FALLBACK_NO_ENGINE_READY = "no_engine_above_min_samples"


@dataclass(frozen=True)
class WeightChain:
    """Every layer of one weight resolution, as the decision actually saw it.

    Frozen, and every dict is built fresh here, so a snapshot taken from it
    cannot be altered by anything that later mutates the caller's weights.
    """

    base: Dict[str, float]
    regime_adjusted: Dict[str, float]
    regime_multipliers: Dict[str, float]
    memory_multipliers: Optional[Dict[str, float]]
    effective: Dict[str, float]
    memory_applied: bool
    fallback_reason: Optional[str]


def _memory_fallback_reason(memory: Optional[CoinMemory],
                            learned: Optional[Dict[str, float]]) -> Optional[str]:
    """Label the branch _decision_adaptive_weights took. Reads only, decides nothing."""
    if learned is not None:
        return None
    if memory is None:
        return FALLBACK_NO_MEMORY
    if memory.total_signals < MIN_SAMPLES_FOR_ADAPTIVE:
        return FALLBACK_BELOW_MIN_SAMPLES
    return FALLBACK_NO_ENGINE_READY


def resolve_weight_chain(
    regime: Optional[str],
    memory: Optional[CoinMemory],
) -> WeightChain:
    """Resolve the weights AND keep every intermediate layer.

    This is the arithmetic get_effective_weights used to hold inline, unchanged:
    base → regime tilt → coin-learned tilt → normalise. get_effective_weights is
    now a thin wrapper over `.effective`, so the telemetry records the very chain
    the decision used rather than a parallel re-derivation of it.
    """
    base = dict(BASE_ENGINE_WEIGHTS)
    weights = regime_weights(regime)

    learned = _decision_adaptive_weights(memory)
    if learned:
        # multipliers-vs-base per engine; combine multiplicatively with the
        # regime-tilted weights.
        combined = {
            k: weights[k] * float(learned.get(k, 1.0))
            for k in weights
        }
        effective = _normalize(combined)
    else:
        effective = weights

    raw_tilt = _REGIME_TILTS.get(regime or "", {})
    return WeightChain(
        base=base,
        regime_adjusted=dict(weights),
        # Spelled out for every engine, so a reader never has to know that an
        # omitted engine means 1.0. These are the RAW tilts; regime_adjusted is
        # what they became after renormalisation.
        regime_multipliers={k: float(raw_tilt.get(k, 1.0)) for k in base},
        memory_multipliers=dict(learned) if learned else None,
        effective=dict(effective),
        memory_applied=learned is not None,
        fallback_reason=_memory_fallback_reason(memory, learned),
    )


def get_effective_weights(
    regime: Optional[str],
    memory: Optional[CoinMemory],
) -> Dict[str, float]:
    """Final engine weights = base → regime tilt → coin-learned tilt → normalise.

    The learned layer is applied only when `memory` has enough resolved samples and
    a computable adaptive model; otherwise just the regime-tilted base is used. F0-L2:
    the model is recomputed from the feature here, not read from the stored cache.
    """
    return resolve_weight_chain(regime, memory).effective


def _finite_weights(d: Optional[Dict[str, float]]) -> Optional[Dict[str, float]]:
    """Reject NaN/Infinity rather than writing a value JSON cannot round-trip.

    Raises so the caller records the failure explicitly; silently substituting a
    number would put a fabricated weight in the historical record, which is the
    one thing this telemetry exists to prevent.
    """
    if d is None:
        return None
    out: Dict[str, float] = {}
    for k, v in d.items():
        f = float(v)
        if not math.isfinite(f):
            raise ValueError(f"non-finite weight for {k!r}: {v!r}")
        out[k] = f
    return out


def _memory_state_fingerprint(memory: Optional[CoinMemory]) -> Optional[str]:
    """Identify the memory state that produced these multipliers.

    coin_memory has no version column and every fold overwrites the row, so
    there is no id to point at. This hashes the ONLY inputs that decide the
    multipliers — each engine's total and correct counts — which is enough for a
    later replay to prove it is looking at the same state, and small enough that
    no unrelated column drift changes it.
    """
    if memory is None:
        return None
    stats = getattr(memory, "engine_stats", None) or {}
    canonical = {
        engine: {
            "total": int((stats.get(engine) or {}).get("total", 0)),
            "correct": int((stats.get(engine) or {}).get("correct", 0)),
        }
        for engine in BASE_ENGINE_WEIGHTS
    }
    canonical["_total_signals"] = int(memory.total_signals or 0)
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


def weight_chain_snapshot(
    chain: WeightChain,
    *,
    symbol: str,
    timeframe: str,
    regime: Optional[str],
    memory: Optional[CoinMemory],
) -> Dict[str, Any]:
    """A serializable, immutable record of the chain, for the candidate row.

    Deliberately NOT the whole memory row: only the fields that actually decided
    the multipliers, plus enough identity to find the same state again. Carries
    no credential, no free-form blob and nothing unbounded.

    Direction and the decision timestamp are added by the candidate logger,
    which is where they are known; inventing them here would mean two sources of
    truth for the same fact.
    """
    engine_order = list(BASE_ENGINE_WEIGHTS)
    effective = _finite_weights(chain.effective) or {}
    missing = [e for e in engine_order if e not in effective]
    if missing:
        raise ValueError(f"effective weights missing engines: {missing}")

    last_updated = getattr(memory, "last_updated_at", None)
    if last_updated is not None and last_updated.tzinfo is None:
        # Stored naive by an older writer; the column is UTC by convention.
        last_updated = last_updated.replace(tzinfo=timezone.utc)

    return {
        "telemetry_version": ADAPTIVE_TELEMETRY_VERSION,
        "capture_policy": ADAPTIVE_CAPTURE_POLICY,
        "history_policy": ADAPTIVE_HISTORY_POLICY,
        "historical_backfill": False,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "timeframe": timeframe,
        "regime": regime,
        "engine_order": engine_order,
        "base_weights": _finite_weights(chain.base),
        "regime_multipliers": _finite_weights(chain.regime_multipliers),
        "regime_adjusted_weights": _finite_weights(chain.regime_adjusted),
        "coin_memory_multipliers": _finite_weights(chain.memory_multipliers),
        # The learned layer is last in the chain, so this equals
        # effective_weights today. Kept distinct so a future layer inserted
        # after it does not silently redefine either name.
        "coin_memory_adjusted_weights": dict(effective),
        "effective_weights": dict(effective),
        "effective_weight_sum": round(sum(effective.values()), 10),
        "adaptive_active": chain.memory_applied,
        "memory_available": memory is not None,
        "memory_applied": chain.memory_applied,
        "memory_key": f"{symbol}|{timeframe}",
        "memory_sample_count": int(memory.total_signals) if memory is not None else None,
        "memory_last_updated_at": last_updated.isoformat() if last_updated else None,
        "memory_state_fingerprint": _memory_state_fingerprint(memory),
        "fallback_reason": chain.fallback_reason,
        "min_samples_for_adaptive": MIN_SAMPLES_FOR_ADAPTIVE,
        "min_engine_samples": MIN_ENGINE_SAMPLES,
        "adaptive_band": [ADAPTIVE_BAND_LOW, ADAPTIVE_BAND_HIGH],
        "normalization_applied": True,
        "source": "load_effective_weights_meta",
    }


def _bias_direction(bias: Any) -> Optional[str]:
    """Collapse an engine SignalBias (string or enum) to bullish/bearish/None."""
    val = bias.value if isinstance(bias, SignalBias) else str(bias)
    if val in ("bullish", "strong_bullish"):
        return "bullish"
    if val in ("bearish", "strong_bearish"):
        return "bearish"
    return None


def _recompute_adaptive_weights(engine_stats: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """Turn per-engine hit rates into a clamped multiplier-vs-base per engine.

    Returns None until at least one engine has crossed MIN_ENGINE_SAMPLES (so we
    never publish weights built on nothing). Engines without enough samples stay
    at multiplier 1.0 (neutral).
    """
    any_ready = False
    multipliers: Dict[str, float] = {}
    for engine in BASE_ENGINE_WEIGHTS:
        st = engine_stats.get(engine, {})
        total = int(st.get("total", 0))
        correct = int(st.get("correct", 0))
        if total >= MIN_ENGINE_SAMPLES:
            any_ready = True
            win_rate = correct / total if total else 0.5
            # 0.0 win → 0.7x, 0.5 → 1.0x, 1.0 → 1.3x
            mult = 0.7 + 0.6 * win_rate
            mult = max(ADAPTIVE_BAND_LOW, min(ADAPTIVE_BAND_HIGH, mult))
        else:
            mult = 1.0
        multipliers[engine] = round(mult, 4)

    return multipliers if any_ready else None


# Outcomes that carry a lesson. Anything else (ACTIVE) teaches nothing.
FOLDABLE_OUTCOMES = (SignalOutcome.WIN, SignalOutcome.LOSS, SignalOutcome.BREAKEVEN,
                     SignalOutcome.EXPIRED, SignalOutcome.INVALIDATED)


def fold_signal_into(mem: CoinMemory, signal: Signal, perf: SignalPerformance,
                     snap: Optional[SignalSnapshot]) -> bool:
    """Fold ONE resolved signal into a cell. PURE: mutates `mem`, no DB, no clock.

    F0-K: the single derivation of the v1 base facets. Both callers go through it —
    `update_coin_memory` online, `rebuild_coin_memory` from the SoT — so the two can
    never drift apart. Modelled on tm_stats, where `rebuild_tm_stats` already shares
    its logic with the online rollup; the base facets had no such rebuild, which is
    why a fold lost to the caller's fail-open envelope was lost for good.

    Returns True when the signal was folded, False when its outcome carries no
    lesson. Does NOT touch tm_stats/tm_sample_count — those are the trade-path
    rollup's facet and have their own derivation.
    """
    outcome = perf.outcome
    if outcome not in FOLDABLE_OUTCOMES:
        return False

    is_win = outcome == SignalOutcome.WIN
    is_loss = outcome in (SignalOutcome.LOSS, SignalOutcome.INVALIDATED)

    # --- counters (work on copies so SQLAlchemy detects JSON mutation) ---
    mem.total_signals = (mem.total_signals or 0) + 1
    if is_win:
        mem.wins = (mem.wins or 0) + 1
    elif is_loss:
        mem.losses = (mem.losses or 0) + 1

    # --- outcome-label distribution ---
    label_stats = dict(mem.outcome_label_stats or {})
    label = perf.detail_label or outcome.value
    label_stats[label] = label_stats.get(label, 0) + 1
    mem.outcome_label_stats = label_stats

    # --- per-engine directional correctness ---
    # Outcome direction: a WIN means the signal's own direction was right; a LOSS
    # means the opposite direction would have been right. Skip ambiguous closes.
    sig_dir = signal.direction.value if hasattr(signal.direction, "value") else str(signal.direction)
    outcome_direction: Optional[str] = None
    if is_win and sig_dir in ("bullish", "bearish"):
        outcome_direction = sig_dir
    elif is_loss and sig_dir in ("bullish", "bearish"):
        outcome_direction = "bearish" if sig_dir == "bullish" else "bullish"

    if outcome_direction and snap and snap.engine_scores:
        engine_stats = {k: dict(v) for k, v in (mem.engine_stats or {}).items()}
        for engine, sc in snap.engine_scores.items():
            edir = _bias_direction(sc.get("bias"))
            if edir is None:
                continue  # neutral engine made no directional call — no lesson
            st = engine_stats.get(engine, {"correct": 0, "total": 0})
            st["total"] = int(st.get("total", 0)) + 1
            if edir == outcome_direction:
                st["correct"] = int(st.get("correct", 0)) + 1
            st["win_rate"] = round(st["correct"] / st["total"], 4) if st["total"] else 0.0
            engine_stats[engine] = st
        mem.engine_stats = engine_stats
        # Recompute adaptive weights from the updated stats.
        new_weights = _recompute_adaptive_weights(engine_stats)
        if new_weights is not None:
            mem.adaptive_weights = new_weights

    # --- per-regime win rate ---
    regime = snap.regime if snap else None
    if regime:
        regime_stats = {k: dict(v) for k, v in (mem.regime_stats or {}).items()}
        rst = regime_stats.get(regime, {"wins": 0, "total": 0})
        rst["total"] = int(rst.get("total", 0)) + 1
        if is_win:
            rst["wins"] = int(rst.get("wins", 0)) + 1
        rst["win_rate"] = round(rst["wins"] / rst["total"], 4) if rst["total"] else 0.0
        regime_stats[regime] = rst
        mem.regime_stats = regime_stats

    # --- rolling average bars-to-outcome ---
    if perf.bars_to_outcome:
        prev_avg = float(mem.avg_bars_to_outcome or 0)
        n = mem.total_signals
        mem.avg_bars_to_outcome = round((prev_avg * (n - 1) + perf.bars_to_outcome) / n, 2)

    return True


async def update_coin_memory(
    db: AsyncSession,
    signal: Signal,
    perf: SignalPerformance,
    symbol: str,
) -> None:
    """Fold a just-resolved signal into its (symbol, timeframe) memory cell.

    Safe to call inside the resolving transaction; wrapped by the caller so a
    memory-update failure never blocks the resolution itself. F0-K: the arithmetic
    moved verbatim into fold_signal_into, which rebuild_coin_memory shares — this is
    now only the I/O around it (find-or-create the cell, read the snapshot).
    """
    timeframe = signal.timeframe.value if hasattr(signal.timeframe, "value") else str(signal.timeframe)

    # Only learn from genuinely resolved outcomes. Checked BEFORE the cell is
    # touched, so an unresolved signal still creates nothing (unchanged).
    if perf.outcome not in FOLDABLE_OUTCOMES:
        return

    # Fetch (or create) the memory cell.
    res = await db.execute(
        select(CoinMemory).where(CoinMemory.symbol == symbol, CoinMemory.timeframe == timeframe)
    )
    mem = res.scalar_one_or_none()
    if mem is None:
        mem = CoinMemory(
            symbol=symbol, timeframe=timeframe,
            total_signals=0, wins=0, losses=0,
            engine_stats={}, regime_stats={}, outcome_label_stats={},
        )
        db.add(mem)

    # Pull the birth-snapshot for engine biases + regime context.
    snap_res = await db.execute(
        select(SignalSnapshot).where(SignalSnapshot.signal_id == signal.id)
    )
    snap = snap_res.scalar_one_or_none()

    fold_signal_into(mem, signal, perf, snap)

    logger.info(
        "[CoinMemory] %s %s updated: total=%d wins=%d losses=%d label=%s",
        symbol, timeframe, mem.total_signals, mem.wins, mem.losses,
        perf.detail_label or perf.outcome.value,
    )


async def rebuild_coin_memory(db: AsyncSession) -> Dict[str, int]:
    """Drop & rebuild every coin_memory BASE facet from signal_performances (the SoT).

    F0-K. update_coin_memory is an incremental online fold wrapped in the caller's
    fail-open envelope: a fold that raises is logged and skipped, the resolution
    commits anyway, and the count is short by one forever. tm_stats has had
    rebuild_tm_stats to repair exactly that; the base facets had nothing, so drift
    could only accumulate. This is that missing half.

    Re-folds through fold_signal_into — the SAME function the online path uses — so
    "rebuild == online" is true by construction rather than by two implementations
    agreeing. Ordered by closed_at because avg_bars_to_outcome is a running mean.
    Note the honest limit: this reproduces the arithmetic exactly, but the true
    historical resolution ORDER is not recoverable, so a cell whose folds landed in
    a different order can differ in that one rolling average.

    Touches ONLY the v1 base facets. tm_stats / tm_sample_count belong to the
    trade-path rollup and are left exactly as they are.

    Read-and-write; MANUAL/admin use — nothing calls this automatically. Caller commits.
    """
    rows = (await db.execute(
        select(SignalPerformance, Signal, Asset.symbol, SignalSnapshot)
        .join(Signal, Signal.id == SignalPerformance.signal_id)
        .join(Asset, Asset.id == Signal.asset_id)
        .outerjoin(SignalSnapshot, SignalSnapshot.signal_id == Signal.id)
        .where(SignalPerformance.outcome.in_(FOLDABLE_OUTCOMES))
        .order_by(SignalPerformance.closed_at.asc().nulls_last())
    )).all()

    mems = (await db.execute(select(CoinMemory))).scalars().all()
    cells = {(m.symbol, m.timeframe): m for m in mems}

    # RESET the base facets on every existing cell — a rebuild that only added
    # would inherit whatever the online path had already miscounted.
    for mem in cells.values():
        _reset_base_facets(mem)

    folded = skipped = created = 0
    for perf, signal, symbol, snap in rows:
        timeframe = signal.timeframe.value if hasattr(signal.timeframe, "value") else str(signal.timeframe)
        key = (symbol, timeframe)
        mem = cells.get(key)
        if mem is None:
            mem = CoinMemory(symbol=symbol, timeframe=timeframe,
                             total_signals=0, wins=0, losses=0,
                             engine_stats={}, regime_stats={}, outcome_label_stats={})
            db.add(mem)
            cells[key] = mem
            created += 1
        if fold_signal_into(mem, signal, perf, snap):
            folded += 1
        else:
            skipped += 1

    logger.info("[CoinMemory] rebuild: %d resolutions -> %d cells (%d new, %d skipped)",
                len(rows), len(cells), created, skipped)
    return {"resolutions": len(rows), "folded": folded, "skipped": skipped,
            "cells": len(cells), "cells_created": created}


def _reset_base_facets(mem: CoinMemory) -> None:
    """Zero the v1 base facets so a rebuild starts from nothing. tm_stats and
    tm_sample_count are deliberately untouched — a different derivation owns them."""
    mem.total_signals = 0
    mem.wins = 0
    mem.losses = 0
    mem.engine_stats = {}
    mem.regime_stats = {}
    mem.outcome_label_stats = {}
    mem.adaptive_weights = None
    mem.avg_bars_to_outcome = None


async def load_effective_weights(
    db: AsyncSession,
    symbol: str,
    timeframe: str,
    regime: Optional[str],
) -> Dict[str, float]:
    """Convenience: fetch the memory cell and resolve effective weights for it."""
    res = await db.execute(
        select(CoinMemory).where(CoinMemory.symbol == symbol, CoinMemory.timeframe == timeframe)
    )
    mem = res.scalar_one_or_none()
    return get_effective_weights(regime, mem)


def adaptive_is_active(memory: Optional[CoinMemory]) -> bool:
    """True when the coin-learned (adaptive) weight layer is applied for this cell —
    the EXACT gate get_effective_weights uses. Pure, read-only; A8-1 telemetry only
    (never influences weights/decision). F0-L2: keyed off the SAME recompute the
    decision uses, so the telemetry flag can never disagree with what actually
    happened (reading the cache here could, if the cache were stale)."""
    return _decision_adaptive_weights(memory) is not None


async def load_effective_weights_meta(
    db: AsyncSession,
    symbol: str,
    timeframe: str,
    regime: Optional[str],
) -> Tuple[Dict[str, float], bool, Optional[Dict[str, Any]]]:
    """Like load_effective_weights but ALSO reports whether the adaptive layer was
    applied, for A8-1 birth telemetry, and (F1-D) a snapshot of the whole chain.

    The weights come from the SAME resolution get_effective_weights performs →
    BYTE-IDENTICAL to load_effective_weights; the flag and the snapshot are
    additive and read-only.

    The snapshot is built in its own try/except on purpose. It is pure and has no
    business failing, but if it ever did, the decision must not notice: an
    exception escaping here would leave the caller's engine_weights at None and
    the signal would be scored on the static base mix instead of the adaptive
    one. Telemetry that can change a decision is not telemetry.
    """
    res = await db.execute(
        select(CoinMemory).where(CoinMemory.symbol == symbol, CoinMemory.timeframe == timeframe)
    )
    mem = res.scalar_one_or_none()
    chain = resolve_weight_chain(regime, mem)

    snapshot: Optional[Dict[str, Any]] = None
    try:
        snapshot = weight_chain_snapshot(
            chain, symbol=symbol, timeframe=timeframe, regime=regime, memory=mem)
    except Exception as exc:  # noqa: BLE001 — never let telemetry reach the decision
        logger.warning("[CoinMemory] adaptive snapshot failed for %s %s: %s",
                       symbol, timeframe, exc)

    return chain.effective, chain.memory_applied, snapshot


# ════════════════════════════════════════════════════════════════════════════
# Coin Memory v2 — trade-management rollup (Trade Management Faz 1, OBSERVATION)
# ════════════════════════════════════════════════════════════════════════════
# Folds each resolved trade's path metrics into coin_memory.tm_stats. This is a
# DERIVABLE CACHE over signal_trade_path (the source of truth) — purely additive
# observation. It does NOT touch the existing engine/regime weight-learning
# logic (update_coin_memory) or any decision/policy. Histograms are additive
# lists so hierarchy parents can later be summed from children.

# Bin upper-edges for R-multiple metrics (MFE_R / MAE_R). Bucket i counts values
# in [edge[i-1], edge[i]); the final bucket is the overflow (>= last edge).
TM_R_EDGES = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0]
_TM_NBINS = len(TM_R_EDGES) + 1  # +1 overflow bucket


def _bin_index(v: float) -> int:
    for i, e in enumerate(TM_R_EDGES):
        if v < e:
            return i
    return len(TM_R_EDGES)  # overflow


def _f(x) -> Optional[float]:
    """Numeric/Decimal column → float (None preserved)."""
    return float(x) if x is not None else None


def _fold_key(path) -> Optional[Tuple[str, str]]:
    """(symbol, timeframe) for a foldable path, or None if it must be SKIPPED:
    missing identity, or a legacy-contradictory live-SL row (CM2-1 fold-hardening —
    KEY1-d predicate). Single source for the skip rule, shared by the online fold
    and the rebuild so they can never diverge."""
    symbol = (path.symbol or "").upper()
    timeframe = path.timeframe
    if not symbol or not timeframe:
        return None
    if is_legacy_contradictory_live_sl(path):
        return None
    return (symbol, timeframe)


def _empty_bucket() -> Dict[str, Any]:
    return {
        "n": 0,
        "mfe_r_sum": 0.0, "mae_r_sum": 0.0,
        "hist_mfe_r": [0] * _TM_NBINS,
        "hist_mae_r": [0] * _TM_NBINS,
        # policy-dependent diagnostics (secondary; derived from cur_* fields)
        "tp1": 0, "tp2": 0, "tp3": 0, "give_back": 0,
        # CM2-2 additive aggregates. Per-field N so avg = sum / N stays exact even
        # when a field is NULL on some rows; SUMSQ enables variance/std on read.
        # All keys default-safe (.get) so pre-CM2-2 buckets gain them on next fold.
        "mfe_r_n": 0, "mae_r_n": 0,
        "mfe_r_sumsq": 0.0, "mae_r_sumsq": 0.0,
        "mfe_atr_sum": 0.0, "mfe_atr_n": 0,
        "mae_atr_sum": 0.0, "mae_atr_n": 0,
        "bars_total_sum": 0, "bars_total_n": 0,
        "bars_to_tp1_sum": 0, "bars_to_tp1_n": 0,        # policy-dependent (cur_*)
        "realized_sum": 0.0, "realized_sumsq": 0.0, "realized_n": 0,  # policy-dependent (cur_*)
        "planned_rr_tp1_sum": 0.0, "planned_rr_tp1_n": 0, "sub1_rr": 0,  # entry-quality
        "tight_sl": 0,                                    # stop-too-tight (canonical label)
    }


def _fold_into_bucket(b: Dict[str, Any], path) -> None:
    b["n"] = int(b.get("n", 0)) + 1
    if path.mfe_r is not None:
        mr = float(path.mfe_r)
        b["mfe_r_sum"] = round(float(b.get("mfe_r_sum", 0.0)) + mr, 4)
        b["mfe_r_n"] = int(b.get("mfe_r_n", 0)) + 1
        b["mfe_r_sumsq"] = round(float(b.get("mfe_r_sumsq", 0.0)) + mr * mr, 4)
        h = b.setdefault("hist_mfe_r", [0] * _TM_NBINS)
        h[_bin_index(mr)] += 1
    if path.mae_r is not None:
        ar = float(path.mae_r)
        b["mae_r_sum"] = round(float(b.get("mae_r_sum", 0.0)) + ar, 4)
        b["mae_r_n"] = int(b.get("mae_r_n", 0)) + 1
        b["mae_r_sumsq"] = round(float(b.get("mae_r_sumsq", 0.0)) + ar * ar, 4)
        h = b.setdefault("hist_mae_r", [0] * _TM_NBINS)
        h[_bin_index(ar)] += 1
    if path.cur_reached_tp1:
        b["tp1"] = int(b.get("tp1", 0)) + 1
    if path.cur_reached_tp2:
        b["tp2"] = int(b.get("tp2", 0)) + 1
    if path.cur_reached_tp3:
        b["tp3"] = int(b.get("tp3", 0)) + 1
    if path.cur_gave_back_after_tp1:
        b["give_back"] = int(b.get("give_back", 0)) + 1

    # ── CM2-2 additive aggregates (policy-independent unless noted) ──────────────
    if path.mfe_atr is not None:
        b["mfe_atr_sum"] = round(float(b.get("mfe_atr_sum", 0.0)) + float(path.mfe_atr), 4)
        b["mfe_atr_n"] = int(b.get("mfe_atr_n", 0)) + 1
    if path.mae_atr is not None:
        b["mae_atr_sum"] = round(float(b.get("mae_atr_sum", 0.0)) + float(path.mae_atr), 4)
        b["mae_atr_n"] = int(b.get("mae_atr_n", 0)) + 1
    if path.bars_total is not None:
        b["bars_total_sum"] = int(b.get("bars_total_sum", 0)) + int(path.bars_total)
        b["bars_total_n"] = int(b.get("bars_total_n", 0)) + 1
    if path.cur_bars_to_tp1 is not None:                  # policy-dependent
        b["bars_to_tp1_sum"] = int(b.get("bars_to_tp1_sum", 0)) + int(path.cur_bars_to_tp1)
        b["bars_to_tp1_n"] = int(b.get("bars_to_tp1_n", 0)) + 1
    if path.cur_realized_return is not None:              # policy-dependent
        rr = float(path.cur_realized_return)
        b["realized_sum"] = round(float(b.get("realized_sum", 0.0)) + rr, 4)
        b["realized_sumsq"] = round(float(b.get("realized_sumsq", 0.0)) + rr * rr, 4)
        b["realized_n"] = int(b.get("realized_n", 0)) + 1
    # Entry-quality: planned R:R recomputed from stored prices (single-source
    # trade_geometry.planned_rr — works for every row, no extra-JSON dependency).
    prr = planned_rr(_f(path.entry_price), _f(path.sl_price), _f(path.tp1_price))
    if prr is not None:
        b["planned_rr_tp1_sum"] = round(float(b.get("planned_rr_tp1_sum", 0.0)) + prr, 4)
        b["planned_rr_tp1_n"] = int(b.get("planned_rr_tp1_n", 0)) + 1
        if prr < 1.0:
            b["sub1_rr"] = int(b.get("sub1_rr", 0)) + 1
    # Stop-too-tight: canonical label (DRY — reuse the classification, don't re-derive).
    if getattr(path, "detail_label", None) == labels.CORRECT_DIR_TIGHT_SL:
        b["tight_sl"] = int(b.get("tight_sl", 0)) + 1


# ════════════════════════════════════════════════════════════════════════════
# CMV2-A — data contract & versioning for the Coin Memory v2 track
# ════════════════════════════════════════════════════════════════════════════
# An ADDITIVE, VERSIONED namespace living beside the v1 buckets inside tm_stats.
# Per cell it records:
#   • which fold rule produced the numbers, counted per rule — so CMV2-B's
#     aggregates stay interpretable after the rule is ever bumped;
#   • the cohort MIX the cell was built from. A HISTOGRAM, not a scalar label:
#     CP-COIN-MEMORY-V2-FORENSIC §7 measured that a cell mixes pre- and post-F1
#     folds, and a single label here would hide exactly that;
#   • why a fold would be INELIGIBLE for a future v2 metric, counted per reason;
#   • an audit stamp for the last fold.
#
# OBSERVATION ONLY, and deliberately less than it could be: no v2 metric is
# aggregated (CMV2-B), no recency/decay/reliability is applied (CMV2-C), no
# adaptive behaviour changes. v1 eligibility is untouched — every row v1 folds
# today is still folded, with the same numbers.
#
# NOTHING on the decision path reads this namespace; that is locked at source
# level by tests/test_cmv2a_contract.py, not left to convention.

CM_V2_NAMESPACE = "cm_v2"
CM_V2_CONTRACT_VERSION = "cm_v2_contract_1"
CM_V2_FOLD_RULE_VERSION = "cm_v2_fold_1"

# Cohort sentinels. LEGACY is a POSITIVE finding — a candidate row exists and
# carries no version field, so the decision provably predates the versioned
# contract. UNKNOWN means it could not be established at all. Neither is ever
# inferred from a timestamp: a date can suggest a cohort, it cannot record one.
CM_V2_COHORT_LEGACY = "legacy"
CM_V2_COHORT_UNKNOWN = "unknown"

# Bounded duplicate guard: the last N fold ids for this cell, newest last. Gates
# the v2 counters ONLY. v1 has its own, stronger guard — signal_trade_path.
# signal_id is UNIQUE and _persist_trade_path_once returns False on a repeat, so
# the v1 fold is never even reached twice — and it is never gated by this ring.
CM_V2_DEDUPE_WINDOW = 32

# Multi-label: a fold may fire several of these at once, so the counters are NOT
# expected to sum to `observed`.
CM_V2_EXCLUSION_REASONS = (
    "active",
    "intrabar_ambiguous",
    "still_forming_resolution",
    "missing_decision_input_version",
    "missing_policy_version",
)


def v1_tm_buckets(tm: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The v1 regime/`_all` buckets only, with the additive v2 namespace stripped.

    The rebuild-vs-online invariant is stated over THIS rather than over the raw
    JSON, because cm_v2 is a fold-EVENT ledger: it carries `last_fold` with a
    wall-clock stamp, and a bulk rebuild cannot reproduce an event log. Public on
    purpose — the F0 gate compares through it, so the v1 half of the invariant
    keeps its full teeth instead of being loosened to accommodate the namespace.
    """
    return {k: v for k, v in (tm or {}).items() if k != CM_V2_NAMESPACE}


def unknown_cohort(source: str = "candidate_missing") -> Dict[str, Any]:
    """The cohort when nothing could be established. Explicit sentinels only —
    an absent value must read as absent, never as a plausible default."""
    return {
        "decision_input_version": CM_V2_COHORT_UNKNOWN,
        "decision_input_version_source": source,
        "policy_version": CM_V2_COHORT_UNKNOWN,
        "policy_version_source": "unavailable",
    }


def _outcome_str(path) -> str:
    val = getattr(path, "outcome", None)
    if val is None:
        return ""
    return str(val.value if hasattr(val, "value") else val)


def cm_v2_exclusions(path, cohort: Optional[Dict[str, Any]]) -> Dict[str, bool]:
    """Why this fold would be INELIGIBLE for a v2 metric. PURE. MULTI-LABEL.

    Changes nothing about v1: this is an opinion ABOUT a fold, recorded next to
    it, never a gate on it.
    """
    outcome = _outcome_str(path).lower()
    div = (cohort or {}).get("decision_input_version")
    pol = (cohort or {}).get("policy_version")
    return {
        # Defensive predicate. A signal_trade_path row is written AT resolution,
        # so no production row carries an ACTIVE outcome and this is expected to
        # stay 0. Kept live and tested anyway, so an unresolved row could never
        # be silently aggregated as a resolved one.
        "active": outcome == "active",
        "intrabar_ambiguous": bool(getattr(path, "intrabar_ambiguous", False)),
        "still_forming_resolution": bool(getattr(path, "still_forming_resolution", False)),
        # No RECORDED version string → both `legacy` and `unknown` count here.
        # The cohort histogram keeps the two distinguishable, so collapsing them
        # into one eligibility counter loses nothing.
        "missing_decision_input_version": div in (
            None, "", CM_V2_COHORT_LEGACY, CM_V2_COHORT_UNKNOWN),
        "missing_policy_version": pol in (None, "", CM_V2_COHORT_UNKNOWN),
    }


def _empty_cm_v2() -> Dict[str, Any]:
    return {
        "version": CM_V2_CONTRACT_VERSION,
        "fold_rule_version": CM_V2_FOLD_RULE_VERSION,
        "cohort": {"decision_input_version": {}, "policy_version": {}},
        "counts": {
            "observed": 0,
            "included": 0,
            "excluded": {r: 0 for r in CM_V2_EXCLUSION_REASONS},
            "by_fold_rule": {},
        },
        "last_fold": {
            "signal_id": None, "outcome": None, "resolved_at": None,
            "folded_at": None, "included": None,
            "decision_input_version": None, "policy_version": None,
        },
        "recent_fold_ids": [],
        "dedupe_window": CM_V2_DEDUPE_WINDOW,
        "duplicate_folds_skipped": 0,
        # CMV2-B: populated only by an INCLUDED fold; stays None until then.
        CM_V2_AGG_KEY: None,
    }


def _nn_int(v: Any) -> int:
    """Non-negative int from untrusted JSON (bools and junk → 0)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return 0
    try:
        return max(0, int(v))
    except (ValueError, OverflowError):
        return 0


def _hist(src: Any) -> Dict[str, int]:
    """Carry a {label: count} histogram forward, dropping anything malformed."""
    if not isinstance(src, dict):
        return {}
    return {str(k): _nn_int(v) for k, v in src.items() if _nn_int(v) > 0}


# ════════════════════════════════════════════════════════════════════════════
# CMV2-B — forward aggregation (SHADOW-ONLY)
# ════════════════════════════════════════════════════════════════════════════
# Raw, additive accumulators for trade-management metrics, kept per
# (fold rule × cohort × facet) inside the CMV2-A namespace. Forward-only: it can
# only ever describe folds that happen after it ships, because a bulk rebuild
# cannot reproduce a fold event (CMV2-A §rebuild).
#
# What it stores is SUFFICIENT STATISTICS, never derived rates:
#   n / sum / sumsq            → mean, variance, std later
#   pos_sum / neg_abs_sum      → profit factor later, WITHOUT dividing by zero now
#   bounded histogram          → approximate (bucket) median later
# Nothing here computes expectancy, PF, a rate, a reliability tier or a weight.
# That is deliberate: a stored ratio freezes a denominator decision, and the
# denominator contract is exactly what CP-COIN-MEMORY-V2-FORENSIC found v1 got
# wrong (two different win-rate denominators in one cell).
#
# EVERY metric carries its OWN denominator. A fold that is included overall may
# still be missing one field, and a missing field is counted as `missing`, never
# folded in as 0 — "not measured" and "0 happened" must stay distinguishable.
#
# Read by NOTHING on the decision path; locked at source level in
# tests/test_cmv2b_aggregation.py.

CM_V2_AGG_KEY = "forward_aggregates"
CM_V2_AGGREGATION_VERSION = "cm_v2_aggregation_1"
# Bump when the MEANING of a metric changes: the stop-label partition, a
# denominator rule, or an edge set. Separate from the aggregation version so a
# pure container change and a semantic change are distinguishable.
CM_V2_METRIC_RULE_VERSION = "cm_v2_metric_1"

# Realized R is SIGNED, so TM_R_EDGES (0.25 … 5.0, unsigned) cannot be reused for
# it: _bin_index maps every negative value to bucket 0, which would collapse all
# losses into one bar and make the distribution useless. MFE/MAE are non-negative
# magnitudes and DO reuse TM_R_EDGES — same numbers as the v1 buckets, so the two
# stay comparable.
CM_V2_SIGNED_R_EDGES = [-3.0, -2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 3.0]
_CM_V2_SIGNED_NBINS = len(CM_V2_SIGNED_R_EDGES) + 1

# Canonical, bounded facet vocabularies — taken from the enums/functions that
# actually produce these values, not invented here:
#   app/models/signal.py:48            Direction
#   app/engines/market_regime/detector.py:35   MarketRegime
#   app/backtesting/trade_path.py:45           volatility_bucket()
# Anything outside a whitelist lands in `unknown`, so no fold can create an
# arbitrary key and the per-cell JSON stays bounded.
CM_V2_UNKNOWN = "unknown"
# A facet that was never recorded is NOT the same as one measured as "unknown":
# MarketRegime has a real UNKNOWN member, while a NULL column means the snapshot
# was absent. Collapsing them would be the one place this design breaks its own
# "missing is not a measured value" rule. (Production incidence today: 0 — regime,
# direction and volatility_bucket are 0% NULL over 3112 rows. Kept separate anyway,
# because a rate computed over a merged denominator would be wrong silently.)
CM_V2_NOT_RECORDED = "not_recorded"
CM_V2_DIRECTIONS = ("bullish", "bearish", "neutral")
CM_V2_REGIMES = ("trending_bull", "trending_bear", "ranging", "volatile_high",
                 "low_volume", "breakout", "unknown")
CM_V2_VOLATILITY_BUCKETS = ("low", "normal", "high", "extreme")
# SignalOutcome values (app/models/signal.py:55) — lower-case, as trade_path
# stores `perf.outcome.value`. ACTIVE is absent on purpose: it never reaches here.
CM_V2_OUTCOMES = ("win", "loss", "breakeven", "expired", "invalidated")

# Cohort keys are bounded by construction (a fold with a missing version is
# excluded before it gets here), but a cap makes that a guarantee rather than an
# expectation. Overflow is counted, never silently dropped.
CM_V2_MAX_COHORT_KEYS = 8

# Outcomes whose realized return reflects OUR policy rather than the trade thesis
# resolving in the market. Excluded from the realized-R distribution and counted
# separately; v1's INVALIDATED=LOSS mapping is untouched (a different layer).
#
# MEASURED LIMIT: no signal_trade_path row carries `invalidated` today. Over 3112
# production rows `outcome` takes exactly three values (loss 1199 / win 1126 /
# breakeven 787), because the reversal and admin paths never write a trade-path
# row. So this guard is defensive and structurally never fires, and
# `outcomes.invalidated` / `outcomes.expired` stay 0. That is precisely why the
# resolution class below is derived from `detail_label` instead: expiry IS visible
# there (expired_loss / expired_profit / expired_flat) even though `outcome` has
# already collapsed it into win/loss/breakeven.
CM_V2_R_EXCLUDED_OUTCOMES = ("invalidated",)

# How the trade actually ended, recovered from the canonical label rather than from
# `outcome`. Answers "stopped / paid / timed out" — which the binary stop split and
# the outcome counters both lose.
CM_V2_RES_STOP = "stop"
CM_V2_RES_TARGET = "target"
CM_V2_RES_EXPIRY = "expiry"
CM_V2_RES_REVERSAL = "reversal"
CM_V2_RESOLUTION_CLASSES = (CM_V2_RES_STOP, CM_V2_RES_TARGET, CM_V2_RES_EXPIRY,
                            CM_V2_RES_REVERSAL, CM_V2_UNKNOWN)


def cm_v2_cohort_key(cohort: Optional[Dict[str, Any]]) -> str:
    """Stable aggregate key for a cohort. Derived ONLY from recorded version
    values — never from a timestamp."""
    c = cohort or {}
    div = str(c.get("decision_input_version", CM_V2_COHORT_UNKNOWN))
    pol = str(c.get("policy_version", CM_V2_COHORT_UNKNOWN))
    return f"decision_input_version={div}|policy_version={pol}"


def _facet(value: Any, allowed: Tuple[str, ...]) -> str:
    """Normalise a facet value onto its canonical whitelist.

    Three distinct outcomes, deliberately not two:
      • a whitelisted value            → itself
      • absent / empty                 → `not_recorded` (never measured)
      • present but off-whitelist      → `unknown` (measured, unrecognised)
    """
    if value is None:
        return CM_V2_NOT_RECORDED
    val = value.value if hasattr(value, "value") else value
    val = str(val).strip().lower()
    if not val:
        return CM_V2_NOT_RECORDED
    return val if val in allowed else CM_V2_UNKNOWN


def cm_v2_resolution_class(label: Optional[str]) -> str:
    """How the trade ended, from the canonical detail label. PURE.

    Derived from `detail_label` rather than `outcome` because outcome collapses
    expiry into win/loss/breakeven: 33 v2-eligible production rows are expiries that
    `outcome` cannot distinguish from a target hit or a stop.
    """
    if label in labels.STOP_HIT_LABELS:
        return CM_V2_RES_STOP
    if label in (labels.TP1_HIT, labels.TP2_HIT, labels.TP3_HIT,
                 labels.TP1_THEN_BREAKEVEN):
        return CM_V2_RES_TARGET
    if label in (labels.EXPIRED_PROFIT, labels.EXPIRED_LOSS, labels.EXPIRED_FLAT):
        return CM_V2_RES_EXPIRY
    if label == labels.INVALIDATED_REVERSAL:
        return CM_V2_RES_REVERSAL
    return CM_V2_UNKNOWN


def _num(x: Any) -> Optional[float]:
    """Finite float or None. Rejects NaN/inf so one corrupt row cannot poison a
    running sum forever — an accumulator has no way to un-add an inf."""
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _signed_bin_index(v: float) -> int:
    for i, e in enumerate(CM_V2_SIGNED_R_EDGES):
        if v < e:
            return i
    return len(CM_V2_SIGNED_R_EDGES)


def _empty_dist(nbins: int, signed: bool = False) -> Dict[str, Any]:
    d: Dict[str, Any] = {"n": 0, "sum": 0.0, "sumsq": 0.0,
                         "hist": [0] * nbins, "missing": 0}
    if signed:
        d.update({"pos_n": 0, "neg_n": 0, "zero_n": 0,
                  "pos_sum": 0.0, "neg_abs_sum": 0.0, "excluded_outcome_n": 0})
    return d


def _empty_scalar() -> Dict[str, Any]:
    return {"n": 0, "sum": 0.0, "sumsq": 0.0, "missing": 0}


def _empty_agg_bucket() -> Dict[str, Any]:
    """One accumulator bucket.

    SIGN CONVENTIONS DIFFER INSIDE THIS BUCKET, on purpose, and a reader must know:
      • `realized_r` is SIGNED — a full stop is about -1.0 (or worse on a gap).
      • `mfe_r` / `mae_r` are unsigned MAGNITUDES: the tracker clamps both with
        max(0.0, …) before storing, so an adverse excursion of one risk unit is
        mae_r = +1.0, not -1.0. Verified on production: 0 negative values in 1829
        v2-eligible rows, and mae_r > 1.0 in 539 of them (29.5%) because the
        excursion is measured to the bar low/high, so a gap-through overshoots.
    Mixing the two into one mean would be meaningless, which is why they never share
    an accumulator or an edge set.
    """
    return {
        "included_fold_n": 0,
        # signed realized R — its own edge set
        "realized_r": _empty_dist(_CM_V2_SIGNED_NBINS, signed=True),
        # unsigned magnitudes — reuse TM_R_EDGES so v1 and v2 stay comparable
        "mfe_r": _empty_dist(_TM_NBINS),
        "mae_r": _empty_dist(_TM_NBINS),
        # additive observability in other units; names carry the unit
        "mfe_pct": _empty_scalar(), "mae_pct": _empty_scalar(),
        "mfe_atr": _empty_scalar(), "mae_atr": _empty_scalar(),
        "tp_reach": {"tp1_eligible_n": 0, "tp1_n": 0,
                     "tp2_eligible_n": 0, "tp2_n": 0,
                     "tp3_eligible_n": 0, "tp3_n": 0,
                     "inconsistent_n": 0},
        # `stop_n` counts rows LABELLED as a stop hit. Honest caveat: the
        # classifier's fallback branch (labels.py classify_resolution, last line)
        # can return sl_hit on pnl_pct < 0 alone, with resolved_by_sl False and no
        # stop observed — so this is "labelled a stop", not "provably touched the
        # stop". Stored rows cannot be told apart. Fixing that means changing the
        # classifier, which is a resolution-semantics change and out of scope here.
        "stop": {"eligible_n": 0, "stop_n": 0, "non_stop_n": 0, "unknown_n": 0},
        # What `outcome` cannot say: stopped / paid / timed out / reversed.
        "resolution_class": {k: 0 for k in CM_V2_RESOLUTION_CLASSES},
        # NAME WARNING: the stored source column is literally
        # `bool(perf.hit_tp1) and not bool(perf.hit_tp2)` (tracker.py:112), so this
        # is a "banked TP1 but never reached TP2" rate, NOT a measure of profit
        # handed back from a peak. Verified identical on production: TP1&!TP2 = 580
        # = gave_back True = 580 over the v2-eligible subset. Read it accordingly;
        # renaming the column is a trade-path schema change, not a CMV2-B one.
        "give_back": {"eligible_n": 0, "gave_back_n": 0,
                      "did_not_give_back_n": 0, "unknown_n": 0},
        "outcomes": {k: 0 for k in CM_V2_OUTCOMES + (CM_V2_UNKNOWN,)},
    }


def _add_dist(d: Dict[str, Any], value: Optional[float], nbins: int,
              signed: bool, binner) -> None:
    """Fold one observation into a distribution. A missing value increments
    `missing` and NOTHING else — it must never look like a measured 0."""
    if value is None:
        d["missing"] = _nn_int(d.get("missing")) + 1
        return
    d["n"] = _nn_int(d.get("n")) + 1
    d["sum"] = round(float(d.get("sum", 0.0) or 0.0) + value, 6)
    d["sumsq"] = round(float(d.get("sumsq", 0.0) or 0.0) + value * value, 6)
    hist = d.get("hist")
    if not isinstance(hist, list) or len(hist) != nbins:
        hist = [0] * nbins
    idx = binner(value)
    hist[idx] = _nn_int(hist[idx]) + 1
    d["hist"] = hist
    if signed:
        if value > 0:
            d["pos_n"] = _nn_int(d.get("pos_n")) + 1
            d["pos_sum"] = round(float(d.get("pos_sum", 0.0) or 0.0) + value, 6)
        elif value < 0:
            d["neg_n"] = _nn_int(d.get("neg_n")) + 1
            d["neg_abs_sum"] = round(float(d.get("neg_abs_sum", 0.0) or 0.0) + abs(value), 6)
        else:
            d["zero_n"] = _nn_int(d.get("zero_n")) + 1


def _add_scalar(s: Dict[str, Any], value: Optional[float]) -> None:
    if value is None:
        s["missing"] = _nn_int(s.get("missing")) + 1
        return
    s["n"] = _nn_int(s.get("n")) + 1
    s["sum"] = round(float(s.get("sum", 0.0) or 0.0) + value, 6)
    s["sumsq"] = round(float(s.get("sumsq", 0.0) or 0.0) + value * value, 6)


def cm_v2_path_metrics(path) -> Dict[str, Any]:
    """PURE: one trade path → the metric observations CMV2-B accumulates.

    Uses the CANONICAL definitions, never a re-derivation:
      • mfe_r / mae_r are read straight off the row (computed once in
        trade_path.py:249-250 as safe_div(excursion_pct, sl_dist_pct));
      • realized R uses that SAME helper and that SAME denominator, so "R" means
        one thing across the codebase — safe_div returns None when sl_dist_pct is
        missing or zero, so there is no division-by-zero branch to get wrong here.

    A field that cannot be measured comes back None, never 0.
    """
    sl_dist = _num(getattr(path, "sl_dist_pct", None))
    realized_pct = _num(getattr(path, "cur_realized_return", None))
    realized_r = _num(safe_div(realized_pct, sl_dist))

    outcome = _outcome_str(path).lower()
    label = getattr(path, "detail_label", None)
    label = str(label) if label else None

    if label in labels.STOP_HIT_LABELS:
        stop = "stop"
    elif label in labels.NON_STOP_TERMINAL_LABELS:
        stop = "non_stop"
    else:
        stop = CM_V2_UNKNOWN

    tp1 = getattr(path, "cur_reached_tp1", None)
    tp2 = getattr(path, "cur_reached_tp2", None)
    tp3 = getattr(path, "cur_reached_tp3", None)
    gave_back = getattr(path, "cur_gave_back_after_tp1", None)

    return {
        "realized_r": realized_r,
        "realized_r_excluded": outcome in CM_V2_R_EXCLUDED_OUTCOMES,
        "mfe_r": _num(getattr(path, "mfe_r", None)),
        "mae_r": _num(getattr(path, "mae_r", None)),
        "mfe_pct": _num(getattr(path, "mfe_pct", None)),
        "mae_pct": _num(getattr(path, "mae_pct", None)),
        "mfe_atr": _num(getattr(path, "mfe_atr", None)),
        "mae_atr": _num(getattr(path, "mae_atr", None)),
        "tp1": None if tp1 is None else bool(tp1),
        "tp2": None if tp2 is None else bool(tp2),
        "tp3": None if tp3 is None else bool(tp3),
        "gave_back": None if gave_back is None else bool(gave_back),
        "stop": stop,
        "resolution_class": cm_v2_resolution_class(label),
        "outcome": outcome if outcome in CM_V2_OUTCOMES else CM_V2_UNKNOWN,
        "facets": {
            "direction": _facet(getattr(path, "direction", None), CM_V2_DIRECTIONS),
            "regime": _facet(getattr(path, "regime", None), CM_V2_REGIMES),
            "volatility": _facet(getattr(path, "volatility_bucket", None),
                                 CM_V2_VOLATILITY_BUCKETS),
        },
    }


def _fold_into_agg_bucket(b: Dict[str, Any], m: Dict[str, Any]) -> None:
    """Fold one included observation into ONE bucket. Every metric advances only
    its own denominator."""
    b["included_fold_n"] = _nn_int(b.get("included_fold_n")) + 1

    # ── realized R ────────────────────────────────────────────────────────────
    r = b.setdefault("realized_r", _empty_dist(_CM_V2_SIGNED_NBINS, signed=True))
    if m["realized_r_excluded"]:
        # Counted, not folded: the close price reflects our reversal policy, not
        # the thesis resolving. Mixing it in would measure policy churn as edge.
        r["excluded_outcome_n"] = _nn_int(r.get("excluded_outcome_n")) + 1
    else:
        _add_dist(r, m["realized_r"], _CM_V2_SIGNED_NBINS, True, _signed_bin_index)

    # ── excursions ────────────────────────────────────────────────────────────
    _add_dist(b.setdefault("mfe_r", _empty_dist(_TM_NBINS)), m["mfe_r"],
              _TM_NBINS, False, _bin_index)
    _add_dist(b.setdefault("mae_r", _empty_dist(_TM_NBINS)), m["mae_r"],
              _TM_NBINS, False, _bin_index)
    for key in ("mfe_pct", "mae_pct", "mfe_atr", "mae_atr"):
        _add_scalar(b.setdefault(key, _empty_scalar()), m[key])

    # ── TP reach — NULL is not False; it is simply not eligible ───────────────
    tp = b.setdefault("tp_reach", _empty_agg_bucket()["tp_reach"])
    for n, val in (("tp1", m["tp1"]), ("tp2", m["tp2"]), ("tp3", m["tp3"])):
        if val is None:
            continue
        tp[f"{n}_eligible_n"] = _nn_int(tp.get(f"{n}_eligible_n")) + 1
        if val:
            tp[f"{n}_n"] = _nn_int(tp.get(f"{n}_n")) + 1
    # A deeper target reached without the shallower one is not silently repaired —
    # it is counted so the anomaly stays visible in the data itself. Both flags must
    # be KNOWN: `tp2=True, tp1=None` is unknown, not an inconsistency, and treating
    # NULL as False would manufacture the very anomaly this counter reports.
    if (m["tp2"] is True and m["tp1"] is False) or (m["tp3"] is True and m["tp2"] is False):
        tp["inconsistent_n"] = _nn_int(tp.get("inconsistent_n")) + 1

    # ── stop ─────────────────────────────────────────────────────────────────
    st = b.setdefault("stop", _empty_agg_bucket()["stop"])
    if m["stop"] == CM_V2_UNKNOWN:
        st["unknown_n"] = _nn_int(st.get("unknown_n")) + 1
    else:
        st["eligible_n"] = _nn_int(st.get("eligible_n")) + 1
        key = "stop_n" if m["stop"] == "stop" else "non_stop_n"
        st[key] = _nn_int(st.get(key)) + 1

    # ── give-back — eligible ONLY when TP1 was actually banked ────────────────
    gb = b.setdefault("give_back", _empty_agg_bucket()["give_back"])
    if m["tp1"] is not True:
        pass                                  # never reached TP1 → not a give-back question
    elif m["gave_back"] is None:
        gb["unknown_n"] = _nn_int(gb.get("unknown_n")) + 1
    else:
        gb["eligible_n"] = _nn_int(gb.get("eligible_n")) + 1
        key = "gave_back_n" if m["gave_back"] else "did_not_give_back_n"
        gb[key] = _nn_int(gb.get(key)) + 1

    # ── resolution class (what `outcome` cannot say) ──────────────────────────
    rc = b.setdefault("resolution_class", _empty_agg_bucket()["resolution_class"])
    rc[m["resolution_class"]] = _nn_int(rc.get(m["resolution_class"])) + 1

    # ── outcomes (observation only; produces no rate) ─────────────────────────
    oc = b.setdefault("outcomes", _empty_agg_bucket()["outcomes"])
    oc[m["outcome"]] = _nn_int(oc.get(m["outcome"])) + 1


def _agg_bucket(container: Dict[str, Any], key: str) -> Dict[str, Any]:
    """Fetch-or-create a bucket lazily, repairing a non-dict in place. Lazy on
    purpose: a cell that only ever sees one regime carries one regime bucket, not
    the whole vocabulary, which is what keeps the stored JSON small."""
    cur = container.get(key)
    if not isinstance(cur, dict):
        cur = _empty_agg_bucket()
        container[key] = cur
    return cur


def observe_cm_v2_aggregates(
    existing: Any,
    path,
    cohort: Optional[Dict[str, Any]],
    folded_at: Optional[str],
) -> Dict[str, Any]:
    """PURE: previous forward-aggregate blob + one INCLUDED fold → the next blob.

    The caller decides inclusion (it is CMV2-A's `included`), so this function is
    only ever handed folds that passed every exclusion gate. Anything of the wrong
    shape is rebuilt from the default instead of raising.

    `existing` is DEEP-copied first. Shallow copies are not enough here: the value
    being folded into is a bucket several levels down, with `hist` lists inside it,
    so a shallow copy would leave the caller's dict aliased and the fold would
    mutate history in place. That is not a theoretical concern — the CMV2-A purity
    test caught exactly this on the first run.
    """
    src = copy.deepcopy(existing) if isinstance(existing, dict) else {}
    by_rule_src = src.get("by_fold_rule")
    by_rule = dict(by_rule_src) if isinstance(by_rule_src, dict) else {}

    rule_node = by_rule.get(CM_V2_FOLD_RULE_VERSION)
    rule_node = dict(rule_node) if isinstance(rule_node, dict) else {}

    # The metric rule PARTITIONS the numbers, it does not merely label them. Its
    # documented bump triggers — the stop-label partition, a denominator rule, an
    # edge set — all change what a sum MEANS, so pre-bump and post-bump observations
    # must not share an accumulator. A flat version field would have left old
    # observations inside the same sum/sumsq/hist with only the new label visible,
    # which is exactly the "geriye dönük yorumlanamaz" failure CMV2-A existed to
    # prevent one level up.
    by_metric_src = rule_node.get("by_metric_rule")
    by_metric = dict(by_metric_src) if isinstance(by_metric_src, dict) else {}
    metric_node = by_metric.get(CM_V2_METRIC_RULE_VERSION)
    metric_node = dict(metric_node) if isinstance(metric_node, dict) else {}

    by_cohort_src = metric_node.get("by_cohort")
    by_cohort = dict(by_cohort_src) if isinstance(by_cohort_src, dict) else {}

    ck = cm_v2_cohort_key(cohort)
    dropped = _nn_int(src.get("cohort_keys_dropped"))
    not_aggregated = _nn_int(src.get("included_not_aggregated_n"))
    if ck not in by_cohort and len(by_cohort) >= CM_V2_MAX_COHORT_KEYS:
        # Bounded by construction, but never silently. Counted TWICE on purpose:
        # `cohort_keys_dropped` says the cap fired, `included_not_aggregated_n`
        # keeps the arithmetic reconcilable against CMV2-A's `counts.included`
        # (which has already counted this fold). Without it the two denominators
        # would differ with nothing recording why.
        dropped += 1
        not_aggregated += 1
    else:
        cohort_node = by_cohort.get(ck)
        cohort_node = dict(cohort_node) if isinstance(cohort_node, dict) else {}
        m = cm_v2_path_metrics(path)

        _fold_into_agg_bucket(_agg_bucket(cohort_node, "all"), m)
        for facet_name, allowed in (("direction", CM_V2_DIRECTIONS),
                                    ("regime", CM_V2_REGIMES),
                                    ("volatility", CM_V2_VOLATILITY_BUCKETS)):
            node = cohort_node.get(facet_name)
            node = dict(node) if isinstance(node, dict) else {}
            _fold_into_agg_bucket(_agg_bucket(node, m["facets"][facet_name]), m)
            cohort_node[facet_name] = node

        by_cohort[ck] = cohort_node

    metric_node["by_cohort"] = by_cohort
    by_metric[CM_V2_METRIC_RULE_VERSION] = metric_node
    rule_node["by_metric_rule"] = by_metric
    by_rule[CM_V2_FOLD_RULE_VERSION] = rule_node

    sid = getattr(path, "signal_id", None)
    resolved_at = getattr(path, "resolved_at", None)
    return {
        "aggregation_version": CM_V2_AGGREGATION_VERSION,
        # The version this writer is currently on. The data itself is partitioned by
        # it in the tree above; this field is the pointer, not the partition.
        "metric_rule_version": CM_V2_METRIC_RULE_VERSION,
        # Which folds these numbers describe. Stated explicitly because the same
        # tm_stats column also carries v1 buckets over a WIDER population (every
        # foldable row) — so a reader comparing a v1 mean with a v2 mean is
        # comparing different denominators unless they read this.
        "population": "cmv2a_included_only",
        "by_fold_rule": by_rule,
        "cohort_keys_dropped": dropped,
        "included_not_aggregated_n": not_aggregated,
        "last_included_fold": {
            "signal_id": str(sid) if sid is not None else None,
            "cohort_key": ck,
            "resolved_at": resolved_at.isoformat() if hasattr(resolved_at, "isoformat")
                           else (str(resolved_at) if resolved_at is not None else None),
            "folded_at": folded_at,
        },
    }


def observe_cm_v2_fold(
    existing: Any,
    path,
    cohort: Optional[Dict[str, Any]],
    folded_at: Optional[str],
) -> Dict[str, Any]:
    """PURE: previous namespace + one fold → the next namespace.

    No DB, no clock (`folded_at` is passed in), no mutation of `existing` — the
    same discipline fold_signal_into follows, for the same reason: a pure step is
    the only one a test can pin exactly.

    Duplicate-safe within CM_V2_DEDUPE_WINDOW folds of the same cell: a repeat of
    a signal_id still in the ring bumps `duplicate_folds_skipped` and touches
    NOTHING else. An `existing` value of the wrong shape is rebuilt from the
    default rather than raising — a corrupt observability blob must never be able
    to cost a fold.
    """
    src = existing if isinstance(existing, dict) else {}
    counts_src = src.get("counts") if isinstance(src.get("counts"), dict) else {}
    exc_src = counts_src.get("excluded") if isinstance(counts_src.get("excluded"), dict) else {}
    coh_src = src.get("cohort") if isinstance(src.get("cohort"), dict) else {}
    ring_src = src.get("recent_fold_ids")
    ring = [str(x) for x in ring_src if isinstance(x, str)] if isinstance(ring_src, list) else []

    out = _empty_cm_v2()
    out["cohort"] = {
        "decision_input_version": _hist(coh_src.get("decision_input_version")),
        "policy_version": _hist(coh_src.get("policy_version")),
    }
    out["counts"]["observed"] = _nn_int(counts_src.get("observed"))
    out["counts"]["included"] = _nn_int(counts_src.get("included"))
    out["counts"]["excluded"] = {r: _nn_int(exc_src.get(r)) for r in CM_V2_EXCLUSION_REASONS}
    out["counts"]["by_fold_rule"] = _hist(counts_src.get("by_fold_rule"))
    out["duplicate_folds_skipped"] = _nn_int(src.get("duplicate_folds_skipped"))
    out["recent_fold_ids"] = ring
    if isinstance(src.get("last_fold"), dict):
        out["last_fold"] = {**out["last_fold"], **{
            k: v for k, v in src["last_fold"].items() if k in out["last_fold"]}}

    # CMV2-B blob rides along unchanged unless an INCLUDED fold updates it below.
    # Carried forward BEFORE the duplicate branch, so a repeat preserves history
    # instead of dropping it.
    prior_agg = src.get(CM_V2_AGG_KEY)
    out[CM_V2_AGG_KEY] = prior_agg if isinstance(prior_agg, dict) else None

    sid = getattr(path, "signal_id", None)
    sid = str(sid) if sid is not None else None
    if sid is not None and sid in ring:
        out["duplicate_folds_skipped"] += 1
        return out                       # every other counter untouched

    coh = cohort if isinstance(cohort, dict) else unknown_cohort("cohort_unavailable")
    div = str(coh.get("decision_input_version", CM_V2_COHORT_UNKNOWN))
    pol = str(coh.get("policy_version", CM_V2_COHORT_UNKNOWN))
    excl = cm_v2_exclusions(path, coh)
    included = not any(excl.values())

    out["counts"]["observed"] += 1
    if included:
        out["counts"]["included"] += 1
    for reason, fired in excl.items():
        if fired:
            out["counts"]["excluded"][reason] += 1
    out["counts"]["by_fold_rule"][CM_V2_FOLD_RULE_VERSION] = (
        out["counts"]["by_fold_rule"].get(CM_V2_FOLD_RULE_VERSION, 0) + 1)
    out["cohort"]["decision_input_version"][div] = (
        out["cohort"]["decision_input_version"].get(div, 0) + 1)
    out["cohort"]["policy_version"][pol] = (
        out["cohort"]["policy_version"].get(pol, 0) + 1)

    resolved_at = getattr(path, "resolved_at", None)
    out["last_fold"] = {
        "signal_id": sid,
        "outcome": _outcome_str(path) or None,
        "resolved_at": resolved_at.isoformat() if hasattr(resolved_at, "isoformat")
                       else (str(resolved_at) if resolved_at is not None else None),
        "folded_at": folded_at,
        "included": included,
        "decision_input_version": div,
        "policy_version": pol,
    }
    if sid is not None:
        out["recent_fold_ids"] = (ring + [sid])[-CM_V2_DEDUPE_WINDOW:]

    # CMV2-B: aggregate ONLY what CMV2-A accepted. One gate, one definition of
    # "included" — a second predicate here could drift from the counters above and
    # the two would disagree about the same fold.
    if included:
        out[CM_V2_AGG_KEY] = observe_cm_v2_aggregates(
            out[CM_V2_AGG_KEY], path, coh, folded_at)
    return out


async def _resolve_fold_cohort(db: AsyncSession, path) -> Dict[str, Any]:
    """Resolve this fold's cohort from RECORDED decision-time provenance.

    Chain, most reliable first — no step guesses:
      1. the candidate row's `extra.decision_input_version` (the string the
         decision itself stamped) plus its `policy_version` COLUMN;
      2. a candidate row whose `extra` has NO version key → `legacy`. Positive
         evidence: candidate logging was live, the version field did not exist yet;
      3. the key present but empty/null → `unknown` with its own source marker.
         The field existed and was not populated — a defect, not a cohort;
      4. no candidate row, or the lookup failed → `unknown`.

    Deliberately NOT in the chain: comparing `resolved_at` against the F1 deploy
    time. That was the forensic's whole point — inferred provenance must not be
    stored as recorded fact.

    ONE lookup on an indexed column, LIMIT 1 → no N+1 and no scan; folds run at
    resolution time (~10²/day), so this is not on any hot path. Never raises: any
    failure degrades to `unknown` with the reason recorded.

    Honest scope note: `policy_version` here is the CANDIDATE-LOG policy version
    (the only policy version the system records). It is provenance for the
    decision log, NOT an adaptive-weight policy version — no such version exists
    yet, and CMV2-C/F will have to introduce one.
    """
    sid = getattr(path, "signal_id", None)
    if sid is None:
        return unknown_cohort("no_signal_id")
    try:
        row = (await db.execute(
            select(SignalDecisionCandidate.extra, SignalDecisionCandidate.policy_version)
            .where(SignalDecisionCandidate.signal_id == sid)
            .order_by(SignalDecisionCandidate.evaluated_at.asc())
            .limit(1)
        )).first()
    except Exception as exc:  # noqa: BLE001 — provenance lookup may never break a fold
        logger.warning("[CoinMemory] cm_v2 cohort lookup failed for signal %s: %s", sid, exc)
        return unknown_cohort("lookup_failed")

    if row is None:
        return unknown_cohort("candidate_missing")

    extra, policy_version = row[0], row[1]
    out = unknown_cohort("candidate_row_without_version")
    if isinstance(policy_version, int) and not isinstance(policy_version, bool):
        out["policy_version"] = policy_version
        out["policy_version_source"] = "candidate_policy_version_column"

    if not isinstance(extra, dict) or "decision_input_version" not in extra:
        # The row predates the version field → provably legacy.
        out["decision_input_version"] = CM_V2_COHORT_LEGACY
        out["decision_input_version_source"] = "candidate_row_without_version"
        return out

    raw = extra.get("decision_input_version")
    if isinstance(raw, str) and raw.strip():
        out["decision_input_version"] = raw.strip()
        out["decision_input_version_source"] = "candidate_extra"
    else:
        out["decision_input_version"] = CM_V2_COHORT_UNKNOWN
        out["decision_input_version_source"] = "candidate_version_null"
    return out


async def update_trade_mgmt_stats(db: AsyncSession, path) -> None:
    """Fold a SignalTradePath row into its coin_memory cell's tm_stats. Regime
    is a sub-key plus an "_all" aggregate. Caller wraps this so any failure is
    fail-open (never blocks resolution). Does not commit (shares caller's txn)."""
    # CM2-1 fold-hardening: skip rows with no identity or legacy-contradictory
    # live-SL rows (single-source _fold_key). v2 + valid v1 rows pass through.
    key = _fold_key(path)
    if key is None:
        return
    symbol, timeframe = key

    # The session uses autoflush=False, and update_coin_memory may have just
    # created this same (symbol, timeframe) cell earlier in this transaction
    # without flushing. Flush first so our SELECT sees it — otherwise we'd
    # create a DUPLICATE and the whole pass commit would fail with a unique
    # violation (which, happening at commit, would even bypass the caller's
    # fail-open guard). This makes the rollup robust and order-independent.
    await db.flush()
    res = await db.execute(
        select(CoinMemory).where(CoinMemory.symbol == symbol, CoinMemory.timeframe == timeframe)
    )
    mem = res.scalar_one_or_none()
    if mem is None:
        mem = CoinMemory(symbol=symbol, timeframe=timeframe,
                         total_signals=0, wins=0, losses=0,
                         engine_stats={}, regime_stats={}, outcome_label_stats={})
        db.add(mem)
        await db.flush()  # surface this cell for any later same-cell update in the txn

    # Rebuild dict (so SQLAlchemy detects the JSON mutation) and fold into both
    # the regime bucket and the "_all" aggregate.
    tm = dict(mem.tm_stats or {})
    regime_key = path.regime or "unknown"
    for key in (regime_key, "_all"):
        bucket = dict(tm.get(key) or _empty_bucket())
        # ensure histogram lists are mutable copies
        bucket["hist_mfe_r"] = list(bucket.get("hist_mfe_r", [0] * _TM_NBINS))
        bucket["hist_mae_r"] = list(bucket.get("hist_mae_r", [0] * _TM_NBINS))
        _fold_into_bucket(bucket, path)
        tm[key] = bucket
    mem.tm_stats = tm
    mem.tm_sample_count = int(mem.tm_sample_count or 0) + 1

    # ── CMV2-A: additive data contract, assigned AFTER v1 is already committed
    # above. The ordering is the safety property: if anything in here raises, the
    # caller's fail-open envelope catches it and the v1 fold that landed a moment
    # ago still stands. Observability that can cost a fold is not observability.
    try:
        cohort = await _resolve_fold_cohort(db, path)
        namespace = observe_cm_v2_fold(
            tm.get(CM_V2_NAMESPACE), path, cohort,
            datetime.now(timezone.utc).isoformat(),
        )
        mem.tm_stats = {**tm, CM_V2_NAMESPACE: namespace}
    except Exception as exc:  # noqa: BLE001 — never let the contract reach the fold
        logger.warning("[CoinMemory] cm_v2 observation skipped for %s %s: %s",
                       symbol, timeframe, exc)


def _aggregate_tm_stats(
    paths: List[Any],
) -> Tuple[Dict[Tuple[str, str], Dict[str, Any]], Dict[Tuple[str, str], int], int]:
    """Pure in-memory rebuild of tm_stats from SignalTradePath rows. Returns
    (cells, counts, skipped): cells[(symbol,tf)] = {regime: bucket, '_all': bucket};
    counts[(symbol,tf)] = folded count. SAME logic as the online fold (_fold_key
    skip + _fold_into_bucket) so the rebuilt cache equals the online rollup."""
    cells: Dict[Tuple[str, str], Dict[str, Any]] = {}
    counts: Dict[Tuple[str, str], int] = {}
    skipped = 0
    for p in paths:
        key = _fold_key(p)
        if key is None:
            skipped += 1
            continue
        tm = cells.setdefault(key, {})
        for bk in (p.regime or "unknown", "_all"):
            _fold_into_bucket(tm.setdefault(bk, _empty_bucket()), p)
        counts[key] = counts.get(key, 0) + 1
    return cells, counts, skipped


async def rebuild_tm_stats(db: AsyncSession) -> Dict[str, int]:
    """Drop & rebuild every coin_memory.tm_stats from signal_trade_path (the SoT).

    tm_stats is a DERIVABLE CACHE → safe + idempotent: RESET each cell, then re-fold
    all valid paths through the SAME logic as the online rollup (CM2-1 legacy filter +
    CM2-2 aggregates). Reads the SoT, writes ONLY the tm_stats cache — never touches
    resolution_core/trade_path geometry or the v1 engine/regime weights. Caller commits."""
    paths = (await db.execute(
        select(SignalTradePath).order_by(SignalTradePath.created_at.asc())
    )).scalars().all()
    cells, counts, skipped = _aggregate_tm_stats(paths)

    mems = (await db.execute(select(CoinMemory))).scalars().all()
    existing = {(m.symbol, m.timeframe): m for m in mems}
    updated = created = 0
    for key, mem in existing.items():
        tm = cells.get(key)
        # CMV2-A: the additive namespace is a fold-EVENT ledger, not a derivable
        # aggregate — a bulk rebuild cannot reproduce `last_fold`/`folded_at`. So it
        # is carried forward UNTOUCHED: dropping it would silently destroy the audit
        # trail this checkpoint exists to create, and recomputing it would fabricate
        # fold timestamps. The v1 buckets are still rebuilt from scratch.
        preserved = (mem.tm_stats or {}).get(CM_V2_NAMESPACE) \
            if isinstance(mem.tm_stats, dict) else None
        rebuilt = dict(tm) if tm else {}
        if preserved is not None:
            rebuilt[CM_V2_NAMESPACE] = preserved
        mem.tm_stats = rebuilt or None
        mem.tm_sample_count = counts.get(key, 0)
        updated += 1
    for key, tm in cells.items():
        if key not in existing:
            db.add(CoinMemory(symbol=key[0], timeframe=key[1],
                              total_signals=0, wins=0, losses=0,
                              engine_stats={}, regime_stats={}, outcome_label_stats={},
                              tm_stats=tm, tm_sample_count=counts.get(key, 0)))
            created += 1
    return {"paths": len(paths), "folded": len(paths) - skipped, "skipped": skipped,
            "cells_updated": updated, "cells_created": created}


# ── CM2-4: read-only tm_stats reader (NO decision, NO score, NO recommendation) ──
# Per-cell gate: below MIN_TM_SAMPLES a bucket exposes ONLY raw counts (no rates /
# averages / dispersion). Mirrors similarity's MIN_SIMILAR_MATCHES / Faz-3's
# MIN_SAMPLES_FOR_ADAPTIVE so the whole stack degrades on one consistent rule.
MIN_TM_SAMPLES = 10


def _avg(total: float, n: int) -> Optional[float]:
    return round(total / n, 4) if n else None


def _std(total: float, sumsq: float, n: int) -> Optional[float]:
    """Population std from running sum + sum-of-squares (None if n < 2)."""
    if not n or n < 2:
        return None
    var = sumsq / n - (total / n) ** 2
    return round(math.sqrt(var), 4) if var > 0 else 0.0


def _pct(num: int, den: int) -> Optional[float]:
    return round(num / den * 100.0, 1) if den else None


def compute_coin_tm_summary(mem, regime: Optional[str] = None) -> Dict[str, Any]:
    """READ-ONLY interpretation of one tm_stats bucket (the given regime, else
    '_all'). Produces NO decision/score/recommendation — descriptive stats only,
    and below the per-cell sample threshold ONLY raw counts (no rates/averages).
    Never raises: returns has_data=False when the cache is missing/empty, so a
    caller can surface it best-effort without ever affecting signal generation."""
    # CMV2-A: read through v1_tm_buckets so the additive contract namespace is
    # structurally invisible here. Without it a caller passing regime="cm_v2" would
    # be served the contract blob as though it were trade statistics. Unreachable
    # in production (regimes come from the regime detector), but the isolation
    # claim should hold by construction, not by which strings happen to occur.
    tm = v1_tm_buckets((getattr(mem, "tm_stats", None) or {}) if mem is not None else {})
    key = regime if (regime and regime in tm) else "_all"
    bucket = tm.get(key) or {}
    n = int(bucket.get("n", 0) or 0)
    sample_count = int(getattr(mem, "tm_sample_count", 0) or 0) if mem is not None else 0
    if n <= 0:
        return {"has_data": False, "n": 0, "regime": key,
                "cell_threshold": MIN_TM_SAMPLES, "tm_sample_count": sample_count}

    # Raw counts — ALWAYS shown (no gate).
    counts = {
        "tp1": int(bucket.get("tp1", 0)), "tp2": int(bucket.get("tp2", 0)),
        "tp3": int(bucket.get("tp3", 0)), "give_back": int(bucket.get("give_back", 0)),
        "tight_sl": int(bucket.get("tight_sl", 0)), "sub1_rr": int(bucket.get("sub1_rr", 0)),
    }
    out = {
        "has_data": True, "n": n, "regime": key,
        "cell_threshold": MIN_TM_SAMPLES, "below_cell_threshold": n < MIN_TM_SAMPLES,
        "tm_sample_count": sample_count, "counts": counts, "metrics": None,
    }
    if n < MIN_TM_SAMPLES:
        return out  # below threshold → raw counts only, no rates/scores

    mfe_n = int(bucket.get("mfe_r_n", 0)); mae_n = int(bucket.get("mae_r_n", 0))
    rr_n = int(bucket.get("planned_rr_tp1_n", 0)); real_n = int(bucket.get("realized_n", 0))
    out["metrics"] = {
        "avg_mfe_r": _avg(float(bucket.get("mfe_r_sum", 0.0)), mfe_n),
        "avg_mae_r": _avg(float(bucket.get("mae_r_sum", 0.0)), mae_n),
        "std_mfe_r": _std(float(bucket.get("mfe_r_sum", 0.0)), float(bucket.get("mfe_r_sumsq", 0.0)), mfe_n),
        "std_mae_r": _std(float(bucket.get("mae_r_sum", 0.0)), float(bucket.get("mae_r_sumsq", 0.0)), mae_n),
        "avg_mfe_atr": _avg(float(bucket.get("mfe_atr_sum", 0.0)), int(bucket.get("mfe_atr_n", 0))),
        "avg_mae_atr": _avg(float(bucket.get("mae_atr_sum", 0.0)), int(bucket.get("mae_atr_n", 0))),
        "avg_realized": _avg(float(bucket.get("realized_sum", 0.0)), real_n),
        "std_realized": _std(float(bucket.get("realized_sum", 0.0)), float(bucket.get("realized_sumsq", 0.0)), real_n),
        "avg_planned_rr_tp1": _avg(float(bucket.get("planned_rr_tp1_sum", 0.0)), rr_n),
        "sub1_rr_pct": _pct(counts["sub1_rr"], rr_n),
        "avg_bars_to_tp1": _avg(float(bucket.get("bars_to_tp1_sum", 0)), int(bucket.get("bars_to_tp1_n", 0))),
        "avg_bars_total": _avg(float(bucket.get("bars_total_sum", 0)), int(bucket.get("bars_total_n", 0))),
        "tp1_rate": _pct(counts["tp1"], n), "tp2_rate": _pct(counts["tp2"], n),
        "tp3_rate": _pct(counts["tp3"], n),
        "give_back_rate": _pct(counts["give_back"], counts["tp1"]),  # among TP1-banked
        "tight_sl_rate": _pct(counts["tight_sl"], n),
    }
    return out
