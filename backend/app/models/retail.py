"""Retail trading platform models — watchlists, risk limits, chart layouts, notifications, search."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from ..db.base import Base


class Watchlist(Base):
    __tablename__ = "watchlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    sort_by: Mapped[str] = mapped_column(String(32), default="custom", server_default=text("'custom'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, index=True
    )

    items: Mapped[list["WatchlistItem"]] = relationship(
        "WatchlistItem",
        back_populates="watchlist",
        cascade="all, delete-orphan",
        order_by="WatchlistItem.sort_order",
    )

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_watchlist_user_name"),
        Index("ix_watchlists_user_sort", "user_id", "sort_order"),
    )


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    watchlist_id: Mapped[int] = mapped_column(
        ForeignKey("watchlists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(16), default="NSE", server_default=text("'NSE'"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    watchlist: Mapped["Watchlist"] = relationship("Watchlist", back_populates="items")

    __table_args__ = (
        UniqueConstraint("watchlist_id", "symbol", name="uq_watchlist_item_symbol"),
        Index("ix_watchlist_items_wl_sort", "watchlist_id", "sort_order"),
    )


class UserRiskLimits(Base):
    """Hard risk limits per user — violations reject orders immediately."""

    __tablename__ = "user_risk_limits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    max_daily_loss: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("50000"), server_default=text("50000"))
    max_trade_loss: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("10000"), server_default=text("10000"))
    max_position_size: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("200000"), server_default=text("200000"))
    max_exposure: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("500000"), server_default=text("500000"))
    max_sector_exposure_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("40"), server_default=text("40"))
    max_leverage: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("5"), server_default=text("5"))
    max_open_positions: Mapped[int] = mapped_column(Integer, default=25, server_default=text("25"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


class ChartLayout(Base):
    __tablename__ = "chart_layouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(8), default="1D", server_default=text("'1D'"))
    chart_type: Mapped[str] = mapped_column(String(16), default="candlestick", server_default=text("'candlestick'"))
    theme: Mapped[str] = mapped_column(String(8), default="dark", server_default=text("'dark'"))
    indicators_json: Mapped[str] = mapped_column(Text, default="[]", server_default=text("'[]'"))
    drawings_json: Mapped[str] = mapped_column(Text, default="[]", server_default=text("'[]'"))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_chart_layout_user_name"),
    )


class SymbolSearchHistory(Base):
    __tablename__ = "symbol_search_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    query: Mapped[str | None] = mapped_column(String(120), nullable=True)
    searched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_search_history_user_time", "user_id", "searched_at"),
    )


class UserNotification(Base):
    """Unified notification center (price, orders, margin, news, corporate actions, etc.)."""

    __tablename__ = "user_notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[str] = mapped_column(String(16), default="info", server_default=text("'info'"))
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_user_notifications_user_unread", "user_id", "is_read", "created_at"),
    )


class FavoriteSymbol(Base):
    __tablename__ = "favorite_symbols"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "symbol", name="uq_favorite_user_symbol"),
    )
