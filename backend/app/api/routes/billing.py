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
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.admin import require_admin
from app.auth.dependencies import get_current_user
from app.challenge import require_challenge
from app.config import get_settings
from app.database import get_db
from app.rate_limit import limiter, CHECKOUT_LIMIT
from app.models.subscription import (
    BillingCycle, Payment, StripeEvent, Subscription,
    SubscriptionStatus, SubscriptionTier,
)
from app.models.user import User
from app.subscriptions.plans import (
    get_months, get_plans_payload, get_price, get_stripe_recurring,
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


class PaymentResponse(BaseModel):
    id: str
    amount: float
    currency: str
    tier: str
    billing_cycle: Optional[str] = None
    method: str
    stripe_invoice_id: Optional[str] = None
    paid_at: datetime


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
    _challenge: None = Depends(require_challenge("checkout", allow_role_bypass=True)),
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

    # Re-buy guard: if the user already has an ACTIVE subscription on the SAME
    # tier+cycle (and it isn't set to end), don't spin up a duplicate — they
    # should manage the existing one. A different tier/cycle is a plan change → allowed.
    existing = await _get_or_create_subscription(db, current_user.id)
    if (
        existing.status == SubscriptionStatus.ACTIVE
        and existing.tier == payload.tier
        and existing.billing_cycle == payload.cycle
        and not existing.cancel_at_period_end
    ):
        raise HTTPException(
            status_code=409,
            detail="Zaten bu plana etkin bir aboneliğiniz var. Değişiklik için mevcut aboneliğinizi yönetebilirsiniz.",
        )

    # ── No Stripe key configured ─────────────────────────────────────────────
    if not _stripe_configured():
        # SECURITY (BP1): a missing Stripe config must NEVER grant a paid tier
        # without payment. The self-activation below is a DEV-ONLY convenience to
        # exercise the UI flow locally; in production (DEBUG=false) we hard-fail
        # instead, so an unconfigured prod can't hand out free Premium.
        if not settings.DEBUG:
            raise HTTPException(
                status_code=503,
                detail="Ödeme sistemi şu anda kullanılamıyor. Lütfen daha sonra tekrar deneyin.",
            )
        # Dev-only: immediately activate the subscription so the UI flow can be tested.
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
    common_meta = {
        "user_id": str(current_user.id),
        "tier": payload.tier.value,
        "cycle": payload.cycle.value,
        "months": str(months),
    }
    # Reuse the user's existing Stripe Customer when we have one (avoids duplicate
    # customers); otherwise let Checkout create one from the email.
    customer_kwargs = (
        {"customer": existing.stripe_customer_id}
        if existing.stripe_customer_id
        else {"customer_email": current_user.email}
    )
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=str(current_user.id),
            allow_promotion_codes=True,   # future coupon / discount-code support
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": f"TradeMinds {payload.tier.value.upper()} – {months} ay",
                    },
                    "unit_amount": int(price * 100),
                    "recurring": get_stripe_recurring(payload.cycle),
                },
                "quantity": 1,
            }],
            # Metadata on BOTH the session (checkout.session.completed) and the
            # Subscription object (so renewal invoice/subscription webhooks carry it).
            metadata=common_meta,
            subscription_data={"metadata": common_meta},
            **customer_kwargs,
        )
        return CheckoutResponse(url=session.url, session_id=session.id, mock=False)
    except Exception as exc:
        logger.error("Stripe checkout failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail="Ödeme sağlayıcısıyla iletişim kurulamadı. Lütfen tekrar deneyin.",
        )


@router.post("/cancel", response_model=SubscriptionResponse, summary="Cancel at period end")
async def cancel_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionResponse:
    sub = await _get_or_create_subscription(db, current_user.id)
    if sub.tier == SubscriptionTier.FREE:
        raise HTTPException(status_code=400, detail="Ücretsiz planda iptal yok.")

    if _stripe_configured() and sub.stripe_subscription_id:
        # Real cancel: schedule cancellation at period end on Stripe (source of
        # truth). Sync our row from Stripe's response; the customer.subscription
        # .updated webhook re-applies the same state idempotently.
        try:
            import stripe   # type: ignore
            stripe.api_key = settings.STRIPE_SECRET_KEY
            updated = stripe.Subscription.modify(
                sub.stripe_subscription_id, cancel_at_period_end=True
            )
            _apply_subscription_object(sub, updated)
        except Exception as exc:
            logger.error("Stripe cancel failed: %s", exc, exc_info=True)
            raise HTTPException(
                status_code=502,
                detail="Abonelik iptali sırasında ödeme sağlayıcısına ulaşılamadı. Lütfen tekrar deneyin.",
            )
    else:
        # Dev / mock (no Stripe configured or no Stripe subscription): local flag only.
        sub.cancel_at_period_end = True

    await db.commit()
    await db.refresh(sub)
    return _to_response(sub)


