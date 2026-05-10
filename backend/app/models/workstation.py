from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


class SavedScan(Base):
    __tablename__ = "saved_scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    mode: Mapped[str] = mapped_column(String(16), default="swing")
    timeframe: Mapped[str] = mapped_column(String(16), default="1d")
    lookback_window: Mapped[int] = mapped_column(Integer, default=180)
    top_n: Mapped[int] = mapped_column(Integer, default=20)
    universe: Mapped[str] = mapped_column(String(80), default="NIFTY500")
    symbols_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    filters_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)


class ScanHistorySnapshot(Base):
    __tablename__ = "scan_history_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    scan_name: Mapped[str] = mapped_column(String(120), default="Manual Scan", index=True)
    screener_name: Mapped[str] = mapped_column(String(120), default="Nifty 500 Swing Scanner")
    mode: Mapped[str] = mapped_column(String(16), default="swing", index=True)
    timeframe: Mapped[str] = mapped_column(String(16), default="1d")
    lookback_window: Mapped[int] = mapped_column(Integer, default=180)
    top_n: Mapped[int] = mapped_column(Integer, default=20)
    universe: Mapped[str] = mapped_column(String(80), default="NIFTY500", index=True)
    scanned_symbols: Mapped[int] = mapped_column(Integer, default=0)
    shortlisted_count: Mapped[int] = mapped_column(Integer, default=0)
    buy_count: Mapped[int] = mapped_column(Integer, default=0)
    watch_count: Mapped[int] = mapped_column(Integer, default=0)
    data_source: Mapped[str | None] = mapped_column(String(80), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class WorkstationAlert(Base):
    __tablename__ = "workstation_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    alert_type: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    condition: Mapped[str | None] = mapped_column(String(8), nullable=True)
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    scan_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)


class RiskSettings(Base):
    __tablename__ = "risk_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    profile: Mapped[str] = mapped_column(String(24), default="moderate")
    default_position_size_pct: Mapped[float] = mapped_column(Float, default=10.0)
    max_risk_per_trade_pct: Mapped[float] = mapped_column(Float, default=2.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
