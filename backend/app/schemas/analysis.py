"""
Analysis-related Pydantic schemas.

Provides response models for per-engine analysis results and
composite analysis overviews.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class EngineResultResponse(BaseModel):
    """Single engine analysis result."""

    id: UUID
    asset_id: UUID
    engine_type: str
    result_data: Optional[Dict[str, Any]] = None
    score: Optional[float] = None
    bias: Optional[str] = None
    key_findings: Optional[List[str]] = None
    analyzed_at: datetime

    model_config = {"from_attributes": True}


class AnalysisResponse(BaseModel):
    """
    Composite analysis response for an asset.

    Combines results from all engines with an overall score and recommendation.
    """

    asset_id: UUID
    symbol: str
    overall_score: Optional[float] = None
    overall_bias: Optional[str] = None
    engine_results: List[EngineResultResponse] = Field(default_factory=list)
    analyzed_at: Optional[datetime] = None


class AnalysisListResponse(BaseModel):
    """Paginated list of analysis results."""

    items: List[EngineResultResponse] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
