"""
TradeMinds AI – Subscription Plan Catalog

Defines the available tiers, pricing across billing cycles, and the
features unlocked at each tier. Single source of truth used by the
billing API and the frontend pricing page.
"""

from dataclasses import dataclass, asdict
from typing import Dict, List

from app.models.subscription import SubscriptionTier, BillingCycle


@dataclass
class PlanFeature:
    label: str
    included: bool


@dataclass
class PlanPricing:
    cycle: BillingCycle
    amount_usd: float
    months: int
    savings_pct: int = 0


@dataclass
class Plan:
    tier: SubscriptionTier
    name: str
    description: str
    pricing: List[PlanPricing]
    features: List[PlanFeature]
    recommended: bool = False


# Feature labels shown on the pricing page.
FREE_FEATURES = [
    PlanFeature("Sınırlı sinyal (günde 3)", True),
    PlanFeature("Temel grafikler", True),
    PlanFeature("Tüm AI motorları", False),
    PlanFeature("Telegram bildirimleri", False),
    PlanFeature("Sınırsız sinyal", False),
    PlanFeature("Geçmiş veri & backtest", False),
    PlanFeature("Öncelikli destek", False),
]

PRO_FEATURES = [
    PlanFeature("Sınırsız sinyal", True),
    PlanFeature("Tüm AI motorları", True),
    PlanFeature("TradingView grafikleri", True),
    PlanFeature("Telegram bildirimleri", True),
    PlanFeature("Strategy Lab & Symbol Analysis", True),
    PlanFeature("On-chain analiz motoru", True),
    PlanFeature("Backtest (sınırlı)", True),
    PlanFeature("Öncelikli destek", False),
    PlanFeature("API erişimi", False),
]

PREMIUM_FEATURES = [
    PlanFeature("Pro'daki her şey", True),
    PlanFeature("Sınırsız backtest", True),
    PlanFeature("Erken erişim özellikleri", True),
    PlanFeature("Öncelikli destek", True),
    PlanFeature("API erişimi", True),
    PlanFeature("Özel sembol istekleri", True),
]


PLANS: Dict[SubscriptionTier, Plan] = {
    SubscriptionTier.FREE: Plan(
        tier=SubscriptionTier.FREE,
        name="Ücretsiz",
        description="Sistemi denemek için temel paket.",
        pricing=[
            PlanPricing(BillingCycle.MONTHLY, 0.0, 1, 0),
        ],
        features=FREE_FEATURES,
    ),
    SubscriptionTier.PRO: Plan(
        tier=SubscriptionTier.PRO,
        name="Pro",
        description="Aktif trader'lar için tam erişim.",
        pricing=[
            PlanPricing(BillingCycle.MONTHLY,     25.0,  1, 0),
            PlanPricing(BillingCycle.QUARTERLY,   60.0,  3, 20),
            PlanPricing(BillingCycle.SEMI_ANNUAL, 100.0, 6, 33),
            PlanPricing(BillingCycle.YEARLY,      150.0, 12, 50),
        ],
        features=PRO_FEATURES,
        recommended=True,
    ),
    SubscriptionTier.PREMIUM: Plan(
        tier=SubscriptionTier.PREMIUM,
        name="Premium",
        description="Kurumsal düzey, sınırsız her şey.",
        pricing=[
            PlanPricing(BillingCycle.MONTHLY,     69.0,  1, 0),
            PlanPricing(BillingCycle.QUARTERLY,   180.0, 3, 13),
            PlanPricing(BillingCycle.SEMI_ANNUAL, 330.0, 6, 20),
            PlanPricing(BillingCycle.YEARLY,      590.0, 12, 28),
        ],
        features=PREMIUM_FEATURES,
    ),
}


def get_plans_payload() -> List[Dict]:
    """Return plans as a JSON-serializable list ordered Free → Pro → Premium."""
    order = [SubscriptionTier.FREE, SubscriptionTier.PRO, SubscriptionTier.PREMIUM]
    out = []
    for tier in order:
        p = PLANS[tier]
        out.append({
            "tier": p.tier.value,
            "name": p.name,
            "description": p.description,
            "recommended": p.recommended,
            "pricing": [
                {"cycle": pr.cycle.value, "amount_usd": pr.amount_usd,
                 "months": pr.months, "savings_pct": pr.savings_pct}
                for pr in p.pricing
            ],
            "features": [asdict(f) for f in p.features],
        })
    return out


def get_price(tier: SubscriptionTier, cycle: BillingCycle) -> float:
    """Look up the price (USD) for a tier + cycle, or 0 if not offered."""
    plan = PLANS.get(tier)
    if not plan:
        return 0.0
    for pr in plan.pricing:
        if pr.cycle == cycle:
            return pr.amount_usd
    return 0.0


def get_months(cycle: BillingCycle) -> int:
    """Number of months in a billing cycle."""
    return {
        BillingCycle.MONTHLY: 1,
        BillingCycle.QUARTERLY: 3,
        BillingCycle.SEMI_ANNUAL: 6,
        BillingCycle.YEARLY: 12,
    }.get(cycle, 1)


def get_stripe_recurring(cycle: BillingCycle) -> Dict[str, object]:
    """Stripe ``recurring`` params for a billing cycle (used by checkout in
    subscription mode).

    Uses ``interval='month'`` + ``interval_count = months`` so 1/3/6/12-month
    cycles map uniformly (Stripe allows interval_count up to 12 for 'month').
    The amount billed each interval is the per-cycle price from PLANS — e.g.
    quarterly = the full 3-month price charged once every 3 months.
    """
    return {"interval": "month", "interval_count": get_months(cycle)}
