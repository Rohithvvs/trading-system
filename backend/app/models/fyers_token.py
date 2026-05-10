from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from ..db.base import Base


class FyersToken(Base):
    """Database model for storing FYERS tokens.

    This model intentionally contains the newer canonical fields used by the
    UI-driven token endpoints (`fyers_tokens` table) while keeping the older
    compatibility fields (`status`, `access_token_saved_at`, `last_error`) so
    existing services remain functional until a migration refactor is done.
    """

    __tablename__ = "fyers_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

    # Compatibility columns (legacy service code may reference these)
    status = Column(String(32), default="active", index=True)
    access_token_saved_at = Column(DateTime, default=datetime.utcnow)
    last_error = Column(Text, nullable=True)

