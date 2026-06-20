"""
Admin audit log model.

Every mutating action taken from the admin panel (role changes, tier
overrides, signal invalidation, asset toggles, user deletion, ...) is
recorded here so "who changed what, and when" is always answerable.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID

from app.database import Base


class AdminAuditLog(Base):
    """
    Attributes:
        actor_id: The admin who performed the action.
        actor_email: Denormalized at write-time so the log entry stays
            readable even if the actor account is later deleted.
        action: Dotted action key, e.g. "user.role_change", "signal.invalidate".
        target_type: What kind of entity was affected ("user", "signal", "asset").
        target_id: The affected entity's id (string — entities use different
            PK types across tables, so this stays untyped here).
        detail: Free-form JSON with before/after values or extra context.
    """

    __tablename__ = "admin_audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    actor_email = Column(String(255), nullable=False)
    action = Column(String(100), nullable=False, index=True)
    target_type = Column(String(50), nullable=True, index=True)
    target_id = Column(String(100), nullable=True, index=True)
    detail = Column(JSON, nullable=True, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    def __repr__(self) -> str:
        return f"<AdminAuditLog(action={self.action}, actor={self.actor_email}, target={self.target_type}:{self.target_id})>"
