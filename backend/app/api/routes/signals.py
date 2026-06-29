"""
Signal API routes.

Provides endpoints for listing active signals, viewing signal details,
history, performance metrics, and triggering signal generation.
"""

import logging
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.asset import Asset
from app.models.signal import Signal, SignalOutcome, SignalPerformance, SignalType, Direction, RiskLevel
from app.models.intelligence import SignalSnapshot, CoinMemory
from app.models.user import User
from app.backtesting import labels as outcome_labels
from app.backtesting import lifecycle
from app.schemas.signal import (
    SignalDetailResponse,
    SignalHistoryStats,
    SignalListResponse,
    SignalPerformanceResponse,
    SignalPerformanceSummary,
    SignalResponse,
    BacktestRequest,
    BacktestResponse,
)
from app.collectors.binance_collector import BinanceCollector
from app.collectors.yahoo_collector import YahooCollector
from app.engines.ai_decision.engine import AIDecisionEngine
from app.backtesting.engine import BacktestEngine
from app.backtesting.tracker import track_and_resolve_active_signals
from app.subscriptions.gating import (
    TIER_LIMITS, SubscriptionTier, get_user_tier_optional, require_feature,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "",
    response_model=SignalListResponse,
    summary="List active signals",
)
async def list_signals(
    asset_id: Optional[UUID] = Query(None, description="Filter by asset ID."),
    direction: Optional[str] = Query(None, description="Filter by direction (bullish, bearish, neutral)."),
    signal_type: Optional[str] = Query(None, description="Filter by signal type."),
    timeframe: Optional[str] = Query(None, description="Filter by timeframe."),
    only_actionable: bool = Query(True, description="If True, hide HOLD signals (only BUY/SELL shown)."),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=300),
    tier: SubscriptionTier = Depends(get_user_tier_optional),
    db: AsyncSession = Depends(get_db),
) -> SignalListResponse:
    """
    List active trading signals with optional filters and pagination.
    Free users are limited to the most recent N signals (daily_signal_limit).
    """
    # ── Tier-based signal limit ──
    free_cap = TIER_LIMITS[tier].daily_signal_limit
    if free_cap > 0:
        # Cap how many they can ask for and how many we surface in total.
        page_size = min(page_size, free_cap)
    query = select(Signal).where(Signal.is_active == True)

    if asset_id is not None:
        query = query.where(Signal.asset_id == asset_id)
    if direction is not None:
        query = query.where(Signal.direction == direction)
    if signal_type is not None:
        query = query.where(Signal.signal_type == signal_type)
    if timeframe is not None:
        query = query.where(Signal.timeframe == timeframe)
    # Hide HOLD by default — user wants actionable BUY/SELL signals
    if only_actionable:
        query = query.where(Signal.signal_type != SignalType.HOLD)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Free users see at most `free_cap` total (most recent N).
    if free_cap > 0:
        total = min(total, free_cap)

    # Paginate — joinedload asset + performance so frontend can show outcome badges
    offset = (page - 1) * page_size
    query = (
        query
        .options(joinedload(Signal.asset), joinedload(Signal.performance))
        .order_by(Signal.generated_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(query)
    signals = result.unique().scalars().all()

    total_pages = max(1, (total + page_size - 1) // page_size)

    def _to_resp(s: Signal) -> SignalResponse:
        d = SignalResponse.model_validate(s)
        perf = s.performance
        d.outcome = perf.outcome.value if perf else "active"
        if perf:
            d.hit_tp1 = perf.hit_tp1
            d.hit_tp2 = perf.hit_tp2
            d.hit_tp3 = perf.hit_tp3
            d.tp1_hit_at = perf.tp1_hit_at
            d.tp2_hit_at = perf.tp2_hit_at
            d.tp3_hit_at = perf.tp3_hit_at
            d.detail_label = perf.detail_label
            d.mfe_pct = float(perf.mfe_pct) if perf.mfe_pct is not None else None
            d.bars_to_outcome = perf.bars_to_outcome
        return d

    return SignalListResponse(
        items=[_to_resp(s) for s in signals],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_previous=page > 1,
    )


def _hist_to_resp(s: Signal) -> SignalResponse:
    d = SignalResponse.model_validate(s)
    perf = s.performance
    d.outcome = perf.outcome.value if perf else "active"
    if perf:
        d.actual_return = float(perf.actual_return) if perf.actual_return is not None else None
        d.max_drawdown = float(perf.max_drawdown) if perf.max_drawdown is not None else None
        d.hit_tp1 = perf.hit_tp1
        d.hit_tp2 = perf.hit_tp2
        d.hit_tp3 = perf.hit_tp3
        d.tp1_hit_at = perf.tp1_hit_at
        d.tp2_hit_at = perf.tp2_hit_at
        d.tp3_hit_at = perf.tp3_hit_at
        d.closed_at = perf.closed_at
        d.detail_label = perf.detail_label
        d.mfe_pct = float(perf.mfe_pct) if perf.mfe_pct is not None else None
        d.bars_to_outcome = perf.bars_to_outcome
    return d


@router.get(
    "/history",
    response_model=SignalListResponse,
    summary="List historical signals with filters",
)
async def signal_history(
    asset_id: Optional[UUID] = Query(None),
    symbol: Optional[str] = Query(None, description="Filter by exact asset symbol (e.g. ALGOUSDT)."),
    market: Optional[str] = Query(None, description="crypto or stock"),
    signal_type: Optional[str] = Query(None),
    outcome: Optional[str] = Query(None, description="win, loss, breakeven, expired, active"),
    min_confidence: Optional[float] = Query(None, ge=0, le=100),
    max_confidence: Optional[float] = Query(None, ge=0, le=100),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    only_resolved: bool = Query(False, description="If True, only show closed signals (exclude active)."),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> SignalListResponse:
    """
    List all signals including inactive/expired ones, with rich filtering
    so users can audit how past signals actually played out.
    """
    query = select(Signal).join(Asset).outerjoin(SignalPerformance)

    if asset_id is not None:
        query = query.where(Signal.asset_id == asset_id)
    if symbol is not None:
        query = query.where(Asset.symbol == symbol.upper())
    if market is not None:
        query = query.where(Asset.asset_type == market)
    if signal_type is not None:
        query = query.where(Signal.signal_type == signal_type)
    if min_confidence is not None:
        query = query.where(Signal.confidence_score >= min_confidence)
    if max_confidence is not None:
        query = query.where(Signal.confidence_score <= max_confidence)
    if date_from is not None:
        query = query.where(Signal.generated_at >= date_from)
    if date_to is not None:
        query = query.where(Signal.generated_at <= date_to)
    if outcome is not None:
        query = query.where(SignalPerformance.outcome == outcome)
    elif only_resolved:
        query = query.where(SignalPerformance.outcome != SignalOutcome.ACTIVE)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    # "Kapanan Sinyaller" reads as a list of closes, not a list of scans —
    # sorting by generated_at put a signal made hours ago but resolved just
    # now below ones generated more recently but still open or resolved
    # earlier. Sort by when it actually closed (falling back to
    # generated_at for the rare still-active row that slips through here).
    sort_key = func.coalesce(SignalPerformance.closed_at, Signal.generated_at)
    query = (
        query
        .options(joinedload(Signal.asset), joinedload(Signal.performance))
        .order_by(sort_key.desc())
        .offset(offset).limit(page_size)
    )
    result = await db.execute(query)
    signals = result.unique().scalars().all()

    total_pages = max(1, (total + page_size - 1) // page_size)

    return SignalListResponse(
        items=[_hist_to_resp(s) for s in signals],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_previous=page > 1,
    )


@router.get(
    "/history/stats",
    response_model=SignalHistoryStats,
    summary="Summary statistics for the Signal History panel",
)
async def signal_history_stats(
    market: Optional[str] = Query(None, description="crypto or stock"),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> SignalHistoryStats:
    """
    Aggregate stats over closed signals: win/TP/SL rates, profit factor,
    best/worst signal. Powers the summary cards on the Signal History page.

    Computed entirely in SQL (COUNT/SUM/AVG + ORDER BY ... LIMIT 1) instead of
    hydrating every SignalPerformance+Signal+Asset row into Python and
    looping — with thousands of resolved signals that previously took 6+
    seconds and could exceed the frontend's request timeout, silently
    presenting as "no history" even though the data existed.
    """
    from sqlalchemy import case

    def _filters(q):
        if market is not None:
            q = q.where(Asset.asset_type == market)
        if date_from is not None:
            q = q.where(Signal.generated_at >= date_from)
        if date_to is not None:
            q = q.where(Signal.generated_at <= date_to)
        return q

    agg_query = _filters(
        select(
            func.count().label("total"),
            func.sum(case((SignalPerformance.outcome == SignalOutcome.WIN, 1), else_=0)).label("win"),
            func.sum(case((SignalPerformance.outcome == SignalOutcome.LOSS, 1), else_=0)).label("loss"),
            func.sum(case((SignalPerformance.outcome == SignalOutcome.BREAKEVEN, 1), else_=0)).label("breakeven"),
            func.sum(case((SignalPerformance.outcome == SignalOutcome.EXPIRED, 1), else_=0)).label("expired"),
            func.sum(case((SignalPerformance.outcome == SignalOutcome.INVALIDATED, 1), else_=0)).label("invalidated"),
            func.sum(case((SignalPerformance.outcome == SignalOutcome.ACTIVE, 1), else_=0)).label("active"),
            # Only count a TP touch on a signal that has actually closed.
            # An ACTIVE signal can already show hit_tp1/2/3=True (the price
            # touched that level while the position is still open) — without
            # this guard, tp_hits summed over *all* signals (mostly active)
            # while tp_hit_rate divided by only the handful that are closed,
            # producing nonsense rates over 100%.
            func.sum(case(
                (
                    (SignalPerformance.outcome != SignalOutcome.ACTIVE)
                    & ((SignalPerformance.hit_tp1 == True) | (SignalPerformance.hit_tp2 == True) | (SignalPerformance.hit_tp3 == True)),
                    1,
                ),
                else_=0,
            )).label("tp_hits"),
            func.avg(SignalPerformance.actual_return).label("avg_return"),
            func.sum(case((SignalPerformance.actual_return > 0, SignalPerformance.actual_return), else_=0)).label("gross_profit"),
            func.sum(case((SignalPerformance.actual_return < 0, SignalPerformance.actual_return), else_=0)).label("gross_loss_neg"),
        )
        .select_from(SignalPerformance)
        .join(Signal, SignalPerformance.signal_id == Signal.id)
        .join(Asset, Signal.asset_id == Asset.id)
    )
    row = (await db.execute(agg_query)).one()

    total = row.total or 0
    if total == 0:
        return SignalHistoryStats()

    win = row.win or 0
    loss = row.loss or 0
    breakeven = row.breakeven or 0
    expired = row.expired or 0
    invalidated = row.invalidated or 0
    active = row.active or 0
    closed = total - active
    resolved = win + loss + breakeven

    win_rate = round(win / resolved * 100, 2) if resolved > 0 else 0.0
    sl_rate = round(loss / resolved * 100, 2) if resolved > 0 else 0.0
    # TP hits are a price-action fact (the candle touched the TP level) —
    # they can happen on a signal that later got INVALIDATED by a reversal
    # before "officially" resolving as a win. Dividing by `resolved`
    # (win+loss+breakeven only) silently zeroed this out whenever every
    # closed signal happened to be invalidated/expired, even though a TP
    # had genuinely been hit. Divide by all closed signals instead.
    tp_hit_rate = round((row.tp_hits or 0) / closed * 100, 2) if closed > 0 else 0.0
    avg_return = round(float(row.avg_return), 4) if row.avg_return is not None else None

    gross_profit = float(row.gross_profit or 0)
    gross_loss = abs(float(row.gross_loss_neg or 0))
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else None

    best_base = _filters(
        select(SignalPerformance, Asset.symbol)
        .select_from(SignalPerformance)
        .join(Signal, SignalPerformance.signal_id == Signal.id)
        .join(Asset, Signal.asset_id == Asset.id)
        .where(SignalPerformance.actual_return.isnot(None))
    )

    def _to_dict(perf: SignalPerformance, symbol: str) -> Dict[str, Any]:
        return {
            "symbol": symbol,
            "return": round(float(perf.actual_return), 2),
            "outcome": perf.outcome.value,
            "closed_at": perf.closed_at.isoformat() if perf.closed_at else None,
        }

    best_row = (await db.execute(best_base.order_by(SignalPerformance.actual_return.desc()).limit(1))).first()
    worst_row = (await db.execute(best_base.order_by(SignalPerformance.actual_return.asc()).limit(1))).first()
    best_signal = _to_dict(best_row[0], best_row[1]) if best_row else None
    worst_signal = _to_dict(worst_row[0], worst_row[1]) if worst_row else None

    return SignalHistoryStats(
        total_signals=total,
        closed_count=closed,
        win_count=win,
        loss_count=loss,
        breakeven_count=breakeven,
        expired_count=expired,
        invalidated_count=invalidated,
        active_count=active,
        win_rate=win_rate,
        tp_hit_rate=tp_hit_rate,
        sl_rate=sl_rate,
        average_return=avg_return,
        profit_factor=profit_factor,
        best_signal=best_signal,
        worst_signal=worst_signal,
    )


@router.get(
    "/performance",
    response_model=SignalPerformanceSummary,
    summary="Get aggregate signal performance",
)
async def signal_performance_summary(
    asset_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> SignalPerformanceSummary:
    """
    Return aggregate performance statistics across all resolved signals,
    including strategy-specific and asset-specific performance breakdowns.
    """
    query = (
        select(SignalPerformance)
        .join(Signal)
        .join(Asset)
        .options(joinedload(SignalPerformance.signal).joinedload(Signal.asset))
    )

    if asset_id is not None:
        query = query.where(Signal.asset_id == asset_id)

    result = await db.execute(query)
    performances = result.scalars().all()

    if not performances:
        return SignalPerformanceSummary()

    total = len(performances)
    win = sum(1 for p in performances if p.outcome == SignalOutcome.WIN)
    loss = sum(1 for p in performances if p.outcome == SignalOutcome.LOSS)
    breakeven = sum(1 for p in performances if p.outcome == SignalOutcome.BREAKEVEN)
    active = sum(1 for p in performances if p.outcome == SignalOutcome.ACTIVE)
    expired = sum(1 for p in performances if p.outcome == SignalOutcome.EXPIRED)

    resolved = win + loss + breakeven
    win_rate = (win / resolved * 100) if resolved > 0 else 0.0

    returns = [float(p.actual_return) for p in performances if p.actual_return is not None]
    avg_return = sum(returns) / len(returns) if returns else None

    drawdowns = [float(p.max_drawdown) for p in performances if p.max_drawdown is not None]
    avg_drawdown = sum(drawdowns) / len(drawdowns) if drawdowns else None

    tp1_hits = sum(1 for p in performances if p.hit_tp1)
    tp2_hits = sum(1 for p in performances if p.hit_tp2)
    tp3_hits = sum(1 for p in performances if p.hit_tp3)

    # 1. Win rate by direction
    win_rate_by_direction = {}
    for d in ["bullish", "bearish", "neutral"]:
        d_perfs = [p for p in performances if p.signal.direction.value == d]
        d_res = sum(1 for p in d_perfs if p.outcome in [SignalOutcome.WIN, SignalOutcome.LOSS, SignalOutcome.BREAKEVEN])
        d_win = sum(1 for p in d_perfs if p.outcome == SignalOutcome.WIN)
        win_rate_by_direction[d] = round((d_win / d_res * 100.0), 2) if d_res > 0 else 0.0

    # 2. Win rate by asset
    win_rate_by_asset = {}
    assets_set = set(p.signal.asset.symbol for p in performances)
    for sym in assets_set:
        a_perfs = [p for p in performances if p.signal.asset.symbol == sym]
        a_res = sum(1 for p in a_perfs if p.outcome in [SignalOutcome.WIN, SignalOutcome.LOSS, SignalOutcome.BREAKEVEN])
        a_win = sum(1 for p in a_perfs if p.outcome == SignalOutcome.WIN)
        win_rate_by_asset[sym] = round((a_win / a_res * 100.0), 2) if a_res > 0 else 0.0

    # 3. Performance by signal type
    performance_by_signal_type = {}
    for st in ["strong_buy", "buy", "sell", "strong_sell"]:
        st_perfs = [p for p in performances if p.signal.signal_type.value == st]
        st_res = sum(1 for p in st_perfs if p.outcome in [SignalOutcome.WIN, SignalOutcome.LOSS, SignalOutcome.BREAKEVEN])
        st_win = sum(1 for p in st_perfs if p.outcome == SignalOutcome.WIN)
        st_avg_ret = sum(float(p.actual_return) for p in st_perfs if p.actual_return is not None) / len([p for p in st_perfs if p.actual_return is not None]) if [p for p in st_perfs if p.actual_return is not None] else 0.0
        performance_by_signal_type[st] = {
            "total": len(st_perfs),
            "win_rate": round((st_win / st_res * 100.0), 2) if st_res > 0 else 0.0,
            "average_return": round(float(st_avg_ret), 4)
        }

    # 4. Historical equity curve (compiles a hypothetical 10% risk curve chronologically)
    sorted_perfs = sorted(performances, key=lambda x: x.closed_at or x.signal.generated_at)
    equity = 10000.0
    historical_equity_curve = [{"time": "Start", "capital": equity}]
    for p in sorted_perfs:
        if p.actual_return is not None:
            trade_return = float(p.actual_return) / 100.0
            impact = equity * 0.1 * trade_return
            equity += impact
            closed_time = (p.closed_at or p.signal.generated_at).isoformat()
            historical_equity_curve.append({
                "time": closed_time,
                "capital": round(equity, 2)
            })

    # 5. Drawdown analysis
    max_dd = max(drawdowns) if drawdowns else 0.0
    drawdown_analysis = {
        "max_drawdown": round(max_dd, 2),
        "average_drawdown": round(avg_drawdown, 2) if avg_drawdown is not None else 0.0
    }

    return SignalPerformanceSummary(
        total_signals=total,
        win_count=win,
        loss_count=loss,
        breakeven_count=breakeven,
        active_count=active,
        expired_count=expired,
        win_rate=round(win_rate, 2),
        average_return=round(avg_return, 4) if avg_return is not None else None,
        average_drawdown=round(avg_drawdown, 4) if avg_drawdown is not None else None,
        tp1_hit_rate=round(tp1_hits / total * 100, 2) if total > 0 else 0.0,
        tp2_hit_rate=round(tp2_hits / total * 100, 2) if total > 0 else 0.0,
        tp3_hit_rate=round(tp3_hits / total * 100, 2) if total > 0 else 0.0,
        win_rate_by_direction=win_rate_by_direction,
        win_rate_by_asset=win_rate_by_asset,
        performance_by_signal_type=performance_by_signal_type,
        historical_equity_curve=historical_equity_curve,
        drawdown_analysis=drawdown_analysis,
    )


@router.get(
    "/lifecycle/metrics",
    summary="Lifecycle observability metrics (read-only)",
)
async def lifecycle_metrics(
    days: int = Query(30, ge=1, le=365, description="Look-back window in days."),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Read-only Lifecycle observability metrics derived from
    signal_status_history + the prevented-flip-flop counter.

    Behavioural metrics (transition counts, durations, flip-flops) are reliable
    within days. Accuracy metrics (invalidating/approaching correctness) need
    enough RESOLVED signals to be meaningful and may be sparse early — they are
    reported with their own sample sizes so they're never read as more certain
    than they are. Purely observational: writes nothing.
    """
    win = f"now() - interval '{int(days)} days'"

    # 1) Event counts by kind.
    kind_rows = (await db.execute(text(
        f"SELECT kind, count(*) c FROM signal_status_history WHERE created_at > {win} GROUP BY kind"
    ))).fetchall()
    event_counts = {r[0]: r[1] for r in kind_rows}

    # 2) Transition matrix (applied transitions only).
    matrix_rows = (await db.execute(text(
        f"""SELECT from_status, to_status, count(*) c FROM signal_status_history
            WHERE kind='transition' AND created_at > {win}
            GROUP BY 1,2 ORDER BY c DESC"""
    ))).fetchall()
    transition_matrix = [
        {"from": r[0], "to": r[1], "count": r[2]} for r in matrix_rows
    ]

    # 3) Prevented flip-flops (the cheap counter) + actual immediate reversals.
    flip_prevented = (await db.execute(text(
        "SELECT COALESCE(SUM(flipflop_prevented_count),0) FROM signals"
    ))).scalar()
    actual_flipflops = (await db.execute(text(
        f"""WITH t AS (
              SELECT signal_id, from_status, to_status,
                     LAG(from_status) OVER w AS prev_from,
                     LAG(to_status)   OVER w AS prev_to
              FROM signal_status_history
              WHERE kind='transition' AND created_at > {win}
              WINDOW w AS (PARTITION BY signal_id ORDER BY created_at)
            )
            SELECT count(*) FROM t WHERE to_status = prev_from AND from_status = prev_to"""
    ))).scalar() or 0
    prevented = int(flip_prevented or 0)
    stability_ratio = (
        round(prevented / (prevented + actual_flipflops), 3)
        if (prevented + actual_flipflops) > 0 else None
    )

    # 4) Average time spent in each state (seconds), from consecutive events.
    dur_rows = (await db.execute(text(
        f"""WITH ev AS (
              SELECT signal_id, from_status, created_at,
                     LAG(created_at) OVER (PARTITION BY signal_id ORDER BY created_at) AS prev_ts
              FROM signal_status_history WHERE created_at > {win}
            )
            SELECT from_status,
                   round(avg(extract(epoch from (created_at - prev_ts)))::numeric, 1) avg_s,
                   count(*) n
            FROM ev WHERE prev_ts IS NOT NULL AND from_status IS NOT NULL
            GROUP BY 1"""
    ))).fetchall()
    avg_state_duration_sec = {r[0]: {"avg_seconds": float(r[1]), "samples": r[2]} for r in dur_rows}

    # 5) Accuracy — needs resolved outcomes; reported with sample sizes.
    # NB: the signal_outcome PG enum stores UPPERCASE labels (WIN/LOSS/...),
    # so normalise keys to lower-case before reading them.
    def _acc_block(rows):
        d = {str(r[0]).lower(): r[1] for r in rows}
        wins = d.get("win", 0)
        losses = d.get("loss", 0) + d.get("invalidated", 0)
        resolved = wins + losses
        return {"win": wins, "loss": losses, "resolved": resolved, "raw": d}

    inv_rows = (await db.execute(text(
        f"""SELECT p.outcome, count(*) c
            FROM (SELECT DISTINCT signal_id FROM signal_status_history WHERE to_status='invalidating') h
            JOIN signal_performances p ON p.signal_id = h.signal_id
            JOIN signals s ON s.id = h.signal_id
            WHERE s.is_active = false AND p.outcome <> 'ACTIVE'
            GROUP BY 1"""
    ))).fetchall()
    inv = _acc_block(inv_rows)
    invalidating_accuracy = {
        "signals_flagged": inv["resolved"],
        # correct = signal that was flagged invalidating and indeed lost
        "correct_loss_rate": round(inv["loss"] / inv["resolved"] * 100, 1) if inv["resolved"] else None,
        "false_alarm_rate": round(inv["win"] / inv["resolved"] * 100, 1) if inv["resolved"] else None,
        "detail": inv["raw"],
    }

    appr_rows = (await db.execute(text(
        f"""SELECT (p.hit_tp1) AS hit, count(*) c
            FROM (SELECT DISTINCT signal_id FROM signal_status_history WHERE to_status='approaching_tp') h
            JOIN signal_performances p ON p.signal_id = h.signal_id
            JOIN signals s ON s.id = h.signal_id
            WHERE s.is_active = false
            GROUP BY 1"""
    ))).fetchall()
    appr = {str(r[0]): r[1] for r in appr_rows}
    appr_hit = appr.get("True", 0) + appr.get("true", 0)
    appr_miss = appr.get("False", 0) + appr.get("false", 0)
    appr_total = appr_hit + appr_miss
    approaching_accuracy = {
        "signals_flagged": appr_total,
        "reached_tp1_rate": round(appr_hit / appr_total * 100, 1) if appr_total else None,
        "false_hope_rate": round(appr_miss / appr_total * 100, 1) if appr_total else None,
    }

    return {
        "window_days": days,
        "event_counts": event_counts,
        "transition_matrix": transition_matrix,
        "flipflops": {
            "prevented": prevented,
            "actual": actual_flipflops,
            "stability_ratio": stability_ratio,
        },
        "avg_state_duration_sec": avg_state_duration_sec,
        "invalidating_accuracy": invalidating_accuracy,
        "approaching_accuracy": approaching_accuracy,
        "note": "Davranışsal metrikler günler içinde, doğruluk metrikleri yeterli çözülmüş sinyal birikince güvenilir olur.",
    }


@router.get(
    "/{signal_id}/intelligence",
    summary="Adaptive intelligence panel data for a signal",
)
async def signal_intelligence(
    signal_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Rich 'is this signal still valid?' panel: live lifecycle status, birth
    regime, this coin/timeframe's learned track record, and the engine scores
    captured when the signal fired. Powers the symbol-page intelligence card."""
    res = await db.execute(
        select(Signal)
        .options(joinedload(Signal.performance), joinedload(Signal.asset))
        .where(Signal.id == signal_id)
    )
    signal = res.unique().scalar_one_or_none()
    if signal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signal not found.")

    symbol = signal.asset.symbol if signal.asset else None
    timeframe = signal.timeframe.value if hasattr(signal.timeframe, "value") else str(signal.timeframe)

    snap = (await db.execute(
        select(SignalSnapshot).where(SignalSnapshot.signal_id == signal_id)
    )).scalar_one_or_none()

    mem = None
    if symbol:
        mem = (await db.execute(
            select(CoinMemory).where(CoinMemory.symbol == symbol, CoinMemory.timeframe == timeframe)
        )).scalar_one_or_none()

    perf = signal.performance

    # Coin-specific learned track record.
    coin: Dict[str, Any] = {"has_memory": False}
    if mem and mem.total_signals > 0:
        resolved = (mem.wins or 0) + (mem.losses or 0)
        coin = {
            "has_memory": True,
            "total_signals": mem.total_signals,
            "wins": mem.wins,
            "losses": mem.losses,
            "win_rate": round((mem.wins / resolved) * 100, 1) if resolved > 0 else None,
            "avg_bars_to_outcome": float(mem.avg_bars_to_outcome) if mem.avg_bars_to_outcome else None,
            "adaptive_active": bool(mem.adaptive_weights),
        }

    # Historical similarity: how did past setups that looked like this resolve?
    from app.services.similarity import find_similar_setups
    try:
        similar = await find_similar_setups(db, signal_id)
    except Exception:
        similar = {"has_data": False, "match_count": 0}

    # Win rate in the regime this signal was born into.
    regime = snap.regime if snap else None
    regime_win_rate = None
    if mem and regime and mem.regime_stats and regime in mem.regime_stats:
        rs = mem.regime_stats[regime]
        if rs.get("total"):
            regime_win_rate = round(rs["wins"] / rs["total"] * 100, 1)

    return {
        "signal_id": str(signal_id),
        "symbol": symbol,
        "timeframe": timeframe,
        "is_active": signal.is_active,
        "generated_at": signal.generated_at.isoformat() if signal.generated_at else None,
        "live_status": signal.live_status,
        "live_status_tr": lifecycle.status_tr(signal.live_status),
        "status_reason": signal.status_reason,
        "status_updated_at": signal.status_updated_at.isoformat() if signal.status_updated_at else None,
        "status_since": signal.live_status_since.isoformat() if signal.live_status_since else None,
        "seconds_in_state": (
            (datetime.now(timezone.utc) - (
                signal.live_status_since if signal.live_status_since.tzinfo
                else signal.live_status_since.replace(tzinfo=timezone.utc)
            )).total_seconds()
            if signal.live_status_since else None
        ),
        "birth_confidence": float(snap.composite_confidence) if snap and snap.composite_confidence is not None else float(signal.confidence_score),
        "regime": regime,
        "regime_win_rate": regime_win_rate,
        "atr_pct": float(snap.atr_pct) if snap and snap.atr_pct is not None else None,
        "volatility_ratio": float(snap.volatility_ratio) if snap and snap.volatility_ratio is not None else None,
        "fear_greed": snap.fear_greed if snap else None,
        "engine_scores_at_signal": snap.engine_scores if snap else None,
        "coin_memory": coin,
        "similar_setups": similar,
        "outcome": perf.outcome.value if perf else None,
        "detail_label": perf.detail_label if perf else None,
        "detail_label_tr": outcome_labels.label_tr(perf.detail_label) if perf and perf.detail_label else None,
        "mfe_pct": float(perf.mfe_pct) if perf and perf.mfe_pct is not None else None,
        "max_drawdown": float(perf.max_drawdown) if perf and perf.max_drawdown is not None else None,
        "bars_to_outcome": perf.bars_to_outcome if perf else None,
    }


@router.get(
    "/{signal_id}",
    response_model=SignalDetailResponse,
    summary="Get signal details",
)
async def get_signal(
    signal_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> SignalDetailResponse:
    """
    Retrieve full details of a specific signal including performance data.
    """
    query = (
        select(Signal)
        .options(joinedload(Signal.performance))
        .where(Signal.id == signal_id)
    )
    result = await db.execute(query)
    signal = result.unique().scalar_one_or_none()

    if signal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Signal not found.",
        )

    return SignalDetailResponse.model_validate(signal)


@router.post(
    "/generate-batch",
    summary="Generate signals for all active assets",
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_batch(
    tier: SubscriptionTier = Depends(get_user_tier_optional),
) -> dict:
    """
    Trigger signal generation for all active assets in the background.
    Free users have a daily cap; Pro/Premium are unlimited.
    """
    # Free users can trigger only if they have remaining quota — simplified
    # to "Pro or above" here.
    if tier == SubscriptionTier.FREE:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "upgrade_required",
                "feature": "manual_batch_generation",
                "message": "Toplu sinyal üretimi Pro veya üzeri abonelik gerektirir.",
            },
        )
    from app.services.scheduler import _run_all_signals
    import asyncio
    asyncio.create_task(_run_all_signals("1h"))
    return {"status": "accepted", "message": "Signal generation started for all active assets."}


@router.post(
    "/generate/{symbol}",
    response_model=SignalDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Trigger signal generation for an asset",
)
async def generate_signal(
    symbol: str,
    timeframe: str = Query("1h", description="Timeframe to analyze (e.g. 15m, 1h, 4h, 1d)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SignalDetailResponse:
    """
    Trigger analysis and signal generation for a specific asset.
    Runs the multi-engine AI decision suite synchronously and saves the resulting signal.
    """
    # Find the asset
    asset_query = select(Asset).where(func.upper(Asset.symbol) == symbol.upper())
    asset_result = await db.execute(asset_query)
    asset = asset_result.scalar_one_or_none()

    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset with symbol '{symbol}' not found.",
        )

    from app.models.price_data import Timeframe as DBTimeframe

    # Map timeframe string to DB enum
    tf_enum_map = {
        "1m": DBTimeframe.M1,
        "5m": DBTimeframe.M5,
        "15m": DBTimeframe.M15,
        "1h": DBTimeframe.H1,
        "4h": DBTimeframe.H4,
        "1d": DBTimeframe.D1,
        "1w": DBTimeframe.W1,
    }
    db_tf = tf_enum_map.get(timeframe.lower(), DBTimeframe.H1)

    binance = BinanceCollector()
    yahoo = YahooCollector()
    try:
        if asset.asset_type.value == "stock" or symbol.upper().endswith(".IS"):
            df = await yahoo.fetch_ohlcv(symbol, timeframe, limit=100)
        else:
            df = await binance.fetch_ohlcv(symbol, timeframe, limit=100)
    except Exception as e:
        logger.error("Market data fetch failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch market data from the data feed.",
        )
    finally:
        await binance.close()
        await yahoo.close()

    try:
        # Run orchestrator
        engine = AIDecisionEngine()
        decision = await engine.analyze_and_decide(
            symbol=symbol,
            timeframe=timeframe,
            ohlcv_data=df,
            asset_type=asset.asset_type.value,
        )
    except Exception as e:
        logger.error(f"Decision Engine execution failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Analysis engine execution failed. Please try again later.",
        )

    # Deactivate any previous active signals for this asset on this timeframe
    deactivate_query = (
        select(Signal)
        .where(Signal.asset_id == asset.id)
        .where(Signal.timeframe == db_tf)
        .where(Signal.is_active == True)
    )
    deactivate_res = await db.execute(deactivate_query)
    for old_sig in deactivate_res.scalars().all():
        old_sig.is_active = False

    sig_type_map = {
        "STRONG_BUY": SignalType.STRONG_BUY,
        "BUY": SignalType.BUY,
        "HOLD": SignalType.HOLD,
        "SELL": SignalType.SELL,
        "STRONG_SELL": SignalType.STRONG_SELL,
    }

    dir_map = {
        "bullish": Direction.BULLISH,
        "bearish": Direction.BEARISH,
        "neutral": Direction.NEUTRAL,
    }

    risk_map = {
        "low": RiskLevel.LOW,
        "medium": RiskLevel.MEDIUM,
        "high": RiskLevel.HIGH,
        "very_high": RiskLevel.VERY_HIGH,
    }

    generated_at = datetime.now(timezone.utc)
    expires_at = generated_at + timedelta(hours=48)

    new_signal = Signal(
        asset_id=asset.id,
        signal_type=sig_type_map.get(decision["signal_type"], SignalType.HOLD),
        confidence_score=decision["confidence_score"],
        probability_score=decision["probability_score"],
        risk_score=decision["risk_score"],
        risk_level=risk_map.get(decision["risk_level"].lower(), RiskLevel.MEDIUM),
        direction=dir_map.get(decision["direction"], Direction.NEUTRAL),
        entry_zone_low=decision["entry_zone_low"],
        entry_zone_high=decision["entry_zone_high"],
        stop_loss=decision["stop_loss"],
        tp1=decision["tp1"],
        tp2=decision["tp2"],
        tp3=decision["tp3"],
        invalidation_conditions=decision["invalidation_conditions"],
        engines_data=decision["engine_results"],
        explanation_tr=decision["explanation_tr"],
        explanation_en=decision["explanation_en"],
        is_active=True,
        timeframe=db_tf,
        generated_at=generated_at,
        expires_at=expires_at,
    )

    db.add(new_signal)
    await db.flush()
    
    perf = SignalPerformance(
        signal_id=new_signal.id,
        outcome=SignalOutcome.ACTIVE,
    )
    db.add(perf)
    
    await db.commit()

    logger.info(
        "Signal successfully generated and saved for %s (%s). Type: %s",
        symbol,
        timeframe,
        new_signal.signal_type.value,
    )

    # Re-fetch with joined relations
    final_query = (
        select(Signal)
        .options(joinedload(Signal.performance))
        .where(Signal.id == new_signal.id)
    )
    final_res = await db.execute(final_query)
    signal_detail = final_res.unique().scalar_one()

    return SignalDetailResponse.model_validate(signal_detail)


@router.post(
    "/backtest",
    response_model=BacktestResponse,
    summary="Run walk-forward historical backtest for an asset",
)
async def backtest_endpoint(
    req: BacktestRequest,
    current_user: User = Depends(get_current_user),
    _gate = Depends(require_feature("can_use_backtest")),
) -> BacktestResponse:
    """
    Run historical backtest simulation candle-by-candle.
    Supports walk-forward testing with zero look-ahead bias.
    """
    binance = BinanceCollector()
    yahoo = YahooCollector()

    try:
        # Fetch longer history (e.g. 300 bars) for backtesting
        if req.symbol.upper().endswith(".IS") or len(req.symbol) == 5:
            df = await yahoo.fetch_ohlcv(req.symbol, req.timeframe, limit=300)
        else:
            df = await binance.fetch_ohlcv(req.symbol, req.timeframe, limit=300)
    except Exception as e:
        logger.error("Backtest candle fetch failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch historical candles for backtesting.",
        )
    finally:
        await binance.close()
        await yahoo.close()

    if df.empty or len(df) < 80:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient candle history ({len(df)} bars) to run backtest. Need at least 80 bars.",
        )

    try:
        engine = BacktestEngine()
        report = await engine.run_backtest(
            symbol=req.symbol,
            timeframe=req.timeframe,
            df=df,
            initial_capital=req.initial_capital,
            risk_pct=req.risk_pct,
            max_age=req.max_age,
            execution_model=req.execution_model,
        )
    except Exception as e:
        logger.error(f"Backtesting engine failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Backtest simulation failed. Please try again later.",
        )

    return BacktestResponse(
        total_trades=report.total_trades,
        wins=report.wins,
        losses=report.losses,
        breakevens=report.breakevens,
        expired=report.expired,
        win_rate=report.win_rate,
        loss_rate=report.loss_rate,
        profit_factor=report.profit_factor,
        sharpe_ratio=report.sharpe_ratio,
        sortino_ratio=report.sortino_ratio,
        max_drawdown_pct=report.max_drawdown_pct,
        average_return_pct=report.average_return_pct,
        average_rr=report.average_rr,
        expectancy_pct=report.expectancy_pct,
        max_consecutive_wins=report.max_consecutive_wins,
        max_consecutive_losses=report.max_consecutive_losses,
        equity_curve=report.equity_curve,
        trades_log=report.trades_log,
    )


@router.post(
    "/track-performance",
    summary="Manually trigger performance tracking check",
)
async def manual_track_performance(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Trigger performance tracking sweep across active signals.
    Checks subsequent price action to resolve active signals as WIN, LOSS, etc.
    """
    try:
        summary = await track_and_resolve_active_signals(db)
        return {
            "status": "success",
            "message": f"Processed {summary['processed']} active signals. Resolved {summary['resolved']}.",
            "details": summary["details"],
        }
    except Exception as e:
        logger.error(f"Error during manual performance tracking sweep: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Performance tracking sweep failed.",
        )
