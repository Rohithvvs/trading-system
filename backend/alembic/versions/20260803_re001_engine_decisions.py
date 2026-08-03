"""Add recommendation_engine_decisions table for RE-001 lab Decision Objects.

Revision ID: 20260803_re001_engine_decisions
Revises: 20260803_pending_market_open
Create Date: 2026-08-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260803_re001_engine_decisions"
down_revision: Union[str, Sequence[str], None] = "20260803_pending_market_open"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    if "recommendation_engine_decisions" in tables:
        return

    op.create_table(
        "recommendation_engine_decisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("recommendation_id", sa.String(length=64), nullable=False),
        sa.Column("engine_id", sa.String(length=32), nullable=False),
        sa.Column("engine_version", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("scan_run_id", sa.String(length=128), nullable=True),
        sa.Column("analysis_history_id", sa.Integer(), nullable=True),
        sa.Column("market_regime", sa.String(length=16), nullable=False),
        sa.Column("trading_objective", sa.String(length=64), nullable=False),
        sa.Column("trading_style", sa.String(length=64), nullable=False),
        sa.Column("strategy_family", sa.String(length=64), nullable=True),
        sa.Column("strategy_name", sa.String(length=128), nullable=True),
        sa.Column("recommendation_state", sa.String(length=12), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("risk_profile", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("portfolio_decision", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("reason_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("trade_guidance", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("production_action", sa.String(length=12), nullable=True),
        sa.Column("production_score", sa.Float(), nullable=True),
        sa.Column("is_mismatch", sa.Boolean(), nullable=True),
        sa.Column("evaluation_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recommendation_engine_decisions")),
        sa.UniqueConstraint("recommendation_id", name=op.f("uq_recommendation_engine_decisions_recommendation_id")),
    )
    op.create_index(
        "ix_recommendation_engine_decisions_engine_id",
        "recommendation_engine_decisions",
        ["engine_id"],
        unique=False,
    )
    op.create_index(
        "ix_recommendation_engine_decisions_symbol",
        "recommendation_engine_decisions",
        ["symbol"],
        unique=False,
    )
    op.create_index(
        "ix_recommendation_engine_decisions_scan_run_id",
        "recommendation_engine_decisions",
        ["scan_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_recommendation_engine_decisions_recommendation_state",
        "recommendation_engine_decisions",
        ["recommendation_state"],
        unique=False,
    )
    op.create_index(
        "ix_recommendation_engine_decisions_created_at",
        "recommendation_engine_decisions",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_recommendation_engine_decisions_analysis_history_id",
        "recommendation_engine_decisions",
        ["analysis_history_id"],
        unique=False,
    )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "recommendation_engine_decisions" not in inspector.get_table_names():
        return
    op.drop_table("recommendation_engine_decisions")
