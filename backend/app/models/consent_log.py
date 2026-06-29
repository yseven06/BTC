"""
Consent log — the single, append-only audit trail for every consent/acceptance.

One row per consent event. Rows are NEVER updated or deleted: a new decision
(grant, decline, withdrawal, re-consent on a new document version) is always a
NEW row. This is the one audit substrate for ALL consent — today the legal
package (ToS / privacy / risk acknowledgements, KVKK açık rıza, ETK marketing,
cookie analytics) and tomorrow high-risk features (Auto Trade, API key linking,
Copy Trade) record here with their own `consent_type`.

`consent_type` and `source` are plain strings (not DB enums) on purpose, so new
consent kinds can be added without a schema migration.
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.database import Base


class ConsentLog(Base):
    """
    Append-only consent/acceptance record.

    Known `consent_type` values (extensible):
        tos · privacy · risk · kvkk_acik_riza · etk_marketing ·
        cookie_analytics · cookie_necessary · auto_trade · api_key · copy_trade
    Known `action` values: granted · declined · withdrawn · accepted
    Known `source` values: register · checkout · cookie_banner · re_consent · settings
    """

    __tablename__ = "consent_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Who — null user_id = anonymous (cookie consent before/without login).
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    anonymous = Column(Boolean, nullable=False, default=False, server_default="false")

    # What was consented to.
    consent_type = Column(String(50), nullable=False, index=True)
    action = Column(String(20), nullable=False)  # granted / declined / withdrawn / accepted

    # Exactly which document/version was accepted (hash pins the wording shown).
    document_slug = Column(String(100), nullable=True)
    document_version = Column(String(20), nullable=True)
    document_hash = Column(String(64), nullable=True)  # SHA-256 hex of the rendered text

    # Context.
    source = Column(String(30), nullable=False, index=True)
    locale = Column(String(10), nullable=True)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(Text, nullable=True)

    # Raw UI checkbox state + an extensible bag for future high-risk features.
    checkbox_states = Column(JSONB, nullable=True)
    details = Column(JSONB, nullable=True)

    # Immutable timestamp (UTC). No updated_at — this table is append-only.
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    def __repr__(self) -> str:
        who = self.user_id or "anonymous"
        return f"<ConsentLog(type={self.consent_type}, action={self.action}, who={who}, src={self.source})>"
