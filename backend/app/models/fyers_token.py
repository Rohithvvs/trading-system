from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


class FyersToken(Base):
    """Stores the current manually saved FYERS access token.

    The table intentionally keeps a minimal set of columns. Existing older
    columns related to refresh tokens (if present in the DB) are ignored by
    the ORM model — they can be removed via a migration if desired.
    """

    __tablename__ = "fyers_token"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token_saved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="inactive", index=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

