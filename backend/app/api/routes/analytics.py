"""
TradeMinds AI – Analytics Routes

Strategy Lab: hour/day/volatility heatmaps with WoE scoring
Symbol Analysis: per-symbol win rates, OB vs FVG breakdown
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models.asset import Asset
from app.models.signal import Signal, SignalOutcome, SignalPerformance
from app.subscriptions.gating import (
    SubscriptionTier, get_user_tier_optional,
)

logger = logging.getLogger(__name__)
router = APIRouter()

DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


def _outcome_counts(perfs: list) -> Dict[str, int]:
    wins      = sum(1 for p in perfs if p.outcome == SignalOutcome.WIN)
    losses    = sum(1 for p in perfs if p.outcome == SignalOutcome.LOSS)
    breakeven = sum(1 for p in perfs if p.outcome == SignalOutcome.BREAKEVEN)
    resolved  = wins + losses + breakeven
    return {"wins": wins, "losses": losses, "breakeven": breakeven, "resolved": resolved}


def _win_rate(wins: int, resolved: int) -> float:
    return round(wins / resolved * 100, 1) if resolved > 0 else 0.0


def _htf_type(engines_data: Any) -> str:
    """Derive 'OB' or 'FVG' from engine results.
    engines_data may be a dict {engine_name: result} or a list of result dicts."""
    if not engines_data:
        return "UNKNOWN"

    smc: Dict[str, Any] = {}
    if isinstance(engines_data, dict):
        smc = engines_data.get("smart_money_concepts", {}) or {}
    elif isinstance(engines_data, list):
        for e in engines_data:
            if isinstance(e, dict) and (e.get("engine_name") == "smart_money_concepts" or e.get("name") == "smart_money_concepts"):
                smc = e
                break

    findings: List[str] = smc.get("key_findings", []) if isinstance(smc, dict) else []
    for f in findings:
        fl = str(f).lower()
        if "order block" in fl:
            return "OB"
        if "fair value" in fl or "fvg" in fl:
            return "FVG"
    return "OTHER"


@router.get("/strategy-lab", summary="Hour/day heatmap with WoE scoring")
async def strategy_lab(
    db: AsyncSession = Depends(get_db),
    tier: SubscriptionTier = Depends(get_user_tier_optional),
) -> Dict[str, Any]:
    if tier == SubscriptionTier.FREE:
        return {"by_hour": [], "by_day": [], "by_direction": [], "by_risk": [],
                "total_signals": 0, "locked": True}
    """
    Returns aggregated signal performance grouped by:
    - hour of day (0-23)
    - day of week (0=Mon … 6=Sun)
    - signal direction
    - risk level
    """
    result = await db.execute(
        select(SignalPerformance)
        .join(Signal)
        .options(joinedload(SignalPerformance.signal).joinedload(Signal.asset))
    )
    perfs = result.scalars().all()

    # ── By Hour ──────────────────────────────────────────────────────────────
    by_hour: Dict[int, list] = defaultdict(list)
    by_day:  Dict[int, list] = defaultdict(list)
    by_direction: Dict[str, list] = defaultdict(list)
    by_risk: Dict[str, list] = defaultdict(list)

    for p in perfs:
        sig = p.signal
        if sig is None:
            continue
        ts = sig.generated_at
        by_hour[ts.hour].append(p)
        by_day[ts.weekday()].append(p)
        by_direction[sig.direction.value].append(p)
        by_risk[sig.risk_level.value].append(p)

    hour_data = []
    for h in range(24):
        items = by_hour[h]
        c = _outcome_counts(items)
        hour_data.append({
            "hour": h,
            "label": f"{h:02d}:00",
            "total": len(items),
            "wins": c["wins"],
            "losses": c["losses"],
            "breakeven": c["breakeven"],
            "win_rate": _win_rate(c["wins"], c["resolved"]),
            "avg_confidence": round(
                sum(p.signal.confidence_score for p in items) / len(items), 1
            ) if items else 0.0,
        })

    day_data = []
    for d in range(7):
        items = by_day[d]
        c = _outcome_counts(items)
        day_data.append({
            "day": d,
            "label": DAYS[d],
            "total": len(items),
            "wins": c["wins"],
            "losses": c["losses"],
            "breakeven": c["breakeven"],
            "win_rate": _win_rate(c["wins"], c["resolved"]),
            "avg_confidence": round(
                sum(p.signal.confidence_score for p in items) / len(items), 1
            ) if items else 0.0,
        })

    direction_data = []
    for direction, items in by_direction.items():
        c = _outcome_counts(items)
        direction_data.append({
            "direction": direction,
            "total": len(items),
            "wins": c["wins"],
            "win_rate": _win_rate(c["wins"], c["resolved"]),
            "avg_confidence": round(
                sum(p.signal.confidence_score for p in items) / len(items), 1
            ) if items else 0.0,
        })

    risk_data = []
    for risk, items in by_risk.items():
        c = _outcome_counts(items)
        risk_data.append({
            "risk_level": risk,
            "total": len(items),
            "wins": c["wins"],
            "win_rate": _win_rate(c["wins"], c["resolved"]),
        })

    return {
        "by_hour": hour_data,
        "by_day": day_data,
        "by_direction": direction_data,
        "by_risk": risk_data,
        "total_signals": len(perfs),
    }


@router.get("/symbol-analysis", summary="Per-symbol win rates and HTF type breakdown")
async def symbol_analysis(
    db: AsyncSession = Depends(get_db),
    tier: SubscriptionTier = Depends(get_user_tier_optional),
) -> Dict[str, Any]:
    if tier == SubscriptionTier.FREE:
        return {"symbols": [], "total_symbols": 0, "locked": True}
    """
    Returns per-symbol statistics:
    - win rate, avg R:R, confidence
    - direction split (bullish vs bearish)
    - HTF type split (OB vs FVG)
    """
    result = await db.execute(
        select(SignalPerformance)
        .join(Signal)
        .options(
            joinedload(SignalPerformance.signal).joinedload(Signal.asset)
        )
    )
    perfs = result.scalars().all()

    # Also fetch all signals (active ones that have no performance record yet)
    all_sigs_res = await db.execute(
        select(Signal).options(joinedload(Signal.asset))
    )
    all_signals = all_sigs_res.unique().scalars().all()

    # Group performance by symbol
    by_symbol: Dict[str, Dict[str, Any]] = {}

    for sig in all_signals:
        if sig.asset is None:
            continue
        sym = sig.asset.symbol
        if sym not in by_symbol:
            by_symbol[sym] = {
                "symbol": sym,
                "name": sig.asset.name,
                "asset_type": sig.asset.asset_type.value,
                "total": 0,
                "wins": 0,
                "losses": 0,
                "breakeven": 0,
                "active": 0,
                "confidences": [],
                "directions": defaultdict(int),
                "htf_types": defaultdict(int),
            }
        d = by_symbol[sym]
        d["total"] += 1
        d["confidences"].append(sig.confidence_score)
        d["directions"][sig.direction.value] += 1
        htf = _htf_type(sig.engines_data)
        d["htf_types"][htf] += 1

    for p in perfs:
        if p.signal is None or p.signal.asset is None:
            continue
        sym = p.signal.asset.symbol
        if sym not in by_symbol:
            continue
        if p.outcome == SignalOutcome.WIN:
            by_symbol[sym]["wins"] += 1
        elif p.outcome == SignalOutcome.LOSS:
            by_symbol[sym]["losses"] += 1
        elif p.outcome == SignalOutcome.BREAKEVEN:
            by_symbol[sym]["breakeven"] += 1
        elif p.outcome == SignalOutcome.ACTIVE:
            by_symbol[sym]["active"] += 1

    symbols_out = []
    for sym, d in by_symbol.items():
        resolved = d["wins"] + d["losses"] + d["breakeven"]
        avg_conf = round(sum(d["confidences"]) / len(d["confidences"]), 1) if d["confidences"] else 0.0
        symbols_out.append({
            "symbol": sym,
            "name": d["name"],
            "asset_type": d["asset_type"],
            "total": d["total"],
            "wins": d["wins"],
            "losses": d["losses"],
            "breakeven": d["breakeven"],
            "active": d["active"],
            "win_rate": _win_rate(d["wins"], resolved),
            "avg_confidence": avg_conf,
            "quality_score": round(avg_conf / 10, 1),
            "directions": dict(d["directions"]),
            "htf_types": dict(d["htf_types"]),
        })

    symbols_out.sort(key=lambda x: x["total"], reverse=True)

    return {
        "symbols": symbols_out,
        "total_symbols": len(symbols_out),
    }
