"""
Historical Similarity Engine.

Answers "what happened the last N times the setup looked like THIS one?" by
matching a signal's birth-snapshot against the snapshots of past *resolved*
signals and reporting how those turned out.

It is deliberately gated: with too few resolved samples it returns
`has_data=False` rather than a misleadingly precise number from a handful of
trades. As the platform accumulates resolved signals it activates on its own —
no flag to flip.

Similarity is a weighted feature distance over:
  • market regime          (categorical — same regime matters most)
  • direction              (bullish/bearish must match to be comparable)
  • birth confidence       (numeric)
  • volatility ratio       (numeric — was the market equally calm/wild?)
  • engine-bias fingerprint(how many of the 9 engines had the same directional
                            lean as in the query setup)

Kept pure-ish: it takes already-loaded candidate rows so it stays unit-testable
without a DB.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.base import SignalBias
from app.models.intelligence import SignalSnapshot
from app.models.signal import Signal, SignalOutcome, SignalPerformance

# Need at least this many similar matches before reporting a win rate.
MIN_SIMILAR_MATCHES = 8
# How many nearest neighbours to summarise.
TOP_K = 50
# Distance above which a candidate isn't "similar" enough to count.
MAX_DISTANCE = 1.0


def _bias_dir(bias: Any) -> Optional[str]:
    val = bias.value if isinstance(bias, SignalBias) else str(bias)
    if val in ("bullish", "strong_bullish"):
        return "bullish"
    if val in ("bearish", "strong_bearish"):
        return "bearish"
    return None


def _engine_fingerprint(engine_scores: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Map each engine to its directional lean ('bullish'/'bearish'/'neutral')."""
    out: Dict[str, str] = {}
    for name, sc in (engine_scores or {}).items():
        out[name] = _bias_dir(sc.get("bias")) or "neutral"
    return out


@dataclass
class _Candidate:
    direction: str
    regime: Optional[str]
    confidence: Optional[float]
    volatility_ratio: Optional[float]
    fingerprint: Dict[str, str]
    outcome: str  # win/loss/breakeven/...
    detail_label: Optional[str]


def _distance(
    q_regime: Optional[str], q_conf: Optional[float], q_vol: Optional[float],
    q_fp: Dict[str, str], cand: _Candidate,
) -> float:
    """Weighted feature distance in [0, ~1.5]; lower = more similar."""
    d = 0.0
    # Regime mismatch is the biggest penalty.
    if q_regime and cand.regime:
        d += 0.0 if q_regime == cand.regime else 0.5
    # Confidence difference (normalised by 100).
    if q_conf is not None and cand.confidence is not None:
        d += min(0.3, abs(q_conf - cand.confidence) / 100.0)
    # Volatility-ratio difference (clamped).
    if q_vol is not None and cand.volatility_ratio is not None:
        d += min(0.3, abs(q_vol - cand.volatility_ratio) / 3.0)
    # Engine fingerprint disagreement fraction.
    if q_fp and cand.fingerprint:
        keys = set(q_fp) & set(cand.fingerprint)
        if keys:
            disagree = sum(1 for k in keys if q_fp[k] != cand.fingerprint[k])
            d += 0.4 * (disagree / len(keys))
    return d


def summarize_similar(
    *,
    q_direction: str,
    q_regime: Optional[str],
    q_confidence: Optional[float],
    q_volatility_ratio: Optional[float],
    q_fingerprint: Dict[str, str],
    candidates: List[_Candidate],
) -> Dict[str, Any]:
    """Core matcher over already-loaded candidates. Pure function."""
    # Only compare against same-direction resolved setups.
    scored = []
    for c in candidates:
        if c.direction != q_direction:
            continue
        dist = _distance(q_regime, q_confidence, q_volatility_ratio, q_fingerprint, c)
        if dist <= MAX_DISTANCE:
            scored.append((dist, c))

    scored.sort(key=lambda x: x[0])
    nearest = [c for _, c in scored[:TOP_K]]

    if len(nearest) < MIN_SIMILAR_MATCHES:
        return {
            "has_data": False,
            "match_count": len(nearest),
            "needed": MIN_SIMILAR_MATCHES,
        }

    wins = sum(1 for c in nearest if c.outcome == SignalOutcome.WIN.value)
    losses = sum(1 for c in nearest if c.outcome in (SignalOutcome.LOSS.value, SignalOutcome.INVALIDATED.value))
    resolved = wins + losses

    # Most common detail label among the matches (the typical way this setup ends).
    label_counts: Dict[str, int] = {}
    for c in nearest:
        if c.detail_label:
            label_counts[c.detail_label] = label_counts.get(c.detail_label, 0) + 1
    common_label = max(label_counts, key=label_counts.get) if label_counts else None

    return {
        "has_data": True,
        "match_count": len(nearest),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / resolved * 100, 1) if resolved > 0 else None,
        "most_common_outcome": common_label,
    }


async def find_similar_setups(db: AsyncSession, signal_id) -> Dict[str, Any]:
    """Load the query signal's snapshot + a pool of resolved candidates and
    summarise how similar past setups resolved."""
    # Query snapshot + signal direction.
    q = (await db.execute(
        select(SignalSnapshot, Signal)
        .join(Signal, Signal.id == SignalSnapshot.signal_id)
        .where(SignalSnapshot.signal_id == signal_id)
    )).first()
    if q is None:
        return {"has_data": False, "match_count": 0, "needed": MIN_SIMILAR_MATCHES}
    snap, signal = q
    q_dir = signal.direction.value if hasattr(signal.direction, "value") else str(signal.direction)

    # Candidate pool: resolved signals (have a terminal performance) with a
    # snapshot, excluding the query signal itself.
    rows = (await db.execute(
        select(SignalSnapshot, Signal, SignalPerformance)
        .join(Signal, Signal.id == SignalSnapshot.signal_id)
        .join(SignalPerformance, SignalPerformance.signal_id == Signal.id)
        .where(Signal.id != signal_id)
        .where(SignalPerformance.outcome.in_([
            SignalOutcome.WIN, SignalOutcome.LOSS,
            SignalOutcome.BREAKEVEN, SignalOutcome.INVALIDATED, SignalOutcome.EXPIRED,
        ]))
        .limit(2000)
    )).all()

    candidates: List[_Candidate] = []
    for csnap, csig, cperf in rows:
        candidates.append(_Candidate(
            direction=csig.direction.value if hasattr(csig.direction, "value") else str(csig.direction),
            regime=csnap.regime,
            confidence=float(csnap.composite_confidence) if csnap.composite_confidence is not None else None,
            volatility_ratio=float(csnap.volatility_ratio) if csnap.volatility_ratio is not None else None,
            fingerprint=_engine_fingerprint(csnap.engine_scores),
            outcome=cperf.outcome.value,
            detail_label=cperf.detail_label,
        ))

    return summarize_similar(
        q_direction=q_dir,
        q_regime=snap.regime,
        q_confidence=float(snap.composite_confidence) if snap.composite_confidence is not None else None,
        q_volatility_ratio=float(snap.volatility_ratio) if snap.volatility_ratio is not None else None,
        q_fingerprint=_engine_fingerprint(snap.engine_scores),
        candidates=candidates,
    )
