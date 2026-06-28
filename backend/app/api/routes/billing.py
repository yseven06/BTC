"""
TradeMinds AI – Billing & Subscription Routes

Endpoints:
  GET  /plans                       — pricing catalog (public)
  GET  /subscription                — current user's subscription
  POST /checkout                    — start a Stripe Checkout session
  POST /cancel                      — cancel at period end
  POST /webhooks/stripe             — Stripe webhook (signature verified)

Stripe is optional: when STRIPE_SECRET_KEY is not configured, the checkout
endpoint returns a mock session url so the UI can still be developed
end-to-end.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.config import get_settings
from app.database import get_db
from app.rate_limit import limiter, CHECKOUT_LIMIT
from app.models.subscription import (
    BillingCycle, Payment, Subscription,
    SubscriptionStatus, SubscriptionTier,
)
from app.models.user import User
from app.subscriptions.plans import (
    get_months, get_plans_payload, get_price,
)
from app.subscriptions.gating import TIER_LIMITS, get_user_tier

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


# ─── Response shapes ──────────────────────────────────────────────────────────

class SubscriptionResponse(BaseModel):
    tier: str
    status: str
    billing_cycle: Optional[str] = None
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool = False


class CheckoutRequest(BaseModel):
    tier: SubscriptionTier
    cycle: BillingCycle


class CheckoutResponse(BaseModel):
    url: str
    session_id: str
    mock: bool = False


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _get_or_create_subscription(db: AsyncSession, user_id) -> Subscription:
    """Fetch the user's subscription row, creating a free-tier default if missing."""
    res = await db.execute(select(Subscription).where(Subscription.user_id == user_id))
    sub = res.scalar_one_or_none()
    if sub is None:
        sub = Subscription(user_id=user_id, tier=SubscriptionTier.FREE,
                           status=SubscriptionStatus.ACTIVE)
        db.add(sub)
        await db.commit()
        await db.refresh(sub)
    return sub


def _to_response(sub: Subscription) -> SubscriptionResponse:
    return SubscriptionResponse(
        tier=sub.tier.value,
        status=sub.status.value,
        billing_cycle=sub.billing_cycle.value if sub.billing_cycle else None,
        current_period_end=sub.current_period_end,
        cancel_at_period_end=sub.cancel_at_period_end,
    )


def _stripe_configured() -> bool:
    return bool(getattr(settings, "STRIPE_SECRET_KEY", ""))


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/plans", summary="Get pricing catalog (public)")
async def list_plans() -> Dict[str, Any]:
    return {"plans": get_plans_payload(), "currency": "USD"}


@router.get("/limits", summary="Get current user's tier limits")
async def my_limits(
    tier: SubscriptionTier = Depends(get_user_tier),
) -> Dict[str, Any]:
    """Returns the feature flags & numerical limits the current user has."""
    lim = TIER_LIMITS[tier]
    return {
        "tier": tier.value,
        "label": lim.label,
        "daily_signal_limit":          lim.daily_signal_limit,
        "can_view_engine_details":     lim.can_view_engine_details,
        "can_use_telegram":            lim.can_use_telegram,
        "can_use_backtest":            lim.can_use_backtest,
        "can_view_strategy_lab":       lim.can_view_strategy_lab,
        "can_view_symbol_analysis":    lim.can_view_symbol_analysis,
        "can_use_api":                 lim.can_use_api,
        "backtest_runs_per_day":       lim.backtest_runs_per_day,
    }


@router.get("/subscription", response_model=SubscriptionResponse, summary="Get current subscription")
async def my_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionResponse:
    sub = await _get_or_create_subscription(db, current_user.id)
    return _to_response(sub)


