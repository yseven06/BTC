"""
Alert API routes.

Full CRUD for user alerts with authentication.
"""

import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.alert import Alert, AlertType
from app.models.user import User
from app.schemas.alert import AlertCreate, AlertResponse, AlertUpdate

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "",
    response_model=List[AlertResponse],
    summary="List user alerts",
)
async def list_alerts(
    is_active: bool = Query(True, description="Filter by active status."),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[AlertResponse]:
    """
    Get all alerts belonging to the authenticated user.
    """
    query = (
        select(Alert)
        .where(
            Alert.user_id == current_user.id,
            Alert.is_active == is_active,
        )
        .order_by(Alert.created_at.desc())
    )
    result = await db.execute(query)
    alerts = result.scalars().all()
    return [AlertResponse.model_validate(a) for a in alerts]


@router.post(
    "",
    response_model=AlertResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new alert",
)
async def create_alert(
    payload: AlertCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AlertResponse:
    """
    Create a new alert for the authenticated user.
    """
    alert = Alert(
        user_id=current_user.id,
        asset_id=payload.asset_id,
        alert_type=AlertType(payload.alert_type),
        conditions=payload.conditions,
        is_active=True,
    )
    db.add(alert)
    await db.flush()
    await db.refresh(alert)

    logger.info("Alert created for asset %s by user %s", payload.asset_id, current_user.email)
    return AlertResponse.model_validate(alert)


@router.get(
    "/{alert_id}",
    response_model=AlertResponse,
    summary="Get an alert by ID",
)
async def get_alert(
    alert_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AlertResponse:
    """
    Retrieve a specific alert. Must belong to the authenticated user.
    """
    query = select(Alert).where(
        Alert.id == alert_id,
        Alert.user_id == current_user.id,
    )
    result = await db.execute(query)
    alert = result.scalar_one_or_none()

    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found.",
        )

    return AlertResponse.model_validate(alert)


@router.patch(
    "/{alert_id}",
    response_model=AlertResponse,
    summary="Update an alert",
)
async def update_alert(
    alert_id: UUID,
    payload: AlertUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AlertResponse:
    """
    Update an alert's conditions or active state.
    """
    query = select(Alert).where(
        Alert.id == alert_id,
        Alert.user_id == current_user.id,
    )
    result = await db.execute(query)
    alert = result.scalar_one_or_none()

    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found.",
        )

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(alert, field, value)

    await db.flush()
    await db.refresh(alert)
    return AlertResponse.model_validate(alert)


@router.delete(
    "/{alert_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an alert",
)
async def delete_alert(
    alert_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete an alert. Must belong to the authenticated user.
    """
    query = select(Alert).where(
        Alert.id == alert_id,
        Alert.user_id == current_user.id,
    )
    result = await db.execute(query)
    alert = result.scalar_one_or_none()

    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found.",
        )

    await db.delete(alert)
    await db.flush()
    logger.info("Alert deleted: %s by user %s", alert_id, current_user.email)
