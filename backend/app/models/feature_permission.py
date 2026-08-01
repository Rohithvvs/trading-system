"""Feature permission catalog (Sprint 3).

System-seeded feature_key values control which roles may access a feature.
Keys follow ^[a-z][a-z0-9_]*$ (seed convention; no admin create-key API).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, TypeDecorator

from ..db.base import Base


class PortableJSONList(TypeDecorator):
    """JSON list: JSONB on PostgreSQL, JSON elsewhere (SQLite tests)."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class FeaturePermission(Base):
    __tablename__ = "feature_permissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    feature_key: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    allowed_roles: Mapped[List[Any]] = mapped_column(
        PortableJSONList, nullable=False, default=list
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
