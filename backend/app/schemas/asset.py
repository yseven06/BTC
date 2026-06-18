"""
Asset-related Pydantic schemas.

Provides response models for asset listing, detail, and search results.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AssetResponse(BaseModel):
    """Single asset response."""

    id: UUID
    symbol: str
    name: str
    asset_type: str
    market: Optional[str] = None
    logo_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = Field(None, alias="metadata_json")
    is_active: bool

    model_config = {"from_attributes": True, "populate_by_name": True}


class AssetListResponse(BaseModel):
    """Paginated list of assets."""

    items: List[AssetResponse] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    total_pages: int = 0
    has_next: bool = False
    has_previous: bool = False


class AssetSearchResult(BaseModel):
    """Lightweight asset for search autocomplete."""

    id: UUID
    symbol: str
    name: str
    asset_type: str
    market: Optional[str] = None
    logo_url: Optional[str] = None

    model_config = {"from_attributes": True}