@router.get("/payments", summary="Current user's payment / invoice history")
async def my_payments(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[PaymentResponse]:
    """Payment & invoice history for the current user (newest first). Refund rows
    appear with a negative amount and method='refund'."""
    res = await db.execute(
        select(Payment).where(Payment.user_id == current_user.id).order_by(Payment.paid_at.desc())
    )
    return [
        PaymentResponse(
            id=str(p.id), amount=float(p.amount), currency=p.currency, tier=p.tier.value,
            billing_cycle=p.billing_cycle.value if p.billing_cycle else None,
            method=p.method, stripe_invoice_id=p.stripe_invoice_id, paid_at=p.paid_at,
        )
        for p in res.scalars().all()
    ]


@router.post("/refund/{payment_id}", summary="Refund a payment (admin)")
async def refund_payment(
    payment_id: uuid.UUID,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Admin-initiated Stripe refund of a payment; records a reversal Payment row
    (negative amount, method='refund'). Money movement is performed by Stripe."""
    res = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = res.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Ödeme bulunamadı.")
    if float(payment.amount) <= 0:
        raise HTTPException(status_code=400, detail="Bu kayıt iade edilemez.")
    if not payment.stripe_payment_intent_id:
        raise HTTPException(status_code=400, detail="Bu ödeme için Stripe ödeme kaydı yok; iade edilemez.")
    if not _stripe_configured():
        raise HTTPException(status_code=503, detail="Stripe yapılandırılmamış.")
    try:
        import stripe   # type: ignore
        stripe.api_key = settings.STRIPE_SECRET_KEY
        refund = stripe.Refund.create(payment_intent=payment.stripe_payment_intent_id)
    except Exception as exc:
        logger.error("Stripe refund failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail="İade sırasında ödeme sağlayıcısına ulaşılamadı.")
    db.add(Payment(
        user_id=payment.user_id, amount=-abs(float(payment.amount)), currency=payment.currency,
        tier=payment.tier, billing_cycle=payment.billing_cycle, method="refund",
        stripe_payment_intent_id=payment.stripe_payment_intent_id,
        stripe_invoice_id=payment.stripe_invoice_id,
        metadata_json={"refund_id": getattr(refund, "id", None), "original_payment_id": str(payment.id)},
    ))
    await db.commit()
    return {"status": "refunded", "refund_id": getattr(refund, "id", None)}


# ─── Stripe webhook helpers (Stripe = single source of truth) ─────────────────

# Stripe subscription.status → our SubscriptionStatus.
_STRIPE_STATUS_MAP = {
    "active": SubscriptionStatus.ACTIVE,
    "trialing": SubscriptionStatus.TRIAL,
    "past_due": SubscriptionStatus.PAST_DUE,
    "unpaid": SubscriptionStatus.PAST_DUE,
    "canceled": SubscriptionStatus.CANCELED,
    "incomplete": SubscriptionStatus.PAST_DUE,
    "incomplete_expired": SubscriptionStatus.EXPIRED,
}


def _ts(unix) -> Optional[datetime]:
    return datetime.fromtimestamp(unix, tz=timezone.utc) if unix else None


def _apply_subscription_object(sub: Subscription, obj: Dict[str, Any]) -> None:
    """Mirror a Subscription row from a Stripe Subscription object (created/updated/
    deleted). Pure state-sync — Stripe is authoritative."""
    meta = obj.get("metadata") or {}
    if meta.get("tier"):
        try:
            sub.tier = SubscriptionTier(meta["tier"])
        except ValueError:
            pass
    if meta.get("cycle"):
        try:
            sub.billing_cycle = BillingCycle(meta["cycle"])
        except ValueError:
            pass
    sub.status = _STRIPE_STATUS_MAP.get(obj.get("status"), sub.status)
    sub.current_period_start = _ts(obj.get("current_period_start")) or sub.current_period_start
    sub.current_period_end = _ts(obj.get("current_period_end")) or sub.current_period_end
    sub.cancel_at_period_end = bool(obj.get("cancel_at_period_end"))
    if obj.get("id"):
        sub.stripe_subscription_id = obj["id"]
    if obj.get("customer"):
        sub.stripe_customer_id = obj["customer"]
    # Fully ended → drop to FREE (access already governed by status/period_end).
    if sub.status in (SubscriptionStatus.CANCELED, SubscriptionStatus.EXPIRED):
        sub.tier = SubscriptionTier.FREE
        sub.cancel_at_period_end = False


async def _find_subscription(db, *, user_id=None, stripe_subscription_id=None):
    if user_id:
        res = await db.execute(select(Subscription).where(Subscription.user_id == user_id))
        sub = res.scalar_one_or_none()
        if sub:
            return sub
    if stripe_subscription_id:
        res = await db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == stripe_subscription_id)
        )
        return res.scalar_one_or_none()
    return None


async def _handle_checkout_completed(db, session: Dict[str, Any]) -> None:
    """First activation after a successful Checkout (subscription mode). Payment rows
    are recorded by invoice.paid (which fires for the first charge and every renewal)."""
    meta = session.get("metadata") or {}
    user_id = meta.get("user_id")
    if not user_id:
        return
    sub = await _find_subscription(
        db, user_id=user_id, stripe_subscription_id=session.get("subscription")
    ) or await _get_or_create_subscription(db, user_id)
    if meta.get("tier"):
        try:
            sub.tier = SubscriptionTier(meta["tier"])
        except ValueError:
            pass
    if meta.get("cycle"):
        try:
            sub.billing_cycle = BillingCycle(meta["cycle"])
        except ValueError:
            pass
    sub.status = SubscriptionStatus.ACTIVE
    sub.cancel_at_period_end = False
    if session.get("customer"):
        sub.stripe_customer_id = session["customer"]
    if session.get("subscription"):
        sub.stripe_subscription_id = session["subscription"]
    now = datetime.now(timezone.utc)
    sub.current_period_start = sub.current_period_start or now
    if not sub.current_period_end or sub.current_period_end < now:
        months = int(meta.get("months") or (get_months(sub.billing_cycle) if sub.billing_cycle else 1))
        sub.current_period_end = now + timedelta(days=30 * months)


async def _handle_invoice_paid(db, invoice: Dict[str, Any]) -> None:
    """First/recurring payment succeeded → ACTIVE + record a Payment row."""
    sub = await _find_subscription(db, stripe_subscription_id=invoice.get("subscription"))
    if not sub:
        return
    sub.status = SubscriptionStatus.ACTIVE
    db.add(Payment(
        user_id=sub.user_id,
        amount=(invoice.get("amount_paid") or 0) / 100.0,
        currency=(invoice.get("currency") or "usd").upper(),
        tier=sub.tier,
        billing_cycle=sub.billing_cycle or BillingCycle.MONTHLY,
        method="stripe",
        stripe_invoice_id=invoice.get("id"),
        stripe_payment_intent_id=invoice.get("payment_intent"),
    ))


async def _handle_invoice_failed(db, invoice: Dict[str, Any]) -> None:
    sub = await _find_subscription(db, stripe_subscription_id=invoice.get("subscription"))
    if sub:
        sub.status = SubscriptionStatus.PAST_DUE


@router.post("/webhooks/stripe", summary="Stripe webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> Dict[str, str]:
    """Handle Stripe subscription lifecycle events. Verifies signature; **idempotent**
    (each event id applied at most once). Stripe is the single source of truth —
    subscription status is updated ONLY here, never from the client."""
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

    event_id = event["id"]
    event_type = event["type"]

    # Idempotency: never apply the same event twice (Stripe redelivers on failure).
    seen = await db.execute(select(StripeEvent).where(StripeEvent.id == event_id))
    if seen.scalar_one_or_none():
        return {"status": "duplicate"}

    obj = event["data"]["object"]
    try:
        if event_type == "checkout.session.completed":
            await _handle_checkout_completed(db, obj)
        elif event_type in (
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted",
        ):
            sub = await _find_subscription(
                db,
                user_id=(obj.get("metadata") or {}).get("user_id"),
                stripe_subscription_id=obj.get("id"),
            )
            if sub:
                _apply_subscription_object(sub, obj)
        elif event_type in ("invoice.paid", "invoice.payment_succeeded"):
            await _handle_invoice_paid(db, obj)
        elif event_type == "invoice.payment_failed":
            await _handle_invoice_failed(db, obj)
        # other event types are acknowledged (200) but not acted on

        db.add(StripeEvent(id=event_id, type=event_type))
        await db.commit()
    except IntegrityError:
        # Concurrent redelivery inserted this event id first → treat as duplicate.
        await db.rollback()
        return {"status": "duplicate"}

    return {"status": "ok"}
