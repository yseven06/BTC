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

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backtesting import labels
from app.backtesting.trade_path import is_legacy_contradictory_live_sl
from app.services.trade_geometry import planned_rr
from app.engines.ai_decision.signal_generator import BASE_ENGINE_WEIGHTS
from app.engines.base import SignalBias
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


def get_effective_weights(
    regime: Optional[str],
    memory: Optional[CoinMemory],
) -> Dict[str, float]:
    """Final engine weights = base → regime tilt → coin-learned tilt → normalise.

    The learned layer is applied only when `memory` has enough resolved samples
    and stored adaptive_weights; otherwise just the regime-tilted base is used.
    """
    weights = regime_weights(regime)

    if (
        memory is not None
        and memory.total_signals >= MIN_SAMPLES_FOR_ADAPTIVE
        and memory.adaptive_weights
    ):
        # adaptive_weights are stored as a multiplier-vs-base ratio per engine;
        # combine multiplicatively with the regime-tilted weights.
        learned = memory.adaptive_weights
        combined = {
            k: weights[k] * float(learned.get(k, 1.0))
            for k in weights
        }
        weights = _normalize(combined)

    return weights


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


async def update_coin_memory(
    db: AsyncSession,
    signal: Signal,
    perf: SignalPerformance,
    symbol: str,
) -> None:
    """Fold a just-resolved signal into its (symbol, timeframe) memory cell.

    Safe to call inside the resolving transaction; wrapped by the caller so a
    memory-update failure never blocks the resolution itself.
    """
    timeframe = signal.timeframe.value if hasattr(signal.timeframe, "value") else str(signal.timeframe)
    outcome = perf.outcome

    # Only learn from genuinely resolved directional outcomes.
    if outcome not in (SignalOutcome.WIN, SignalOutcome.LOSS, SignalOutcome.BREAKEVEN,
                       SignalOutcome.EXPIRED, SignalOutcome.INVALIDATED):
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

    logger.info(
        "[CoinMemory] %s %s updated: total=%d wins=%d losses=%d label=%s",
        symbol, timeframe, mem.total_signals, mem.wins, mem.losses, label,
    )


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
    (never influences weights/decision)."""
    return bool(
        memory is not None
        and memory.total_signals >= MIN_SAMPLES_FOR_ADAPTIVE
        and memory.adaptive_weights
    )


async def load_effective_weights_meta(
    db: AsyncSession,
    symbol: str,
    timeframe: str,
    regime: Optional[str],
) -> Tuple[Dict[str, float], bool]:
    """Like load_effective_weights but ALSO reports whether the adaptive layer was
    applied, for A8-1 birth telemetry. The weights are computed by the SAME
    get_effective_weights call → BYTE-IDENTICAL to load_effective_weights; only an
    additive read-only flag is returned alongside."""
    res = await db.execute(
        select(CoinMemory).where(CoinMemory.symbol == symbol, CoinMemory.timeframe == timeframe)
    )
    mem = res.scalar_one_or_none()
    return get_effective_weights(regime, mem), adaptive_is_active(mem)


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
        mem.tm_stats = tm if tm else None
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
    tm = (getattr(mem, "tm_stats", None) or {}) if mem is not None else {}
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
