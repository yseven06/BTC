"""
Portfolio and PortfolioHolding database models.

Tracks user investment portfolios with individual asset holdings,
entry prices, quantities, and current profit/loss calculations.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import relationship

from app.database import Base


class Portfolio(Base):
    """
    User portfolio model.

    Represents a named portfolio containing multiple asset holdings.

    Attributes:
        id: Unique UUID primary key.
        user_id: Foreign key to the owning user.
        name: Portfolio display name.
        description: Optional notes about the portfolio.
        initial_capital: Starting capital in base currency.
        currency: Base currency code (e.g., USD, TRY).
        created_at: Creation timestamp.
        updated_at: Last modification timestamp.
    """

    __tablename__ = "portfolios"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    initial_capital = Column(Numeric(precision=20, scale=2), nullable=True, default=0)
    currency = Column(String(10), nullable=False, default="USD")
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    user = relationship("User", back_populates="portfolios")
    holdings = relationship(
        "PortfolioHolding", back_populates="portfolio", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Portfolio(id={self.id}, user_id={self.user_id}, name={self.name})>"


class PortfolioHolding(Base):
    """
    Individual asset holding within a portfolio.

    Attributes:
        id: Unique UUID primary key.
        portfolio_id: Foreign key to the parent portfolio.
        asset_id: Foreign key to the held asset.
        quantity: Number of units held.
        average_entry_price: Average cost basis per unit.
        current_price: Last known market price per unit.
        total_cost: Total invested amount (quantity * avg_entry).
        current_value: Current market value.
        unrealized_pnl: Unrealised profit/loss.
        unrealized_pnl_pct: Unrealised P&L as percentage.
        notes: Optional trade notes.
        added_at: When the holding was first added.
        updated_at: Last update timestamp.
    """

    __tablename__ = "portfolio_holdings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    portfolio_id = Column(
        UUID(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    quantity = Column(Numeric(precision=20, scale=8), nullable=False, default=0)
    average_entry_price = Column(Numeric(precision=20, scale=8), nullable=False, default=0)
    current_price = Column(Numeric(precision=20, scale=8), nullable=True)
    total_cost = Column(Numeric(precision=20, scale=8), nullable=True)
    current_value = Column(Numeric(precision=20, scale=8), nullable=True)
    unrealized_pnl = Column(Numeric(precision=20, scale=8), nullable=True)
    unrealized_pnl_pct = Column(Numeric(precision=10, scale=4), nullable=True)
    notes = Column(Text, nullable=True)
    is_closed = Column(Boolean, nullable=False, default=False, server_default="false")
    exit_price = Column(Numeric(precision=20, scale=8), nullable=True)
    realized_pnl = Column(Numeric(precision=20, scale=8), nullable=True)
    realized_pnl_pct = Column(Numeric(precision=10, scale=4), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    added_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    portfolio = relationship("Portfolio", back_populates="holdings")
    asset = relationship("Asset")

    def __repr__(self) -> str:
        return (
            f"<PortfolioHolding(id={self.id}, portfolio={self.portfolio_id}, "
            f"asset={self.asset_id}, qty={self.quantity})>"
        )
