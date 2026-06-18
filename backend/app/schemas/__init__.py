"""
Pydantic schemas package.

Exports all request/response schemas used across the API layer.
"""

from app.schemas.user import (
    UserCreate,
    UserLogin,
    UserResponse,
    UserUpdate,
    TokenResponse,
)
from app.schemas.asset import AssetResponse, AssetListResponse
from app.schemas.signal import (
    SignalResponse,
    SignalDetailResponse,
    SignalListResponse,
    SignalPerformanceResponse,
)
from app.schemas.analysis import AnalysisResponse, EngineResultResponse
from app.schemas.watchlist import WatchlistCreate, WatchlistResponse, WatchlistUpdate
from app.schemas.alert import AlertCreate, AlertResponse, AlertUpdate
from app.schemas.common import PaginatedResponse, ErrorResponse

__all__ = [
    "UserCreate",
    "UserLogin",
    "UserResponse",
    "UserUpdate",
    "TokenResponse",
    "AssetResponse",
    "AssetListResponse",
    "SignalResponse",
    "SignalDetailResponse",
    "SignalListResponse",
    "SignalPerformanceResponse",
    "AnalysisResponse",
    "EngineResultResponse",
    "WatchlistCreate",
    "WatchlistResponse",
    "WatchlistUpdate",
    "AlertCreate",
    "AlertResponse",
    "AlertUpdate",
    "PaginatedResponse",
    "ErrorResponse",
]
