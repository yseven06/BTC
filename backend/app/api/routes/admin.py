"""
TradeMinds AI – Admin Panel API

All endpoints under /admin require an admin user (role=admin or
role=super_admin). Founder-only actions (granting roles, deleting users,
deleting assets) require role=super_admin specifically — see
require_super_admin in app.auth.admin.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.auth.admin import require_admin, require_super_admin
from app.backtesting import labels
from app.database import get_db
from app.models.admin_audit import AdminAuditLog
from app.models.asset import Asset, AssetType
from app.models.signal import Signal, SignalOutcome, SignalPerformance
from app.models.subscription import (
    Payment, Subscription, SubscriptionStatus, SubscriptionTier,
)
from app.models.user import User, UserRole
from app.services.scheduler import (
    generate_signal_now, get_job_status, trigger_job_now,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Audit log helper ───────────────────────────────────────────────────────

async def _log_audit(
    db: AsyncSession, actor: User, action: str,
    target_type: Optional[str] = None, target_id: Optional[str] = None,
    detail: Optional[Dict[str, Any]] = None,
) -> None:
    db.add(AdminAuditLog(
        actor_id=actor.id, actor_email=actor.email, action=action,
        target_type=target_type, target_id=target_id, detail=detail or {},
    ))


# ─── Schemas ──────────────────────────────────────────────────────────────────

class AdminUserRow(BaseModel):
    id: UUID
    email: str
    full_name: Optional[str] = None
    provider: str
    is_active: bool
    is_admin: bool
    role: str
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
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    tier: Optional[SubscriptionTier] = None


class AssetCreate(BaseModel):
    symbol: str
    name: str
    asset_type: AssetType
    market: Optional[str] = None


class AssetUpdate(BaseModel):
    name: Optional[str] = None
    market: Optional[str] = None
    is_active: Optional[bool] = None


class SignalGenerateRequest(BaseModel):
    symbol: str
    timeframe: str = "1h"


class BulkCleanRequest(BaseModel):
    min_confidence: float = 40.0
    market: Optional[str] = None


class BulkDeleteClosedRequest(BaseModel):
    outcome: Optional[str] = None       # win, loss, breakeven, expired — None = any closed outcome
    signal_type: Optional[str] = None   # e.g. "hold" to clear out HOLD noise specifically
    older_than_days: Optional[int] = None
    market: Optional[str] = None


# ─── Platform stats ───────────────────────────────────────────────────────────

@router.get("/stats", response_model=AdminStats, summary="Platform stats")
async def admin_stats(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> AdminStats:
    # Was 12 sequential round-trips (one COUNT per stat) — under load (e.g.
    # while the signal-generation sweeps are running) that routinely blew
    # past apiFetch's 8s abort timeout and showed a false "backend down"
    # error even though every query eventually succeeded. Collapsed into
    # one aggregate query per table.
    user_row = (await db.execute(
        select(
            func.count(User.id).label("total"),
            func.sum(case((User.is_active == True, 1), else_=0)).label("active"),
            func.sum(case((User.is_admin == True, 1), else_=0)).label("admins"),
        )
    )).one()
    total_users, active_users, admin_count = user_row.total or 0, user_row.active or 0, user_row.admins or 0

    paying = (await db.execute(
        select(func.count(Subscription.id))
        .where(Subscription.tier != SubscriptionTier.FREE)
        .where(Subscription.status == SubscriptionStatus.ACTIVE)
    )).scalar_one()

    signal_row = (await db.execute(
        select(
            func.count(Signal.id).label("total"),
            func.sum(case((Signal.is_active == True, 1), else_=0)).label("active"),
        )
    )).one()
    total_signals, active_signals = signal_row.total or 0, signal_row.active or 0

    total_assets = (await db.execute(select(func.count(Asset.id)))).scalar_one()

    rev_res = await db.execute(select(func.coalesce(func.sum(Payment.amount), 0)))
    total_revenue = float(rev_res.scalar_one())

    perf_row = (await db.execute(
        select(
            func.sum(case((SignalPerformance.outcome == SignalOutcome.WIN, 1), else_=0)).label("wins"),
            func.sum(case((SignalPerformance.outcome == SignalOutcome.LOSS, 1), else_=0)).label("losses"),
            func.sum(case((SignalPerformance.outcome == SignalOutcome.BREAKEVEN, 1), else_=0)).label("be"),
        )
    )).one()
    wins, losses, be = perf_row.wins or 0, perf_row.losses or 0, perf_row.be or 0
    resolved = wins + losses + be
    win_rate = round((wins / resolved * 100), 1) if resolved > 0 else 0.0

    return AdminStats(
        total_users=total_users, active_users=active_users, admin_count=admin_count,
        paying_users=paying, total_signals=total_signals, active_signals=active_signals,
        total_assets=total_assets, total_revenue_usd=total_revenue, win_rate=win_rate,
    )


# ─── User management ──────────────────────────────────────────────────────────

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
            id=u.id, email=u.email, full_name=u.full_name, provider=u.provider.value,
            is_active=u.is_active, is_admin=bool(getattr(u, "is_admin", False)),
            role=(u.role.value if getattr(u, "role", None) else UserRole.USER.value),
            created_at=u.created_at.isoformat(),
            tier=(s.tier.value if s else "free"),
            sub_status=(s.status.value if s else None),
            sub_period_end=(s.current_period_end.isoformat() if s and s.current_period_end else None),
        ))

    return {"items": [i.model_dump() for i in items], "total": total, "page": page, "page_size": page_size}


@router.patch("/users/{user_id}", summary="Update user (admin)")
async def update_user(
    user_id: UUID,
    payload: UserAdminUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Dict[str, Any]:
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")

    # Role changes are founder-only — a regular admin can't grant itself or
    # anyone else admin/super_admin rights, and can't demote the last super admin.
    if payload.role is not None and payload.role != user.role:
        if admin.role != UserRole.SUPER_ADMIN:
            raise HTTPException(status_code=403, detail="Rol değiştirmek için kurucu yetkisi gereklidir.")
        if user.role == UserRole.SUPER_ADMIN and payload.role != UserRole.SUPER_ADMIN:
            count_res = await db.execute(select(func.count(User.id)).where(User.role == UserRole.SUPER_ADMIN))
            if count_res.scalar_one() <= 1:
                raise HTTPException(status_code=400, detail="Sistemde en az bir kurucu (super admin) kalmalı.")
        old_role = user.role.value if user.role else "user"
        user.role = payload.role
        user.is_admin = payload.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)
        await _log_audit(db, admin, "user.role_change", "user", str(user.id),
                          {"email": user.email, "from": old_role, "to": payload.role.value})

    if payload.is_active is not None and payload.is_active != user.is_active:
        user.is_active = payload.is_active
        await _log_audit(db, admin, "user.active_toggle", "user", str(user.id),
                          {"email": user.email, "is_active": payload.is_active})

    if payload.tier is not None:
        sub_res = await db.execute(select(Subscription).where(Subscription.user_id == user.id))
        sub = sub_res.scalar_one_or_none()
        old_tier = sub.tier.value if sub else "free"
        if sub is None:
            sub = Subscription(user_id=user.id, tier=payload.tier, status=SubscriptionStatus.ACTIVE)
            db.add(sub)
        else:
            sub.tier = payload.tier
            sub.status = SubscriptionStatus.ACTIVE
        if old_tier != payload.tier.value:
            await _log_audit(db, admin, "user.tier_change", "user", str(user.id),
                              {"email": user.email, "from": old_tier, "to": payload.tier.value})

    await db.commit()
    return {"status": "ok", "user_id": str(user.id)}


@router.delete("/users/{user_id}", summary="Delete user (founder only)")
async def delete_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_super_admin),
) -> Dict[str, str]:
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Kendi hesabınızı silemezsiniz.")
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
    await _log_audit(db, admin, "user.delete", "user", str(user_id), {"email": user.email})
    await db.delete(user)
    await db.commit()
    return {"status": "deleted", "user_id": str(user_id)}


# ─── Signal moderation ─────────────────────────────────────────────────────────

@router.get("/signals", summary="List signals for moderation (admin)")
async def admin_list_signals(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
    q: Optional[str] = Query(None, description="Symbol search"),
    only_active: bool = Query(False),
    min_confidence: Optional[float] = Query(None),
    max_confidence: Optional[float] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    query = select(Signal).join(Asset)
    if q:
        query = query.where(Asset.symbol.ilike(f"%{q.upper()}%"))
    if only_active:
        query = query.where(Signal.is_active == True)
    if min_confidence is not None:
        query = query.where(Signal.confidence_score >= min_confidence)
    if max_confidence is not None:
        query = query.where(Signal.confidence_score <= max_confidence)

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    offset = (page - 1) * page_size
    query = (
        query.options(joinedload(Signal.asset), joinedload(Signal.performance))
        .order_by(Signal.generated_at.desc()).offset(offset).limit(page_size)
    )
    result = await db.execute(query)
    signals = result.unique().scalars().all()

    items = []
    for s in signals:
        items.append({
            "id": str(s.id),
            "symbol": s.asset.symbol if s.asset else "?",
            "signal_type": s.signal_type.value,
            "confidence_score": float(s.confidence_score),
            "timeframe": s.timeframe.value,
            "is_active": s.is_active,
            "admin_invalidated": s.admin_invalidated,
            "generated_at": s.generated_at.isoformat(),
            "outcome": s.performance.outcome.value if s.performance else "active",
        })

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/signals/{signal_id}/invalidate", summary="Invalidate a signal (admin)")
async def invalidate_signal(
    signal_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Dict[str, str]:
    """Hide a bad/wrong signal from users without deleting history. Sets
    is_active=False and closes its performance as EXPIRED if still open."""
    res = await db.execute(
        select(Signal).where(Signal.id == signal_id).options(joinedload(Signal.performance))
    )
    signal = res.unique().scalar_one_or_none()
    if signal is None:
        raise HTTPException(status_code=404, detail="Sinyal bulunamadı.")

    from datetime import datetime, timezone
    signal.is_active = False
    signal.admin_invalidated = True
    perf = signal.performance
    if perf and perf.outcome == SignalOutcome.ACTIVE:
        perf.outcome = SignalOutcome.EXPIRED
        perf.is_expired = True
        perf.closed_at = datetime.now(timezone.utc)
        # F1-d: who resolved it, under which semantics. Telemetry only — until
        # now this row was indistinguishable from a HOLD expiry on its own.
        perf.resolution_source = labels.RES_SRC_ADMIN_INVALIDATE
        perf.resolution_version = labels.RESOLUTION_SEMANTICS_VERSION

    await _log_audit(db, admin, "signal.invalidate", "signal", str(signal_id),
                      {"symbol": signal.asset.symbol if signal.asset else None})
    await db.commit()
    return {"status": "invalidated", "signal_id": str(signal_id)}


@router.delete("/signals/{signal_id}", summary="Permanently delete a closed signal (founder only)")
async def admin_delete_signal(
    signal_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_super_admin),
) -> Dict[str, str]:
    """Hard-delete a single signal and its performance row (cascade). Active
    signals must be invalidated first — deleting a live trade plan out from
    under a user is never the right move, only history cleanup is."""
    res = await db.execute(select(Signal).options(joinedload(Signal.asset)).where(Signal.id == signal_id))
    signal = res.unique().scalar_one_or_none()
    if signal is None:
        raise HTTPException(status_code=404, detail="Sinyal bulunamadı.")
    if signal.is_active:
        raise HTTPException(status_code=400, detail="Aktif sinyaller silinemez — önce geçersiz kılın.")

    await _log_audit(db, admin, "signal.delete", "signal", str(signal_id),
                      {"symbol": signal.asset.symbol if signal.asset else None})
    await db.delete(signal)
    await db.commit()
    return {"status": "deleted", "signal_id": str(signal_id)}


@router.post("/signals/bulk-clean", summary="Bulk-invalidate low-quality active signals (admin)")
async def bulk_clean_signals(
    payload: BulkCleanRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Dict[str, Any]:
    from datetime import datetime, timezone

    query = (
        select(Signal)
        .join(Asset)
        .where(Signal.is_active == True)
        .where(Signal.confidence_score < payload.min_confidence)
        .options(joinedload(Signal.performance), joinedload(Signal.asset))
    )
    if payload.market:
        query = query.where(Asset.asset_type == payload.market)

    result = await db.execute(query)
    signals = result.unique().scalars().all()

    now = datetime.now(timezone.utc)
    for s in signals:
        s.is_active = False
        s.admin_invalidated = True
        if s.performance and s.performance.outcome == SignalOutcome.ACTIVE:
            s.performance.outcome = SignalOutcome.EXPIRED
            s.performance.is_expired = True
            s.performance.closed_at = now
            # F1-d: who resolved it, under which semantics. Telemetry only.
            s.performance.resolution_source = labels.RES_SRC_ADMIN_BULK_CLEAN
            s.performance.resolution_version = labels.RESOLUTION_SEMANTICS_VERSION

    await _log_audit(db, admin, "signal.bulk_clean", "signal", None,
                      {"count": len(signals), "min_confidence": payload.min_confidence, "market": payload.market})
    await db.commit()
    return {"status": "ok", "invalidated_count": len(signals)}


@router.post("/signals/generate", summary="Force-generate a signal now (admin)")
async def admin_generate_signal(
    payload: SignalGenerateRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Dict[str, str]:
    res = await db.execute(select(Asset).where(Asset.symbol == payload.symbol.upper()))
    asset = res.scalar_one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="Varlık bulunamadı.")

    await generate_signal_now(asset.symbol, asset.asset_type.value, payload.timeframe)
    await _log_audit(db, admin, "signal.force_generate", "asset", str(asset.id),
                      {"symbol": asset.symbol, "timeframe": payload.timeframe})
    await db.commit()
    return {"status": "generated", "symbol": asset.symbol, "timeframe": payload.timeframe}


@router.post("/signals/bulk-delete-closed", summary="Permanently delete closed signals matching filters (founder only)")
async def admin_bulk_delete_closed(
    payload: BulkDeleteClosedRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_super_admin),
) -> Dict[str, Any]:
    """Wipe historical noise (e.g. thousands of HOLD signals) permanently.
    Only ever touches is_active=False rows — never an open trade plan."""
    query = (
        select(Signal)
        .join(Asset)
        .outerjoin(SignalPerformance)
        .where(Signal.is_active == False)
    )
    if payload.outcome:
        query = query.where(SignalPerformance.outcome == payload.outcome)
    if payload.signal_type:
        query = query.where(Signal.signal_type == payload.signal_type)
    if payload.market:
        query = query.where(Asset.asset_type == payload.market)
    if payload.older_than_days:
        from datetime import datetime, timedelta, timezone
        cutoff = datetime.now(timezone.utc) - timedelta(days=payload.older_than_days)
        query = query.where(Signal.generated_at < cutoff)

    result = await db.execute(query.with_only_columns(Signal.id))
    ids = result.scalars().all()
    count = len(ids)

    # A row-by-row ORM delete() issues one DELETE per signal (plus cascade
    # checks) — with thousands of closed HOLD signals this routinely blew
    # past the frontend's 8s request timeout. SignalPerformance has an
    # ON DELETE CASCADE FK, so a single bulk DELETE is both correct and
    # orders of magnitude faster.
    if ids:
        await db.execute(delete(Signal).where(Signal.id.in_(ids)))

    await _log_audit(db, admin, "signal.bulk_delete_closed", "signal", None,
                      {"count": count, **payload.model_dump(exclude_none=True)})
    await db.commit()
    return {"status": "ok", "deleted_count": count}


# ─── Asset management ──────────────────────────────────────────────────────────

@router.get("/assets", summary="List assets (admin)")
async def admin_list_assets(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
    q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=300),
) -> Dict[str, Any]:
    query = select(Asset)
    if q:
        query = query.where(Asset.symbol.ilike(f"%{q.upper()}%"))
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    offset = (page - 1) * page_size
    res = await db.execute(query.order_by(Asset.symbol).offset(offset).limit(page_size))
    assets = res.scalars().all()
    items = [{
        "id": str(a.id), "symbol": a.symbol, "name": a.name,
        "asset_type": a.asset_type.value, "market": a.market, "is_active": a.is_active,
    } for a in assets]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/assets", summary="Add a new tracked asset (admin)")
async def admin_create_asset(
    payload: AssetCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Dict[str, str]:
    existing = await db.execute(select(Asset).where(Asset.symbol == payload.symbol.upper()))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="Bu sembol zaten kayıtlı.")

    asset = Asset(
        symbol=payload.symbol.upper(), name=payload.name,
        asset_type=payload.asset_type, market=payload.market, is_active=True,
    )
    db.add(asset)
    await db.flush()
    await _log_audit(db, admin, "asset.create", "asset", str(asset.id), {"symbol": asset.symbol})
    await db.commit()
    return {"status": "created", "symbol": asset.symbol}


@router.patch("/assets/{asset_id}", summary="Update an asset (admin)")
async def admin_update_asset(
    asset_id: UUID,
    payload: AssetUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Dict[str, str]:
    res = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = res.scalar_one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="Varlık bulunamadı.")

    changes: Dict[str, Any] = {}
    if payload.name is not None:
        asset.name = payload.name
        changes["name"] = payload.name
    if payload.market is not None:
        asset.market = payload.market
        changes["market"] = payload.market
    if payload.is_active is not None:
        asset.is_active = payload.is_active
        changes["is_active"] = payload.is_active

    if changes:
        await _log_audit(db, admin, "asset.update", "asset", str(asset.id),
                          {"symbol": asset.symbol, **changes})
    await db.commit()
    return {"status": "ok", "symbol": asset.symbol}


@router.delete("/assets/{asset_id}", summary="Delete an asset (founder only)")
async def admin_delete_asset(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_super_admin),
) -> Dict[str, str]:
    res = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = res.scalar_one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="Varlık bulunamadı.")
    await _log_audit(db, admin, "asset.delete", "asset", str(asset_id), {"symbol": asset.symbol})
    await db.delete(asset)
    await db.commit()
    return {"status": "deleted", "symbol": asset.symbol}


# ─── System & scheduler ─────────────────────────────────────────────────────────

@router.get("/system/jobs", summary="Scheduler job status (admin)")
async def admin_job_status(
    _admin: User = Depends(require_admin),
) -> Dict[str, Any]:
    return {"jobs": get_job_status()}


@router.post("/system/jobs/{job_id}/trigger", summary="Manually trigger a job now (admin)")
async def admin_trigger_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Dict[str, Any]:
    started = await trigger_job_now(job_id)
    if not started:
        raise HTTPException(status_code=404, detail=f"Bilinmeyen iş: {job_id}")
    await _log_audit(db, admin, "system.job_trigger", "job", job_id, {})
    await db.commit()
    return {"status": "started", "job_id": job_id}


# ─── Audit log ──────────────────────────────────────────────────────────────────

@router.get("/audit-log", summary="Admin audit log (admin)")
async def admin_audit_log(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
    action: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    query = select(AdminAuditLog)
    if action:
        query = query.where(AdminAuditLog.action == action)

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    offset = (page - 1) * page_size
    res = await db.execute(
        query.order_by(AdminAuditLog.created_at.desc()).offset(offset).limit(page_size)
    )
    rows = res.scalars().all()
    items = [{
        "id": str(r.id), "actor_email": r.actor_email, "action": r.action,
        "target_type": r.target_type, "target_id": r.target_id,
        "detail": r.detail, "created_at": r.created_at.isoformat(),
    } for r in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size}
