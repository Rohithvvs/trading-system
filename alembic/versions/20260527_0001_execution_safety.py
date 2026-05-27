"""execution safety primitives

Revision ID: 20260527_0001
Revises:
Create Date: 2026-05-27
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260527_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "market_replay_sessions" not in inspector.get_table_names():
        op.create_table(
            "market_replay_sessions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("replay_key", sa.String(length=160), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="RUNNING"),
            sa.Column("gap_start", sa.DateTime(), nullable=False),
            sa.Column("gap_end", sa.DateTime(), nullable=False),
            sa.Column("checkpoint_symbol", sa.String(length=32), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_market_replay_sessions_replay_key", "market_replay_sessions", ["replay_key"], unique=True)

    columns = {col["name"] for col in inspector.get_columns("paper_trading_orders")}
    if "idempotency_key" not in columns:
        op.add_column("paper_trading_orders", sa.Column("idempotency_key", sa.String(length=128), nullable=True))
        op.execute("UPDATE paper_trading_orders SET idempotency_key = 'legacy:' || id WHERE idempotency_key IS NULL")
        op.alter_column("paper_trading_orders", "idempotency_key", nullable=False)
    op.create_index("ix_paper_trading_orders_idempotency_key", "paper_trading_orders", ["idempotency_key"], unique=True, if_not_exists=True)
    op.create_index("idx_orders_active_symbol", "paper_trading_orders", ["symbol", "status", "lifecycle_state", "monitor_enabled"], if_not_exists=True)

    columns = {col["name"] for col in inspector.get_columns("paper_trading_execution_events")}
    if "event_id" not in columns:
        op.add_column("paper_trading_execution_events", sa.Column("event_id", sa.String(length=36), nullable=True))
        op.execute("UPDATE paper_trading_execution_events SET event_id = md5(random()::text || clock_timestamp()::text) WHERE event_id IS NULL")
        op.alter_column("paper_trading_execution_events", "event_id", nullable=False)
    op.create_index("ix_paper_trading_execution_events_event_id", "paper_trading_execution_events", ["event_id"], unique=True, if_not_exists=True)
    op.create_unique_constraint("uq_execution_event_dedupe", "paper_trading_execution_events", ["dedupe_key"])
    op.create_unique_constraint("uq_market_engine_session_trading_date", "market_engine_sessions", ["trading_date"])
    op.create_unique_constraint("uq_notification_account_dedupe", "paper_trading_notifications", ["account_id", "dedupe_key"])


def downgrade() -> None:
    op.drop_table("market_replay_sessions")
