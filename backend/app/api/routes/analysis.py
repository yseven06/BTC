"""
Analysis API routes.

Provides endpoints for viewing per-engine analysis results
and composite analysis overviews for assets.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.analysis import AnalysisBias, AnalysisResult, EngineType
from app.models.asset import Asset
from app.schemas.analysis import AnalysisResponse, EngineResultResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/{symbol}",
    response_model=AnalysisResponse,
    summary="Get full analysis for an asset",
)
async def get_analysis(
    symbol: str,
    db: AsyncSession = Depends(get_db),
) -> AnalysisResponse:
    """
    Retrieve composite analysis results from all engines for a given asset.

    Aggregates the latest result from each engine type and computes
    an overall score and directional bias.
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

    # Get the latest result for each engine type
    # Using a subquery to find max analyzed_at per engine_type
    latest_subquery = (
        select(
            AnalysisResult.engine_type,
            func.max(AnalysisResult.analyzed_at).label("max_analyzed_at"),
        )
        .where(AnalysisResult.asset_id == asset.id)
        .group_by(AnalysisResult.engine_type)
        .subquery()
    )

    query = (
        select(AnalysisResult)
        .join(
            latest_subquery,
            (AnalysisResult.engine_type == latest_subquery.c.engine_type)
            & (AnalysisResult.analyzed_at == latest_subquery.c.max_analyzed_at),
        )
        .where(AnalysisResult.asset_id == asset.id)
        .order_by(AnalysisResult.engine_type)
    )

    result = await db.execute(query)
    engine_results = result.scalars().all()

    # Compute overall score (average of all engine scores)
    scores = [
        float(r.score) for r in engine_results if r.score is not None
    ]
    overall_score = round(sum(scores) / len(scores), 2) if scores else None

    # Determine overall bias from the average score.
    # All engine scores are on a 0–100 scale where 50 = neutral, > 50 = bullish,
    # < 50 = bearish.  The previous thresholds were written for a -100…+100 scale
    # which caused a neutral score of ~50 to display as STRONGLY_BULLISH.
    overall_bias = None
    if overall_score is not None:
        if overall_score >= 75:
            overall_bias = AnalysisBias.STRONGLY_BULLISH.value
        elif overall_score >= 60:
            overall_bias = AnalysisBias.BULLISH.value
        elif overall_score >= 53:
            overall_bias = AnalysisBias.SLIGHTLY_BULLISH.value
        elif overall_score >= 47:
            overall_bias = AnalysisBias.NEUTRAL.value
        elif overall_score >= 40:
            overall_bias = AnalysisBias.SLIGHTLY_BEARISH.value
        elif overall_score >= 25:
            overall_bias = AnalysisBias.BEARISH.value
        else:
            overall_bias = AnalysisBias.STRONGLY_BEARISH.value

    latest_at = max(
        (r.analyzed_at for r in engine_results), default=None
    )

    return AnalysisResponse(
        asset_id=asset.id,
        symbol=asset.symbol,
        overall_score=overall_score,
        overall_bias=overall_bias,
        engine_results=[EngineResultResponse.model_validate(r) for r in engine_results],
        analyzed_at=latest_at,
    )


@router.get(
    "/{symbol}/{engine_type}",
    response_model=EngineResultResponse,
    summary="Get analysis from a specific engine",
)
async def get_engine_analysis(
    symbol: str,
    engine_type: str,
    db: AsyncSession = Depends(get_db),
) -> EngineResultResponse:
    """
    Retrieve the latest analysis result from a specific engine for an asset.
    """
    # Validate engine_type
    try:
        et = EngineType(engine_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid engine_type: {engine_type}. Must be one of: {[e.value for e in EngineType]}",
        )

    # Find the asset
    asset_query = select(Asset).where(func.upper(Asset.symbol) == symbol.upper())
    asset_result = await db.execute(asset_query)
    asset = asset_result.scalar_one_or_none()

    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset with symbol '{symbol}' not found.",
        )

    # Get the latest result for this engine type
    query = (
        select(AnalysisResult)
        .where(
            AnalysisResult.asset_id == asset.id,
            AnalysisResult.engine_type == et,
        )
        .order_by(AnalysisResult.analyzed_at.desc())
        .limit(1)
    )
    result = await db.execute(query)
    analysis = result.scalar_one_or_none()

    if analysis is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No {engine_type} analysis found for '{symbol}'.",
        )

    return EngineResultResponse.model_validate(analysis)
