"""Add pending-market-open order fields and widen status column.

Revision ID: 20260803_pending_market_open
Revises: 20260730_001_feature_permissions
Create Date: 2026-08-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260803_pending_market_open"
down_revision: Union[str, Sequence[str], None] = "20260730_001_feature_permissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    if "paper_trading_orders" not in tables:
        return

    cols = {c["name"]: c for c in inspector.get_columns("paper_trading_orders")}

    # Widen status to fit PENDING_MARKET_OPEN (and future enum values)
    if "status" in cols:
        op.alter_column(
            "paper_trading_orders",
            "status",
            existing_type=sa.String(length=16),
            type_=sa.String(length=32),
            existing_nullable=True,
        )

    if "scheduled_execution" not in cols:
        op.add_column(
            "paper_trading_orders",
            sa.Column("scheduled_execution", sa.DateTime(timezone=True), nullable=True),
        )
    if "market_session" not in cols:
        op.add_column(
            "paper_trading_orders",
            sa.Column("market_session", sa.String(length=32), nullable=True),
        )

    existing_indexes = {ix["name"] for ix in inspector.get_indexes("paper_trading_orders")}
    if "idx_orders_pending_market_open" not in existing_indexes:
        op.create_index(
            "idx_orders_pending_market_open",
            "paper_trading_orders",
            ["status", "scheduled_execution"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "paper_trading_orders" not in inspector.get_table_names():
        return

    existing_indexes = {ix["name"] for ix in inspector.get_indexes("paper_trading_orders")}
    if "idx_orders_pending_market_open" in existing_indexes:
        op.drop_index("idx_orders_pending_market_open", table_name="paper_trading_orders")

    cols = {c["name"] for c in inspector.get_columns("paper_trading_orders")}
    if "market_session" in cols:
        op.drop_column("paper_trading_orders", "market_session")
    if "scheduled_execution" in cols:
        op.drop_column("paper_trading_orders", "scheduled_execution")

    op.alter_column(
        "paper_trading_orders",
        "status",
        existing_type=sa.String(length=32),
        type_=sa.String(length=16),
        existing_nullable=True,
    )
