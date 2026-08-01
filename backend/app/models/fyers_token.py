from __future__ import annotations

from sqlalchemy import text, Boolean, Column, DateTime, Integer, String, Text

from ..db.base import Base
from ..utils.datetime_utils import utc_now


class FyersToken(Base):
    """Database model for storing FYERS tokens.

    This model intentionally contains the newer canonical fields used by the
    UI-driven token endpoints (`fyers_tokens` table) while keeping the older
    compatibility fields (`status`, `access_token_saved_at`, `last_error`) so
    existing services remain functional until a migration refactor is done.

    All timestamps default to timezone-aware UTC via ``utc_now``.
    """

    __tablename__ = "fyers_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)

    access_token = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, server_default=text("true"))
    validated_at = Column(DateTime(timezone=True), nullable=True)

    # Compatibility columns (legacy service code may reference these)
    status = Column(String(32), default="active", index=True)
    access_token_saved_at = Column(DateTime(timezone=True), default=utc_now)
    last_error = Column(Text, nullable=True)
