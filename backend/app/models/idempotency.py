from __future__ import annotations
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base

class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    operation_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_idempotency_key_status", "idempotency_key", "status"),
    )
