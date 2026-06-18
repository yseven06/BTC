"""
Watchlist-related Pydantic schemas.

Covers creation, update, and response models for user watchlists.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class WatchlistCreate(BaseModel):
    """Schema for creating a new watchlist."""

    name: str = Field(..., min_length=1, max_length=100, description="Watchlist name.")
    asset_ids: List[str] = Field(default_factory=list, description="List of asset UUID strings.")


class WatchlistUpdate(BaseModel):
    """Schema for updating a watchlist."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    asset_ids: Optional[List[str]] = None


class WatchlistResponse(BaseModel):
    """Watchlist response model."""

    id: UUID
    user_id: UUID
    name: str
    asset_ids: List[str] = Field(default_factory=list)
    created_at: datetime

    model_config = {"from_attributes": True}
