"""User-scoped broker API credentials (encrypted at rest)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from ..db.base import Base


class BrokerToken(Base):
    """One active credential row per (user_id, broker). Secrets are Fernet-encrypted."""

    __tablename__ = "broker_tokens"
    __table_args__ = (
        UniqueConstraint("user_id", "broker", name="uq_broker_tokens_user_broker"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    broker = Column(String(32), nullable=False, default="FYERS", index=True)
    # Fernet ciphertext: enc:v1:...
    encrypted_token = Column(Text, nullable=False)
    encrypted_api_key = Column(Text, nullable=True)
    encrypted_api_secret = Column(Text, nullable=True)
    token_expiry = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    last_validated_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    # Masked preview only — never full secret (short mask; VARCHAR(512) headroom)
    token_masked = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
