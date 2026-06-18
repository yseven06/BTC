"""
TradeMinds AI – Admin Panel API

All endpoints under /admin require an admin user (is_admin=True).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.admin import require_admin
from app.database import get_db
from app.models.asset import Asset
from app.models.signal import Signal, SignalOutcome, SignalPerformance
from app.models.subscription import (
    Payment, Subscription, SubscriptionStatus, SubscriptionTier,
)
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Schemas ──────────────────────────────────────────────────────────────────

class AdminUserRow(BaseModel):
    id: UUID
    email: str
    full_name: Optional[str] = None
    provider: str
    is_active: bool
    is_admin: bool
    created_at: str
    tier: str = "free"
    sub_status: Optional[str] = None
    sub_period_end: Optional[str] = None


class AdminStats(BaseModel):
    total_users: int
    active_users: int
    admin_count: int
    paying_users: int
    total_signals: int
    active_signals: int
    total_assets: int
    total_revenue_usd: float
    win_rate: float


class UserAdminUpdate(BaseModel):
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None
    tier: Optional[SubscriptionTier] = None


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/stats", response_model=AdminStats, summary="Platform stats")
async def admin_stats(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> AdminStats:
    # Users
    total_users  = (await db.execute(select(func.count(User.id)))).scalar_one()
    active_users = (await db.execute(select(func.count(User.id)).where(User.is_active == True))).scalar_one()
    admin_count  = (await db.execute(select(func.count(User.id)).where(User.is_admin == True))).scalar_one()

    # Paying users
    paying = (await db.execute(
        select(func.count(Subscription.id))
        .where(Subscription.tier != SubscriptionTier.FREE)
        .where(Subscription.status == SubscriptionStatus.ACTIVE)
    )).scalar_one()

    # Signals
    total_signals  = (await db.execute(select(func.count(Signal.id)))).scalar_one()
    active_signals = (await db.execute(select(func.count(Signal.id)).where(Signal.is_active == True))).scalar_one()

    # Assets
    total_assets = (await db.execute(select(func.count(Asset.id)))).scalar_one()

    # Revenue
    rev_res = await db.execute(select(func.coalesce(func.sum(Payment.amount), 0)))
    total_revenue = float(rev_res.scalar_one())

    # Win rate
    wins   = (await db.execute(select(func.count(SignalPerformance.id)).where(SignalPerformance.outcome == SignalOutcome.WIN))).scalar_one()
    losses = (await db.execute(select(func.count(SignalPerformance.id)).where(SignalPerformance.outcome == SignalOutcome.LOSS))).scalar_one()
    be     = (await db.execute(select(func.count(SignalPerformance.id)).where(SignalPerformance.outcome == SignalOutcome.BREAKEVEN))).scalar_one()
    resolved = wins + losses + be
    win_rate = round((wins / resolved * 100), 1) if resolved > 0 else 0.0

    return AdminStats(
        total_users=total_users,
        active_users=active_users,
        admin_count=admin_count,
        paying_users=paying,
        total_signals=total_signals,
        active_signals=active_signals,
        total_assets=total_assets,
        total_revenue_usd=total_revenue,
        win_rate=win_rate,
    )


@router.get("/users", summary="List all users (admin)")
async def list_users(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    q: Optional[str] = Query(None, description="Email/name search"),
) -> Dict[str, Any]:
    base = select(User)
    if q:
        like = f"%{q.lower()}%"
        base = base.where(
            func.lower(User.email).like(like) | func.lower(User.full_name).like(like)
        )

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    offset = (page - 1) * page_size

    res = await db.execute(
        base.order_by(User.created_at.desc()).offset(offset).limit(page_size)
    )
    users = res.scalars().all()

    # Fetch matching subs in one query
    user_ids = [u.id for u in users]
    sub_map = {}
    if user_ids:
        subs_res = await db.execute(select(Subscription).where(Subscription.user_id.in_(user_ids)))
        for s in subs_res.scalars().all():
            sub_map[s.user_id] = s

    items: List[AdminUserRow] = []
    for u in users:
        s = sub_map.get(u.id)
        items.append(AdminUserRow(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            provider=u.provider.value,
            is_active=u.is_active,
            is_admin=bool(getattr(u, "is_admin", False)),
            created_at=u.created_at.isoformat(),
            tier=(s.tier.value if s else "free"),
            sub_status=(s.status.value if s else None),
            sub_period_end=(s.current_period_end.isoformat() if s and s.current_period_end else None),
        ))

    return {
        "items": [i.model_dump() for i in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.patch("/users/{user_id}", summary="Update user (admin)")
async def update_user(
    user_id: UUID,
    payload: UserAdminUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> Dict[str, Any]:
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")

    if payload.is_admin is not None:
        user.is_admin = payload.is_admin
    if payload.is_active is not None:
        user.is_active = payload.is_active

    if payload.tier is not None:
        sub_res = await db.execute(select(Subscription).where(Subscription.user_id == user.id))
        sub = sub_res.scalar_one_or_none()
        if sub is None:
            sub = Subscription(user_id=user.id, tier=payload.tier,
                               status=SubscriptionStatus.ACTIVE)
            db.add(sub)
        else:
            sub.tier = payload.tier
            sub.status = SubscriptionStatus.ACTIVE

    await db.commit()
    return {"status": "ok", "user_id": str(user.id)}


@router.delete("/users/{user_id}", summary="Delete user (admin)")
async def delete_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Dict[str, str]:
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Kendi hesabınızı silemezsiniz.")
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
    await db.delete(user)
    await db.commit()
    return {"status": "deleted", "user_id": str(user_id)}
