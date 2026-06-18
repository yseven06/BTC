"""
Watchlist database model.

Allows users to organize and track groups of assets they are interested in.
"""

import uuid

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSON, UUID
from sqlalchemy.orm import relationship

from app.database import Base


class Watchlist(Base):
    """
    User watchlist model.

    Each watchlist holds a named collection of asset IDs that a user
    wants to monitor.

    Attributes:
        id: Unique UUID primary key.
        user_id: Foreign key to the owning user.
        name: Display name of the watchlist.
        asset_ids: JSON array of asset UUID strings.
        created_at: Creation timestamp.
    """

    __tablename__ = "watchlists"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(100), nullable=False)
    asset_ids = Column(JSON, nullable=False, default=list)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    user = relationship("User", back_populates="watchlists")

    def __repr__(self) -> str:
        return f"<Watchlist(id={self.id}, user_id={self.user_id}, name={self.name})>"
