"""
Main API router.

Aggregates all sub-routers under the /api/v1 prefix.
"""

from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.assets import router as assets_router
from app.api.routes.signals import router as signals_router
from app.api.routes.watchlist import router as watchlist_router
from app.api.routes.alerts import router as alerts_router
from app.api.routes.portfolio import router as portfolio_router
from app.api.routes.analysis import router as analysis_router
from app.api.routes.prices import router as prices_router
from app.api.routes.analytics import router as analytics_router
from app.api.routes.notifications import router as notifications_router
from app.api.routes.billing import router as billing_router
from app.api.routes.macro import router as macro_router
from app.api.routes.admin import router as admin_router
from app.api.routes.reports import router as reports_router
from app.api.routes.consent import router as consent_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_router.include_router(assets_router, prefix="/assets", tags=["Assets"])
api_router.include_router(signals_router, prefix="/signals", tags=["Signals"])
api_router.include_router(watchlist_router, prefix="/watchlists", tags=["Watchlists"])
api_router.include_router(alerts_router, prefix="/alerts", tags=["Alerts"])
api_router.include_router(portfolio_router, prefix="/portfolios", tags=["Portfolios"])
api_router.include_router(analysis_router, prefix="/analysis", tags=["Analysis"])
api_router.include_router(prices_router, prefix="/prices", tags=["Prices"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(notifications_router, prefix="/notifications", tags=["Notifications"])
api_router.include_router(billing_router, prefix="/billing", tags=["Billing"])
api_router.include_router(macro_router, prefix="/macro", tags=["Macro"])
api_router.include_router(admin_router, prefix="/admin", tags=["Admin"])
api_router.include_router(reports_router, prefix="/reports", tags=["Reports"])
api_router.include_router(consent_router, prefix="/consent", tags=["Consent"])
