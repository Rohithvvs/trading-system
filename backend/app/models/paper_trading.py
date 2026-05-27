from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, Boolean, Numeric, Index, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


class PaperTradingAccount(Base):
    __tablename__ = "paper_trading_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(80), default="Primary Paper Account")
    base_currency: Mapped[str] = mapped_column(String(8), default="INR")
    starting_balance: Mapped[float] = mapped_column(Numeric(18, 2), default=100000.0)
    cash_balance: Mapped[float] = mapped_column(Numeric(18, 2), default=100000.0)
    max_risk_per_trade: Mapped[float] = mapped_column(Numeric(18, 8), default=0.02)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)


class PaperPosition(Base):
    __tablename__ = "paper_trading_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_trading_accounts.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="OPEN", index=True)
    lifecycle_state: Mapped[str] = mapped_column(String(32), default="OPEN_POSITION", index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    qty: Mapped[float] = mapped_column(Numeric(18, 8))
    avg_entry_price: Mapped[float] = mapped_column(Numeric(18, 8))
    current_price: Mapped[float] = mapped_column(Numeric(18, 8), default=0.0)
    realized_pnl: Mapped[float] = mapped_column(Numeric(18, 2), default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Numeric(18, 2), default=0.0)
    stop_loss: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    target: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    monitor_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    paused_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source_score: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    source_confidence: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    __table_args__ = (
        Index("idx_unique_open_position", "account_id", "symbol", unique=True, postgresql_where=status == 'OPEN'),
        Index("idx_positions_active_symbol", "symbol", "status", "lifecycle_state", "monitor_enabled"),
    )


class PaperOrder(Base):
    __tablename__ = "paper_trading_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_trading_accounts.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(8), index=True)
    order_type: Mapped[str] = mapped_column(String(12), index=True)
    lifecycle_state: Mapped[str] = mapped_column(String(32), default="PENDING_ENTRY", index=True)
    product_type: Mapped[str] = mapped_column(String(8), default="CNC")
    qty: Mapped[float] = mapped_column(Numeric(18, 8))
    order_price: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    stop_price: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    target: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    requested_entry_price: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    monitor_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    paused_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen_ltp: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source_score: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    source_confidence: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    filled_price: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        index=True,
        default=lambda: f"internal:{uuid.uuid4()}",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_orders_active_symbol", "symbol", "status", "lifecycle_state", "monitor_enabled"),
        Index("idx_orders_account_status_created", "account_id", "status", "created_at"),
    )


class PaperTradeHistory(Base):
    __tablename__ = "paper_trading_trade_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_trading_accounts.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    qty: Mapped[float] = mapped_column(Numeric(18, 8))
    entry_price: Mapped[float] = mapped_column(Numeric(18, 8))
    exit_price: Mapped[float] = mapped_column(Numeric(18, 8))
    pnl: Mapped[float] = mapped_column(Numeric(18, 2))
    pnl_percent: Mapped[float] = mapped_column(Numeric(18, 2))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source_score: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    source_confidence: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    closed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    exit_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)


class PaperNotification(Base):
    __tablename__ = "paper_trading_notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_trading_accounts.id"), index=True)
    message: Mapped[str] = mapped_column(Text)
    level: Mapped[str] = mapped_column(String(16), default="info")
    event_type: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        UniqueConstraint("account_id", "dedupe_key", name="uq_notification_account_dedupe"),
    )


class PaperTransaction(Base):
    __tablename__ = "paper_trading_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_trading_accounts.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(16), index=True)
    qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float] = mapped_column(Float)
    balance_after: Mapped[float | None] = mapped_column(Float, nullable=True)


class PaperAlert(Base):
    __tablename__ = "paper_trading_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_trading_accounts.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    condition: Mapped[str] = mapped_column(String(4))
    target_price: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    triggered_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)


class MarketEngineSession(Base):
    __tablename__ = "market_engine_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    trading_date: Mapped[str] = mapped_column(String(10), index=True)
    status: Mapped[str] = mapped_column(String(32), default="STOPPED", index=True)
    requested_start_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_tick_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    websocket_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    token_status: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    paused_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    monitored_symbols_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    __table_args__ = (
        UniqueConstraint("trading_date", name="uq_market_engine_session_trading_date"),
    )


class ExecutionEvent(Base):
    __tablename__ = "paper_trading_execution_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_id: Mapped[str] = mapped_column(String(36), unique=True, index=True, default=lambda: str(uuid.uuid4()), nullable=False)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    position_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    from_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_execution_event_dedupe"),
        Index("idx_execution_events_order_type", "order_id", "event_type"),
        Index("idx_execution_events_position_type", "position_id", "event_type"),
    )


class ReplaySession(Base):
    __tablename__ = "market_replay_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    replay_key: Mapped[str] = mapped_column(String(160), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="RUNNING", index=True)
    gap_start: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    gap_end: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    checkpoint_symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)


@event.listens_for(ExecutionEvent, "before_update")
def prevent_execution_event_update(mapper, connection, target):
    raise ValueError("ExecutionEvent rows are append-only and cannot be updated.")
