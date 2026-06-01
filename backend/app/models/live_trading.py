from __future__ import annotations
from decimal import Decimal
from datetime import datetime, timezone
import uuid

from sqlalchemy import (
    DateTime, Integer, String, Text, Boolean, Numeric, Index, UniqueConstraint, CheckConstraint, ForeignKey
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB

from ..db.base import Base

def utc_now():
    return datetime.now(timezone.utc)

class LiveAccount(Base):
    __tablename__ = "live_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(80), default="Primary Live Account")
    base_currency: Mapped[str] = mapped_column(String(8), default="INR")
    starting_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=100000.0)
    available_cash: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=100000.0)
    reserved_cash: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0.0)
    max_risk_per_trade: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=0.02)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, index=True)

    __table_args__ = (
        CheckConstraint('available_cash >= 0', name='check_available_cash_non_negative'),
        CheckConstraint('reserved_cash >= 0', name='check_reserved_cash_non_negative'),
    )

    @property
    def buying_power(self) -> Decimal:
        return self.available_cash


class LivePosition(Base):
    __tablename__ = "live_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("live_accounts.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="OPEN", index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    avg_entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    current_price: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=0.0)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0.0)
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, index=True)

    __table_args__ = (
        Index("idx_unique_live_open_position", "account_id", "symbol", unique=True, postgresql_where=status == 'OPEN'),
    )


class LiveOrder(Base):
    __tablename__ = "live_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    execution_id: Mapped[str] = mapped_column(String(36), unique=True, index=True, default=lambda: str(uuid.uuid4()))
    account_id: Mapped[int] = mapped_column(ForeignKey("live_accounts.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(8), index=True)
    order_type: Mapped[str] = mapped_column(String(12), index=True)
    product_type: Mapped[str] = mapped_column(String(8), default="CNC")
    
    requested_qty: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    filled_qty: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=0.0)
    
    order_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    
    status: Mapped[str] = mapped_column(String(32), index=True)
    
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    broker_request_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    
    reconciliation_attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_reconcile_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, index=True)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_live_orders_reconciliation", "status", "next_reconcile_at"),
        CheckConstraint(
            status.in_([
                'CREATED', 'EXECUTING', 'BROKER_ACCEPTED', 'PARTIALLY_FILLED', 
                'FILLED', 'MODIFY_PENDING', 'CANCEL_PENDING', 'CANCELLED', 
                'REJECTED', 'EXPIRED', 'FAILED', 'RECONCILING', 'MANUAL_INTERVENTION_REQUIRED'
            ]),
            name='check_valid_live_order_status'
        )
    )

class OrderExecutionEvent(Base):
    __tablename__ = "order_execution_events"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("live_orders.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True) # e.g., STATE_TRANSITION
    previous_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_state: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    
    correlation_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class BrokerExecutionLog(Base):
    __tablename__ = "broker_execution_logs"

    broker_trade_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    broker_order_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    
    execution_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
