"""
Asset database model.

Represents tradeable assets across multiple markets including
crypto, stocks, forex, and futures.
"""

import enum
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    Enum,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import relationship

from app.database import Base


class AssetType(str, enum.Enum):
    """Supported asset classes."""
    CRYPTO = "crypto"
    STOCK = "stock"
    FOREX = "forex"
    FUTURES = "futures"


class Asset(Base):
    """
    Tradeable asset model.

    Attributes:
        id: Unique UUID primary key.
        symbol: Ticker symbol (e.g., BTCUSDT, THYAO.IS, EURUSD).
        name: Human-readable name (e.g., Bitcoin, Turkish Airlines).
        asset_type: The asset class category.
        market: Market or exchange identifier (e.g., binance, bist, nasdaq).
        logo_url: URL to the asset's logo image.
        metadata_json: Additional unstructured metadata.
        is_active: Whether the asset is actively tracked.
    """

    __tablename__ = "assets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    symbol = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    asset_type = Column(
        Enum(AssetType, name="asset_type", create_constraint=True),
        nullable=False,
        index=True,
    )
    market = Column(String(50), nullable=True, index=True)
    logo_url = Column(Text, nullable=True)
    metadata_json = Column("metadata", JSON, nullable=True, default=dict)
    is_active = Column(Boolean, nullable=False, default=True)

    # Relationships
    price_data = relationship("PriceData", back_populates="asset", cascade="all, delete-orphan")
    signals = relationship("Signal", back_populates="asset", cascade="all, delete-orphan")
    analysis_results = relationship("AnalysisResult", back_populates="asset", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="asset", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Asset(id={self.id}, symbol={self.symbol}, type={self.asset_type})>"
