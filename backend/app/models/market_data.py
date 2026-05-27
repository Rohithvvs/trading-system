from datetime import datetime
from sqlalchemy import Integer, String, Float, DateTime, Numeric, UniqueConstraint, Index, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
import uuid

from ..db.base import Base

class BlacklistedSymbol(Base):
    __tablename__ = "blacklisted_symbols"

    symbol: Mapped[str] = mapped_column(String(50), primary_key=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

class HistoricalCandle(Base):
    __tablename__ = "historical_candles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    resolution: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    open: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    high: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    low: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    close: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    volume: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="FYERS")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    __table_args__ = (
        UniqueConstraint("symbol", "resolution", "timestamp", name="uq_historical_candle"),
        Index("idx_hist_candles_sym_res_ts", "symbol", "resolution", "timestamp"),
        Index("idx_hist_candles_sym_ts", "symbol", "timestamp"),
    )

class LatestScanResult(Base):
    __tablename__ = "latest_scan_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    signal_type: Mapped[str] = mapped_column(String(50), nullable=False)
    score: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    scanned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

class ScannerSession(Base):
    __tablename__ = "scanner_sessions"

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    progress_percentage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    symbols_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    symbols_completed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    symbols_failed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_symbol: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

class ScannerSymbolTracking(Base):
    __tablename__ = "scanner_symbol_tracking"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("scanner_sessions.session_id", ondelete="CASCADE"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    retry_count: Mapped[int | None] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    __table_args__ = (
        UniqueConstraint("session_id", "symbol", name="uq_scanner_session_symbol"),
    )

class SystemLock(Base):
    __tablename__ = "system_locks"

    lock_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    locked_by: Mapped[str] = mapped_column(String(200), nullable=False)
    locked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
