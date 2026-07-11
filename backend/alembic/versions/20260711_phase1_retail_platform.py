"""Phase 1 retail trading platform tables.

Revision ID: phase1_retail_001
Revises: paper_daily_journal_001
Create Date: 2026-07-11

Watchlists, risk limits, chart layouts, search history, notifications, favorites.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "phase1_retail_001"
down_revision: Union[str, Sequence[str], None] = "paper_daily_journal_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    if "watchlists" not in tables:
        op.create_table(
            "watchlists",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
            sa.Column("is_pinned", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("is_favorite", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("sort_by", sa.String(32), server_default="'custom'", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "name", name="uq_watchlist_user_name"),
        )
        op.create_index("ix_watchlists_user_id", "watchlists", ["user_id"])
        op.create_index("ix_watchlists_user_sort", "watchlists", ["user_id", "sort_order"])

    if "watchlist_items" not in tables:
        op.create_table(
            "watchlist_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("watchlist_id", sa.Integer(), sa.ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False),
            sa.Column("symbol", sa.String(32), nullable=False),
            sa.Column("exchange", sa.String(16), server_default="'NSE'", nullable=False),
            sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
            sa.Column("notes", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("watchlist_id", "symbol", name="uq_watchlist_item_symbol"),
        )
        op.create_index("ix_watchlist_items_watchlist_id", "watchlist_items", ["watchlist_id"])
        op.create_index("ix_watchlist_items_symbol", "watchlist_items", ["symbol"])
        op.create_index("ix_watchlist_items_wl_sort", "watchlist_items", ["watchlist_id", "sort_order"])

    if "user_risk_limits" not in tables:
        op.create_table(
            "user_risk_limits",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("max_daily_loss", sa.Numeric(18, 2), server_default="50000", nullable=False),
            sa.Column("max_trade_loss", sa.Numeric(18, 2), server_default="10000", nullable=False),
            sa.Column("max_position_size", sa.Numeric(18, 2), server_default="200000", nullable=False),
            sa.Column("max_exposure", sa.Numeric(18, 2), server_default="500000", nullable=False),
            sa.Column("max_sector_exposure_pct", sa.Numeric(8, 4), server_default="40", nullable=False),
            sa.Column("max_leverage", sa.Numeric(8, 4), server_default="5", nullable=False),
            sa.Column("max_open_positions", sa.Integer(), server_default="25", nullable=False),
            sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_user_risk_limits_user_id", "user_risk_limits", ["user_id"])

    if "chart_layouts" not in tables:
        op.create_table(
            "chart_layouts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("symbol", sa.String(32), nullable=False),
            sa.Column("timeframe", sa.String(8), server_default="'1D'", nullable=False),
            sa.Column("chart_type", sa.String(16), server_default="'candlestick'", nullable=False),
            sa.Column("theme", sa.String(8), server_default="'dark'", nullable=False),
            sa.Column("indicators_json", sa.Text(), server_default="'[]'", nullable=False),
            sa.Column("drawings_json", sa.Text(), server_default="'[]'", nullable=False),
            sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "name", name="uq_chart_layout_user_name"),
        )
        op.create_index("ix_chart_layouts_user_id", "chart_layouts", ["user_id"])
        op.create_index("ix_chart_layouts_symbol", "chart_layouts", ["symbol"])

    if "symbol_search_history" not in tables:
        op.create_table(
            "symbol_search_history",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("symbol", sa.String(32), nullable=False),
            sa.Column("query", sa.String(120), nullable=True),
            sa.Column("searched_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_symbol_search_history_user_id", "symbol_search_history", ["user_id"])
        op.create_index("ix_search_history_user_time", "symbol_search_history", ["user_id", "searched_at"])

    if "user_notifications" not in tables:
        op.create_table(
            "user_notifications",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("category", sa.String(32), nullable=False),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("level", sa.String(16), server_default="'info'", nullable=False),
            sa.Column("symbol", sa.String(32), nullable=True),
            sa.Column("payload_json", sa.Text(), nullable=True),
            sa.Column("is_read", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_user_notifications_user_id", "user_notifications", ["user_id"])
        op.create_index("ix_user_notifications_category", "user_notifications", ["category"])
        op.create_index("ix_user_notifications_user_unread", "user_notifications", ["user_id", "is_read", "created_at"])

    if "favorite_symbols" not in tables:
        op.create_table(
            "favorite_symbols",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("symbol", sa.String(32), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "symbol", name="uq_favorite_user_symbol"),
        )
        op.create_index("ix_favorite_symbols_user_id", "favorite_symbols", ["user_id"])


def downgrade() -> None:
    for table in (
        "favorite_symbols",
        "user_notifications",
        "symbol_search_history",
        "chart_layouts",
        "user_risk_limits",
        "watchlist_items",
        "watchlists",
    ):
        op.drop_table(table)
