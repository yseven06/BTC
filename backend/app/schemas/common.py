"""
Common schemas used across multiple API endpoints.

Provides generic paginated response wrappers and error response models.
"""

from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorResponse(BaseModel):
    """Standard error response body."""

    detail: str = Field(..., description="Human-readable error message.")
    error_code: Optional[str] = Field(None, description="Machine-readable error code.")


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Generic paginated response wrapper.

    Wraps a list of items with pagination metadata so clients
    can implement infinite scroll or page-based navigation.
    """

    items: List[Any] = Field(default_factory=list, description="List of result items.")
    total: int = Field(0, description="Total number of matching records.")
    page: int = Field(1, ge=1, description="Current page number (1-indexed).")
    page_size: int = Field(20, ge=1, le=100, description="Number of items per page.")
    total_pages: int = Field(0, description="Total number of pages.")
    has_next: bool = Field(False, description="Whether a next page exists.")
    has_previous: bool = Field(False, description="Whether a previous page exists.")

    @classmethod
    def create(
        cls,
        items: List[Any],
        total: int,
        page: int = 1,
        page_size: int = 20,
    ) -> "PaginatedResponse":
        """
        Factory method to build a paginated response with computed metadata.

        Args:
            items: The current page of result items.
            total: Total matching record count.
            page: Current page number.
            page_size: Items per page.

        Returns:
            A fully populated PaginatedResponse instance.
        """
        total_pages = max(1, (total + page_size - 1) // page_size)
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        )


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field("healthy", description="Application health status.")
    version: str = Field(..., description="Application version.")
    environment: str = Field(..., description="Current environment (dev/prod).")


class MessageResponse(BaseModel):
    """Simple message response."""

    message: str = Field(..., description="Response message.")
