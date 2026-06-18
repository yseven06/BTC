"""
TradeMinds AI – Tier-Based Feature Gating

Defines per-tier feature limits and dependency-injectable helpers used by
API routes to enforce subscription gates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, get_optional_user
from app.database import get_db
from app.models.subscription import Subscription, SubscriptionStatus, SubscriptionTier
from app.models.user import User


@dataclass
class TierLimits:
    """Feature limits and capabilities for a subscription tier."""
    daily_signal_limit: int                 # -1 = unlimited
    can_view_engine_details: bool
    can_use_telegram: bool
    can_use_backtest: bool
    can_view_strategy_lab: bool
    can_view_symbol_analysis: bool
    can_use_api: bool
    backtest_runs_per_day: int              # -1 = unlimited
    label: str


TIER_LIMITS = {
    SubscriptionTier.FREE: TierLimits(
        daily_signal_limit=3,
        can_view_engine_details=False,
        can_use_telegram=False,
        can_use_backtest=False,
        can_view_strategy_lab=False,
        can_view_symbol_analysis=False,
        can_use_api=False,
        backtest_runs_per_day=0,
        label="Ücretsiz",
    ),
    SubscriptionTier.PRO: TierLimits(
        daily_signal_limit=-1,
        can_view_engine_details=True,
        can_use_telegram=True,
        can_use_backtest=True,
        can_view_strategy_lab=True,
        can_view_symbol_analysis=True,
        can_use_api=False,
        backtest_runs_per_day=20,
        label="Pro",
    ),
    SubscriptionTier.PREMIUM: TierLimits(
        daily_signal_limit=-1,
        can_view_engine_details=True,
        can_use_telegram=True,
        can_use_backtest=True,
        can_view_strategy_lab=True,
        can_view_symbol_analysis=True,
        can_use_api=True,
        backtest_runs_per_day=-1,
        label="Premium",
    ),
}


async def _fetch_subscription(db: AsyncSession, user_id) -> Optional[Subscription]:
    res = await db.execute(select(Subscription).where(Subscription.user_id == user_id))
    return res.scalar_one_or_none()


def _effective_tier(sub: Optional[Subscription]) -> SubscriptionTier:
    """Return the effective tier — Free if no sub, expired, or canceled."""
    if sub is None:
        return SubscriptionTier.FREE
    if sub.status not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL):
        return SubscriptionTier.FREE
    if sub.current_period_end is not None:
        period_end = sub.current_period_end
        # Make sure both sides of the comparison are timezone-aware
        if period_end.tzinfo is None:
            period_end = period_end.replace(tzinfo=timezone.utc)
        if period_end < datetime.now(timezone.utc):
            return SubscriptionTier.FREE
    return sub.tier


async def get_user_tier(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionTier:
    """Get the effective tier of the currently authenticated user.
    Admins always get Premium-level access."""
    if getattr(current_user, "is_admin", False):
        return SubscriptionTier.PREMIUM
    sub = await _fetch_subscription(db, current_user.id)
    return _effective_tier(sub)


async def get_user_limits(
    tier: SubscriptionTier = Depends(get_user_tier),
) -> TierLimits:
    """Get the effective feature limits for the current user."""
    return TIER_LIMITS[tier]


async def get_user_tier_optional(
    current_user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionTier:
    """Like get_user_tier but returns FREE when not authenticated (no 401).
    Admins always get Premium-level access."""
    if current_user is None:
        return SubscriptionTier.FREE
    if getattr(current_user, "is_admin", False):
        return SubscriptionTier.PREMIUM
    sub = await _fetch_subscription(db, current_user.id)
    return _effective_tier(sub)


def require_feature(feature: str):
    """
    Dependency factory: enforces that the current user's tier has `feature`
    set to True on TierLimits. Raises 403 with an upgrade hint otherwise.
    """
    async def _check(limits: TierLimits = Depends(get_user_limits)) -> TierLimits:
        if not getattr(limits, feature, False):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "error": "upgrade_required",
                    "feature": feature,
                    "current_tier": limits.label,
                    "message": "Bu özelliği kullanmak için Pro veya üzeri abonelik gereklidir.",
                },
            )
        return limits
    return _check
