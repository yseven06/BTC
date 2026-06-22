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
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.ai_decision.signal_generator import BASE_ENGINE_WEIGHTS
from app.engines.base import SignalBias
from app.models.intelligence import CoinMemory, SignalSnapshot
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
