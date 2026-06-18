"""
TradeMinds AI – Report Routes

PDF export endpoints for signals and performance summaries.
Pro tier or above required.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.signal import Signal, SignalOutcome, SignalPerformance
from app.models.user import User
from app.reports.pdf_generator import (
    generate_performance_pdf, generate_signal_pdf,
)
from app.subscriptions.gating import require_feature

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/signal/{signal_id}.pdf",
    summary="Download PDF report for a single signal (Pro+)",
)
async def signal_pdf(
    signal_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _gate = Depends(require_feature("can_view_engine_details")),
) -> Response:
    res = await db.execute(
        select(Signal).options(joinedload(Signal.asset)).where(Signal.id == signal_id)
    )
    sig = res.unique().scalar_one_or_none()
    if sig is None:
        raise HTTPException(status_code=404, detail="Sinyal bulunamadı.")

    payload: Dict[str, Any] = {
        "symbol":            sig.asset.symbol if sig.asset else "—",
        "asset_name":        sig.asset.name if sig.asset else "",
        "timeframe":         sig.timeframe.value if hasattr(sig.timeframe, "value") else str(sig.timeframe),
        "direction":         sig.direction.value if hasattr(sig.direction, "value") else str(sig.direction),
        "signal_type":       sig.signal_type.value if hasattr(sig.signal_type, "value") else str(sig.signal_type),
        "risk_level":        sig.risk_level.value if hasattr(sig.risk_level, "value") else str(sig.risk_level),
        "confidence_score":  float(sig.confidence_score or 0),
        "probability_score": float(sig.probability_score or 0),
        "risk_score":        float(sig.risk_score or 0),
        "entry_zone_low":    sig.entry_zone_low,
        "entry_zone_high":   sig.entry_zone_high,
        "stop_loss":         sig.stop_loss,
        "tp1":               sig.tp1,
        "tp2":               sig.tp2,
        "tp3":               sig.tp3,
        "explanation_tr":    sig.explanation_tr,
        "engines_data":      sig.engines_data,
        "generated_at":      sig.generated_at.isoformat() if sig.generated_at else None,
    }

    pdf_bytes = generate_signal_pdf(payload)
    filename = f"trademinds-signal-{payload['symbol']}-{signal_id.hex[:8]}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/performance.pdf",
    summary="Download overall performance summary as PDF (Pro+)",
)
async def performance_pdf(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _gate = Depends(require_feature("can_view_strategy_lab")),
) -> Response:
    # Compute the same stats as /signals/performance, condensed.
    res = await db.execute(
        select(SignalPerformance)
        .join(Signal)
        .options(joinedload(SignalPerformance.signal).joinedload(Signal.asset))
    )
    perfs = res.scalars().all()

    total      = len(perfs)
    wins       = sum(1 for p in perfs if p.outcome == SignalOutcome.WIN)
    losses     = sum(1 for p in perfs if p.outcome == SignalOutcome.LOSS)
    breakeven  = sum(1 for p in perfs if p.outcome == SignalOutcome.BREAKEVEN)
    active     = sum(1 for p in perfs if p.outcome == SignalOutcome.ACTIVE)
    resolved   = wins + losses + breakeven
    win_rate   = (wins / resolved * 100) if resolved > 0 else 0.0
    returns    = [float(p.actual_return) for p in perfs if p.actual_return is not None]
    avg_return = (sum(returns) / len(returns)) if returns else None
    tp1_hits   = sum(1 for p in perfs if p.hit_tp1)
    tp2_hits   = sum(1 for p in perfs if p.hit_tp2)

    stats = {
        "total_signals":   total,
        "win_count":       wins,
        "loss_count":      losses,
        "breakeven_count": breakeven,
        "active_count":    active,
        "win_rate":        round(win_rate, 1),
        "average_return":  round(avg_return, 2) if avg_return is not None else None,
        "tp1_hit_rate":    round(tp1_hits / total * 100, 1) if total > 0 else 0,
        "tp2_hit_rate":    round(tp2_hits / total * 100, 1) if total > 0 else 0,
    }

    # Per-symbol summary
    by_sym: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"total": 0, "wins": 0, "resolved": 0, "conf_sum": 0.0})
    for p in perfs:
        if not p.signal or not p.signal.asset:
            continue
        sym = p.signal.asset.symbol
        by_sym[sym]["total"] += 1
        by_sym[sym]["conf_sum"] += float(p.signal.confidence_score or 0)
        if p.outcome == SignalOutcome.WIN:
            by_sym[sym]["wins"] += 1
            by_sym[sym]["resolved"] += 1
        elif p.outcome in (SignalOutcome.LOSS, SignalOutcome.BREAKEVEN):
            by_sym[sym]["resolved"] += 1

    symbols: List[Dict[str, Any]] = []
    for sym, d in by_sym.items():
        wr = (d["wins"] / d["resolved"] * 100) if d["resolved"] > 0 else 0.0
        avg_conf = d["conf_sum"] / d["total"] if d["total"] > 0 else 0
        symbols.append({
            "symbol":        sym,
            "total":         d["total"],
            "win_rate":      round(wr, 1),
            "quality_score": round(avg_conf / 10, 1),
        })
    symbols.sort(key=lambda x: x["total"], reverse=True)

    pdf_bytes = generate_performance_pdf(stats, symbols)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="trademinds-performance.pdf"'},
    )
