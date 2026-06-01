from datetime import datetime
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base

class MigrationCheckpoint(Base):
    __tablename__ = "migration_checkpoints"

    table_name: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    last_processed_primary_key: Mapped[int] = mapped_column(Integer, default=0)
    last_processed_chunk: Mapped[int] = mapped_column(Integer, default=0)
    rows_migrated: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    migration_status: Mapped[str] = mapped_column(String(32), default="IN_PROGRESS")
    migration_run_id: Mapped[str] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
