"""
Watchlist API routes.

Full CRUD for user watchlists with authentication.
"""

import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.watchlist import Watchlist
from app.schemas.watchlist import WatchlistCreate, WatchlistResponse, WatchlistUpdate

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "",
    response_model=List[WatchlistResponse],
    summary="List user watchlists",
)
async def list_watchlists(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[WatchlistResponse]:
    """
    Get all watchlists belonging to the authenticated user.
    """
    query = (
        select(Watchlist)
        .where(Watchlist.user_id == current_user.id)
        .order_by(Watchlist.created_at.desc())
    )
    result = await db.execute(query)
    watchlists = result.scalars().all()
    return [WatchlistResponse.model_validate(w) for w in watchlists]


@router.post(
    "",
    response_model=WatchlistResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new watchlist",
)
async def create_watchlist(
    payload: WatchlistCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WatchlistResponse:
    """
    Create a new watchlist for the authenticated user.
    """
    watchlist = Watchlist(
        user_id=current_user.id,
        name=payload.name,
        asset_ids=payload.asset_ids,
    )
    db.add(watchlist)
    await db.flush()
    await db.refresh(watchlist)

    logger.info("Watchlist created: %s for user %s", watchlist.name, current_user.email)
    return WatchlistResponse.model_validate(watchlist)


@router.get(
    "/{watchlist_id}",
    response_model=WatchlistResponse,
    summary="Get a watchlist by ID",
)
async def get_watchlist(
    watchlist_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WatchlistResponse:
    """
    Retrieve a specific watchlist. Must belong to the authenticated user.
    """
    query = select(Watchlist).where(
        Watchlist.id == watchlist_id,
        Watchlist.user_id == current_user.id,
    )
    result = await db.execute(query)
    watchlist = result.scalar_one_or_none()

    if watchlist is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist not found.",
        )

    return WatchlistResponse.model_validate(watchlist)


@router.patch(
    "/{watchlist_id}",
    response_model=WatchlistResponse,
    summary="Update a watchlist",
)
async def update_watchlist(
    watchlist_id: UUID,
    payload: WatchlistUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WatchlistResponse:
    """
    Update a watchlist's name or asset list.
    """
    query = select(Watchlist).where(
        Watchlist.id == watchlist_id,
        Watchlist.user_id == current_user.id,
    )
    result = await db.execute(query)
    watchlist = result.scalar_one_or_none()

    if watchlist is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist not found.",
        )

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(watchlist, field, value)

    await db.flush()
    await db.refresh(watchlist)
    return WatchlistResponse.model_validate(watchlist)


@router.delete(
    "/{watchlist_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a watchlist",
)
async def delete_watchlist(
    watchlist_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete a watchlist. Must belong to the authenticated user.
    """
    query = select(Watchlist).where(
        Watchlist.id == watchlist_id,
        Watchlist.user_id == current_user.id,
    )
    result = await db.execute(query)
    watchlist = result.scalar_one_or_none()

    if watchlist is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist not found.",
        )

    await db.delete(watchlist)
    await db.flush()
    logger.info("Watchlist deleted: %s by user %s", watchlist_id, current_user.email)
