"""Per-user profile stored in the database (not browser storage)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base


class UserProfile(Base):
    """1:1 extension of User for retail profile + preferences."""

    __tablename__ = "user_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )

    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    timezone: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    date_of_birth: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trading_experience: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    risk_profile: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Nested preferences: notifications, scanner defaults, watchlist, themePreference, etc.
    preferences: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user = relationship("User", backref="profile", uselist=False, lazy="joined")
