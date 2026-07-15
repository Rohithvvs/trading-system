from datetime import datetime, timezone
from sqlalchemy import Integer, String, Float, Boolean, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..db.base import Base

class EventCalendar(Base):
    __tablename__ = "event_calendar"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    symbol: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    event_scope: Mapped[str] = mapped_column(String(20), index=True)  # COMPANY / SECTOR / MARKET / GLOBAL
    event_type: Mapped[str] = mapped_column(String(50), index=True)   # EARNINGS / AGM / DIVIDEND / SPLIT / INTEREST_RATE / GDP / etc.
    severity: Mapped[str] = mapped_column(String(10), index=True)      # LOW / MEDIUM / HIGH / CRITICAL
    source: Mapped[str] = mapped_column(String(50))
    source_priority: Mapped[int] = mapped_column(Integer)             # 1 (highest) to 5 (lowest)
    
    event_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    event_time: Mapped[str | None] = mapped_column(String(10), nullable=True) # HH:MM format
    announced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    effective_start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class EventCalendarCoverage(Base):
    __tablename__ = "event_calendar_coverage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    coverage_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str] = mapped_column(String(50), index=True)
    scope: Mapped[str] = mapped_column(String(20), index=True)
    symbols_checked: Mapped[int] = mapped_column(Integer, default=0)
    records_loaded: Mapped[int] = mapped_column(Integer, default=0)
    coverage_status: Mapped[str] = mapped_column(String(20))          # COMPLETE / INCOMPLETE
    freshness_status: Mapped[str] = mapped_column(String(20))         # FRESH / STALE
    warnings: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class EventIngestionRun(Base):
    __tablename__ = "event_ingestion_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source: Mapped[str] = mapped_column(String(50), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20))                   # RUNNING / COMPLETED / FAILED
    records_seen: Mapped[int] = mapped_column(Integer, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
