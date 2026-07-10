from decimal import Decimal
from datetime import datetime
from sqlalchemy import Integer, String, Float, DateTime, Numeric, UniqueConstraint, Index, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
import uuid

from ..db.base import Base

class BlacklistedSymbol(Base):
    __tablename__ = "blacklisted_symbols"

    symbol: Mapped[str] = mapped_column(String(50), primary_key=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)

class HistoricalCandle(Base):
    __tablename__ = "historical_candles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    resolution: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="FYERS")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

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
    score: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

class ScanSnapshot(Base):
    __tablename__ = "scan_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    scan_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    scan_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    scan_duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    total_scanned: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_symbols: Mapped[int] = mapped_column(Integer, nullable=False)
    buy_count: Mapped[int] = mapped_column(Integer, nullable=False)
    watch_count: Mapped[int] = mapped_column(Integer, nullable=False)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="completed")
    error_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

class ScanSnapshotRecord(Base):
    __tablename__ = "scan_snapshot_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    scan_id: Mapped[str] = mapped_column(String(36), ForeignKey("scan_snapshots.scan_id", ondelete="CASCADE"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    recommendation: Mapped[str] = mapped_column(String(20), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    close_price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    sma50: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    sma200: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    rsi: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    macd: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ScannerSession(Base):
    __tablename__ = "scanner_sessions"

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    progress_percentage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    symbols_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    symbols_completed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    symbols_failed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_symbol: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

class ScannerSymbolTracking(Base):
    __tablename__ = "scanner_symbol_tracking"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("scanner_sessions.session_id", ondelete="CASCADE"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    retry_count: Mapped[int | None] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    __table_args__ = (
        UniqueConstraint("session_id", "symbol", name="uq_scanner_session_symbol"),
    )

class SystemLock(Base):
    __tablename__ = "system_locks"

    lock_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    locked_by: Mapped[str] = mapped_column(String(200), nullable=False)
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
