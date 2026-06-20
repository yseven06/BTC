"""
Portfolio API routes.

Full CRUD for portfolios and portfolio holdings with authentication.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.portfolio import Portfolio, PortfolioHolding
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


# --- Request/Response schemas specific to portfolio routes ---


class PortfolioCreate(BaseModel):
    """Create a new portfolio."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    initial_capital: Optional[float] = 0
    currency: str = Field("USD", max_length=10)


class PortfolioUpdate(BaseModel):
    """Update portfolio fields."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    initial_capital: Optional[float] = None
    currency: Optional[str] = None


class HoldingCreate(BaseModel):
    """Add a holding to a portfolio."""
    asset_id: UUID
    quantity: float
    average_entry_price: float
    notes: Optional[str] = None


class HoldingUpdate(BaseModel):
    """Update holding fields."""
    quantity: Optional[float] = None
    average_entry_price: Optional[float] = None
    current_price: Optional[float] = None
    notes: Optional[str] = None


class HoldingClose(BaseModel):
    """Close an open holding at a realized exit price."""
    exit_price: float = Field(..., gt=0)


class HoldingResponse(BaseModel):
    """Portfolio holding response."""
    id: UUID
    portfolio_id: UUID
    asset_id: Optional[UUID] = None
    quantity: float
    average_entry_price: float
    current_price: Optional[float] = None
    total_cost: Optional[float] = None
    current_value: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None
    notes: Optional[str] = None
    is_closed: bool = False
    exit_price: Optional[float] = None
    realized_pnl: Optional[float] = None
    realized_pnl_pct: Optional[float] = None
    closed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PortfolioResponse(BaseModel):
    """Portfolio response with holdings."""
    id: UUID
    user_id: UUID
    name: str
    description: Optional[str] = None
    initial_capital: Optional[float] = 0
    currency: str = "USD"
    holdings: List[HoldingResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class PortfolioListResponse(BaseModel):
    """Simple portfolio list item (without holdings)."""
    id: UUID
    user_id: UUID
    name: str
    description: Optional[str] = None
    initial_capital: Optional[float] = 0
    currency: str = "USD"

    model_config = {"from_attributes": True}


# --- Routes ---


@router.get(
    "",
    response_model=List[PortfolioListResponse],
    summary="List user portfolios",
)
async def list_portfolios(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[PortfolioListResponse]:
    """
    Get all portfolios belonging to the authenticated user.
    """
    query = (
        select(Portfolio)
        .where(Portfolio.user_id == current_user.id)
        .order_by(Portfolio.created_at.desc())
    )
    result = await db.execute(query)
    portfolios = result.scalars().all()
    return [PortfolioListResponse.model_validate(p) for p in portfolios]


@router.post(
    "",
    response_model=PortfolioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new portfolio",
)
async def create_portfolio(
    payload: PortfolioCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortfolioResponse:
    """
    Create a new portfolio for the authenticated user.
    """
    portfolio = Portfolio(
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
        initial_capital=payload.initial_capital,
        currency=payload.currency,
    )
    db.add(portfolio)
    await db.flush()
    await db.refresh(portfolio)

    logger.info("Portfolio created: %s for user %s", portfolio.name, current_user.email)
    return PortfolioResponse.model_validate(portfolio)


@router.get(
    "/{portfolio_id}",
    response_model=PortfolioResponse,
    summary="Get portfolio with holdings",
)
async def get_portfolio(
    portfolio_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortfolioResponse:
    """
    Retrieve a portfolio including all its holdings.
    """
    query = (
        select(Portfolio)
        .options(joinedload(Portfolio.holdings))
        .where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    result = await db.execute(query)
    portfolio = result.unique().scalar_one_or_none()

    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found.",
        )

    return PortfolioResponse.model_validate(portfolio)


@router.patch(
    "/{portfolio_id}",
    response_model=PortfolioResponse,
    summary="Update a portfolio",
)
async def update_portfolio(
    portfolio_id: UUID,
    payload: PortfolioUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortfolioResponse:
    """
    Update portfolio metadata.
    """
    query = (
        select(Portfolio)
        .options(joinedload(Portfolio.holdings))
        .where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    result = await db.execute(query)
    portfolio = result.unique().scalar_one_or_none()

    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found.",
        )

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(portfolio, field, value)

    await db.flush()
    await db.refresh(portfolio)
    return PortfolioResponse.model_validate(portfolio)


@router.delete(
    "/{portfolio_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a portfolio",
)
async def delete_portfolio(
    portfolio_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete a portfolio and all its holdings.
    """
    query = select(Portfolio).where(
        Portfolio.id == portfolio_id,
        Portfolio.user_id == current_user.id,
    )
    result = await db.execute(query)
    portfolio = result.scalar_one_or_none()

    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found.",
        )

    await db.delete(portfolio)
    await db.flush()


# --- Holding sub-routes ---


