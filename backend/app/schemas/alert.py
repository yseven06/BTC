"""
Alert-related Pydantic schemas.

Covers creation, update, and response models for user alerts.
"""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AlertCreate(BaseModel):
    """Schema for creating a new alert."""

    asset_id: UUID = Field(..., description="Target asset UUID.")
    alert_type: str = Field(
        ...,
        pattern="^(price|signal|custom)$",
        description="Alert type: price, signal, or custom.",
    )
    conditions: Dict[str, Any] = Field(
        ...,
        description=(
            "Alert-specific conditions. Examples:\n"
            "  price: {\"direction\": \"above\", \"target_price\": 50000}\n"
            "  signal: {\"signal_types\": [\"strong_buy\"], \"min_confidence\": 75}\n"
            "  custom: {\"indicator\": \"RSI\", \"condition\": \"below\", \"value\": 30}"
        ),
    )


class AlertUpdate(BaseModel):
    """Schema for updating an alert."""

    conditions: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class AlertResponse(BaseModel):
    """Alert response model."""

    id: UUID
    user_id: UUID
    asset_id: UUID
    alert_type: str
    conditions: Dict[str, Any]
    is_active: bool
    triggered_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}
