"""
Database models package.

Exports all SQLAlchemy ORM models so they are registered with the
Base metadata and available for Alembic migrations.
"""

from app.models.user import User
from app.models.asset import Asset
from app.models.price_data import PriceData
from app.models.signal import Signal, SignalPerformance
from app.models.analysis import AnalysisResult
from app.models.watchlist import Watchlist
from app.models.portfolio import Portfolio, PortfolioHolding
from app.models.alert import Alert
from app.models.notification import NotificationSettings
from app.models.subscription import Subscription, Payment
from app.models.admin_audit import AdminAuditLog
from app.models.intelligence import SignalSnapshot, CoinMemory

__all__ = [
    "User",
    "Asset",
    "PriceData",
    "Signal",
    "SignalPerformance",
    "AnalysisResult",
    "Watchlist",
    "Portfolio",
    "PortfolioHolding",
    "Alert",
    "NotificationSettings",
    "Subscription",
    "Payment",
    "AdminAuditLog",
    "SignalSnapshot",
    "CoinMemory",
]