@router.post(
    "/{portfolio_id}/holdings",
    response_model=HoldingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a holding to portfolio",
)
async def add_holding(
    portfolio_id: UUID,
    payload: HoldingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HoldingResponse:
    """
    Add a new asset holding to a portfolio.
    """
    # Verify portfolio ownership
    pf_query = select(Portfolio).where(
        Portfolio.id == portfolio_id,
        Portfolio.user_id == current_user.id,
    )
    pf_result = await db.execute(pf_query)
    portfolio = pf_result.scalar_one_or_none()
    if portfolio is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio not found.")

    total_cost = payload.quantity * payload.average_entry_price
    holding = PortfolioHolding(
        portfolio_id=portfolio_id,
        asset_id=payload.asset_id,
        quantity=Decimal(str(payload.quantity)),
        average_entry_price=Decimal(str(payload.average_entry_price)),
        total_cost=Decimal(str(total_cost)),
        notes=payload.notes,
    )
    db.add(holding)
    await db.flush()
    await db.refresh(holding)

    return HoldingResponse.model_validate(holding)


@router.patch(
    "/{portfolio_id}/holdings/{holding_id}",
    response_model=HoldingResponse,
    summary="Update a holding",
)
async def update_holding(
    portfolio_id: UUID,
    holding_id: UUID,
    payload: HoldingUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HoldingResponse:
    """
    Update holding quantity, price, or notes.
    """
    # Verify portfolio ownership
    pf_query = select(Portfolio).where(
        Portfolio.id == portfolio_id,
        Portfolio.user_id == current_user.id,
    )
    pf_result = await db.execute(pf_query)
    portfolio = pf_result.scalar_one_or_none()
    if portfolio is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio not found.")

    h_query = select(PortfolioHolding).where(
        PortfolioHolding.id == holding_id,
        PortfolioHolding.portfolio_id == portfolio_id,
    )
    h_result = await db.execute(h_query)
    holding = h_result.scalar_one_or_none()

    if holding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found.")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None and field in ("quantity", "average_entry_price", "current_price"):
            value = Decimal(str(value))
        setattr(holding, field, value)

    # Recalculate derived fields
    qty = float(holding.quantity or 0)
    entry = float(holding.average_entry_price or 0)
    holding.total_cost = Decimal(str(qty * entry))

    if holding.current_price is not None:
        current = float(holding.current_price)
        holding.current_value = Decimal(str(qty * current))
        holding.unrealized_pnl = holding.current_value - holding.total_cost
        if holding.total_cost and float(holding.total_cost) != 0:
            holding.unrealized_pnl_pct = Decimal(
                str(round(float(holding.unrealized_pnl) / float(holding.total_cost) * 100, 4))
            )

    await db.flush()
    await db.refresh(holding)
    return HoldingResponse.model_validate(holding)


@router.post(
    "/{portfolio_id}/holdings/{holding_id}/close",
    response_model=HoldingResponse,
    summary="Close a position at a realized exit price",
)
async def close_holding(
    portfolio_id: UUID,
    holding_id: UUID,
    payload: HoldingClose,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HoldingResponse:
    """
    Lock in the realized P&L for a long-only spot holding (exit_price - avg
    entry, times quantity) and mark it closed. Closed holdings stay in the
    portfolio as history — they aren't deleted — so the user has a permanent
    record to share a "closed trade" result card from, same as the live
    "open position" card they can already generate from an unclosed holding.
    """
    pf_query = select(Portfolio).where(
        Portfolio.id == portfolio_id,
        Portfolio.user_id == current_user.id,
    )
    pf_result = await db.execute(pf_query)
    if pf_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio not found.")

    h_query = select(PortfolioHolding).where(
        PortfolioHolding.id == holding_id,
        PortfolioHolding.portfolio_id == portfolio_id,
    )
    h_result = await db.execute(h_query)
    holding = h_result.scalar_one_or_none()
    if holding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found.")
    if holding.is_closed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Pozisyon zaten kapatılmış.")

    qty = float(holding.quantity or 0)
    entry = float(holding.average_entry_price or 0)
    exit_price = payload.exit_price
    cost = qty * entry

    realized_pnl = qty * (exit_price - entry)
    realized_pnl_pct = round((realized_pnl / cost) * 100, 4) if cost > 0 else 0.0

    holding.is_closed = True
    holding.exit_price = Decimal(str(exit_price))
    holding.realized_pnl = Decimal(str(realized_pnl))
    holding.realized_pnl_pct = Decimal(str(realized_pnl_pct))
    holding.closed_at = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(holding)
    return HoldingResponse.model_validate(holding)


@router.delete(
    "/{portfolio_id}/holdings/{holding_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a holding",
)
async def delete_holding(
    portfolio_id: UUID,
    holding_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove an asset holding from a portfolio.
    """
    pf_query = select(Portfolio).where(
        Portfolio.id == portfolio_id,
        Portfolio.user_id == current_user.id,
    )
    pf_result = await db.execute(pf_query)
    if pf_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio not found.")

    h_query = select(PortfolioHolding).where(
        PortfolioHolding.id == holding_id,
        PortfolioHolding.portfolio_id == portfolio_id,
    )
    h_result = await db.execute(h_query)
    holding = h_result.scalar_one_or_none()

    if holding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found.")

    await db.delete(holding)
    await db.flush()
