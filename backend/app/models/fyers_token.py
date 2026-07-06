from __future__ import annotations

from datetime import datetime

from sqlalchemy import text, Boolean, Column, DateTime, Integer, String, Text

from ..db.base import Base


class FyersToken(Base):
    """Database model for storing FYERS access tokens only.

    Refresh token / auto-renewal columns have been removed.
    Only manual access token workflow is supported.
    """

    __tablename__ = "fyers_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)

    access_token = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, server_default=text("true"))
    validated_at = Column(DateTime(timezone=True), nullable=True)

    # Compatibility / legacy columns kept for backward compatibility in services
    status = Column(String(32), default="active", index=True)
    access_token_saved_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    last_error = Column(Text, nullable=True)

