"""
Asset API routes.

Provides endpoints for listing, searching, and retrieving asset details.
"""

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.asset import Asset, AssetType
from app.schemas.asset import AssetListResponse, AssetResponse, AssetSearchResult

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "",
    response_model=AssetListResponse,
    summary="List assets with filters",
)
async def list_assets(
    asset_type: Optional[str] = Query(None, description="Filter by asset type (crypto, stock, forex, futures)."),
    market: Optional[str] = Query(None, description="Filter by market (binance, bist, etc.)."),
    is_active: Optional[bool] = Query(None, description="Filter by active status."),
    page: int = Query(1, ge=1, description="Page number."),
    page_size: int = Query(20, ge=1, le=200, description="Items per page."),
    db: AsyncSession = Depends(get_db),
) -> AssetListResponse:
    """
    List assets with optional filtering and pagination.
    """
    # Crypto-only ürün (2026-07): BIST/hisse kaldırıldı — public varlık listesi yalnız kripto.
    query = select(Asset).where(Asset.asset_type == AssetType.CRYPTO)

    if asset_type is not None:
        try:
            at = AssetType(asset_type)
            query = query.where(Asset.asset_type == at)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid asset_type: {asset_type}. Must be one of: {[t.value for t in AssetType]}",
            )

    if market is not None:
        query = query.where(Asset.market == market)

    if is_active is not None:
        query = query.where(Asset.is_active == is_active)

    # Count total matching records
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.order_by(Asset.symbol).offset(offset).limit(page_size)
    result = await db.execute(query)
    assets = result.scalars().all()

    total_pages = max(1, (total + page_size - 1) // page_size)

    return AssetListResponse(
        items=[AssetResponse.model_validate(a) for a in assets],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_previous=page > 1,
    )


@router.get(
    "/search",
    response_model=List[AssetSearchResult],
    summary="Search assets by name or symbol",
)
async def search_assets(
    q: str = Query(..., min_length=1, max_length=50, description="Search query."),
    limit: int = Query(10, ge=1, le=50, description="Maximum results to return."),
    db: AsyncSession = Depends(get_db),
) -> List[AssetSearchResult]:
    """
    Search assets by symbol or name using case-insensitive partial matching.
    Returns lightweight results for autocomplete use cases.
    """
    search_pattern = f"%{q.upper()}%"
    query = (
        select(Asset)
        .where(
            Asset.is_active == True,
            or_(
                func.upper(Asset.symbol).like(search_pattern),
                func.upper(Asset.name).like(search_pattern),
            ),
        )
        .order_by(Asset.symbol)
        .limit(limit)
    )
    result = await db.execute(query)
    assets = result.scalars().all()
    return [AssetSearchResult.model_validate(a) for a in assets]


@router.get(
    "/{symbol}",
    response_model=AssetResponse,
    summary="Get asset details by symbol",
)
async def get_asset(
    symbol: str,
    db: AsyncSession = Depends(get_db),
) -> AssetResponse:
    """
    Retrieve detailed information about a specific asset by its symbol.
    """
    query = select(Asset).where(func.upper(Asset.symbol) == symbol.upper())
    result = await db.execute(query)
    asset = result.scalar_one_or_none()

    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset with symbol '{symbol}' not found.",
        )

    return AssetResponse.model_validate(asset)