@router.post("/checkout", response_model=CheckoutResponse, summary="Start checkout session")
@limiter.limit(CHECKOUT_LIMIT)
async def start_checkout(
    request: Request,
    payload: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CheckoutResponse:
    """
    Create a Stripe Checkout session for the chosen tier+cycle.
    Falls back to a mock session when Stripe is not configured.
    """
    if payload.tier == SubscriptionTier.FREE:
        raise HTTPException(status_code=400, detail="Ücretsiz plan için ödeme gerekmez.")

    price = get_price(payload.tier, payload.cycle)
    if price <= 0:
        raise HTTPException(status_code=400, detail="Geçersiz tier/cycle kombinasyonu.")

    # ── Mock mode: no Stripe key configured ──────────────────────────────────
    if not _stripe_configured():
        # Immediately activate the subscription so the UI flow can be tested.
        sub = await _get_or_create_subscription(db, current_user.id)
        now = datetime.now(timezone.utc)
        sub.tier = payload.tier
        sub.status = SubscriptionStatus.ACTIVE
        sub.billing_cycle = payload.cycle
        sub.current_period_start = now
        sub.current_period_end = now + timedelta(days=30 * get_months(payload.cycle))
        sub.cancel_at_period_end = False
        db.add(Payment(
            user_id=current_user.id, amount=price, currency="USD",
            tier=payload.tier, billing_cycle=payload.cycle, method="mock",
            metadata_json={"note": "Mock payment — Stripe not configured."},
        ))
        await db.commit()
        return CheckoutResponse(
            url="/settings?upgraded=1",
            session_id=f"mock_{current_user.id}",
            mock=True,
        )

    # ── Real Stripe path ─────────────────────────────────────────────────────
    try:
        import stripe   # type: ignore
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="Stripe paketi yüklü değil. pip install stripe çalıştırın.",
        )

    stripe.api_key = settings.STRIPE_SECRET_KEY
    success_url = f"{settings.FRONTEND_BASE_URL}/settings?session_id={{CHECKOUT_SESSION_ID}}&upgraded=1"
    cancel_url  = f"{settings.FRONTEND_BASE_URL}/pricing?canceled=1"

    months = get_months(payload.cycle)
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=str(current_user.id),
            customer_email=current_user.email,
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": f"TradeMinds {payload.tier.value.upper()} – {months} ay",
                    },
                    "unit_amount": int(price * 100),
                },
                "quantity": 1,
            }],
            metadata={
                "user_id": str(current_user.id),
                "tier": payload.tier.value,
                "cycle": payload.cycle.value,
                "months": str(months),
            },
        )
        return CheckoutResponse(url=session.url, session_id=session.id, mock=False)
    except Exception as exc:
        logger.error("Stripe checkout failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Stripe hatası: {exc}")


@router.post("/cancel", response_model=SubscriptionResponse, summary="Cancel at period end")
async def cancel_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionResponse:
    sub = await _get_or_create_subscription(db, current_user.id)
    if sub.tier == SubscriptionTier.FREE:
        raise HTTPException(status_code=400, detail="Ücretsiz planda iptal yok.")
    sub.cancel_at_period_end = True
    await db.commit()
    await db.refresh(sub)
    return _to_response(sub)


@router.post("/webhooks/stripe", summary="Stripe webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> Dict[str, str]:
    """Handle Stripe events (checkout.session.completed). Verifies signature."""
    if not _stripe_configured():
        raise HTTPException(status_code=503, detail="Stripe yapılandırılmamış.")

    try:
        import stripe   # type: ignore
    except ImportError:
        raise HTTPException(status_code=500, detail="stripe paketi yüklü değil.")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception as exc:
        logger.warning("Stripe webhook signature invalid: %s", exc)
        raise HTTPException(status_code=400, detail="invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        meta = session.get("metadata") or {}
        user_id = meta.get("user_id")
        tier_str = meta.get("tier")
        cycle_str = meta.get("cycle")
        if not (user_id and tier_str and cycle_str):
            return {"status": "ignored"}

        tier  = SubscriptionTier(tier_str)
        cycle = BillingCycle(cycle_str)
        months = int(meta.get("months", get_months(cycle)))

        sub = await _get_or_create_subscription(db, user_id)
        now = datetime.now(timezone.utc)
        sub.tier = tier
        sub.status = SubscriptionStatus.ACTIVE
        sub.billing_cycle = cycle
        sub.current_period_start = now
        sub.current_period_end = now + timedelta(days=30 * months)
        sub.cancel_at_period_end = False
        sub.stripe_customer_id = session.get("customer")
        sub.stripe_subscription_id = session.get("subscription")

        db.add(Payment(
            user_id=user_id,
            amount=session.get("amount_total", 0) / 100,
            currency=(session.get("currency") or "usd").upper(),
            tier=tier, billing_cycle=cycle, method="stripe",
            stripe_session_id=session.get("id"),
            stripe_payment_intent_id=session.get("payment_intent"),
        ))
        await db.commit()
        logger.info("Subscription activated for user %s → %s/%s", user_id, tier_str, cycle_str)

    return {"status": "ok"}
