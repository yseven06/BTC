"""
Price data database model.

Stores OHLCV (Open, High, Low, Close, Volume) candlestick data
for multiple timeframes, linked to assets.
"""

import enum
import uuid

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class Timeframe(str, enum.Enum):
    """Supported candlestick timeframes."""
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"


class PriceData(Base):
    """
    OHLCV candlestick data model.

    Stores historical and real-time price data for assets at
    various timeframe granularities. A composite unique constraint
    on (asset_id, timeframe, timestamp) prevents duplicate entries.

    Attributes:
        id: Unique UUID primary key.
        asset_id: Foreign key to the parent asset.
        open: Opening price.
        high: Highest price in the period.
        low: Lowest price in the period.
        close: Closing price.
        volume: Trading volume.
        timeframe: Candlestick time interval.
        timestamp: The start time of the candle.
    """

    __tablename__ = "price_data"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    open = Column(Numeric(precision=20, scale=8), nullable=False)
    high = Column(Numeric(precision=20, scale=8), nullable=False)
    low = Column(Numeric(precision=20, scale=8), nullable=False)
    close = Column(Numeric(precision=20, scale=8), nullable=False)
    volume = Column(Numeric(precision=30, scale=8), nullable=False, default=0)
    timeframe = Column(
        Enum(Timeframe, name="timeframe", create_constraint=True),
        nullable=False,
        index=True,
    )
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)

    # Relationships
    asset = relationship("Asset", back_populates="price_data")

    __table_args__ = (
        Index(
            "ix_price_data_asset_timeframe_ts",
            "asset_id",
            "timeframe",
            "timestamp",
            unique=True,
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<PriceData(asset_id={self.asset_id}, tf={self.timeframe}, "
            f"ts={self.timestamp}, close={self.close})>"
        )
