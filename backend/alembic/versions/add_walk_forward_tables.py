"""create walk forward summary and veto history tables

Revision ID: add_walk_forward_tables
Revises: add_market_regime_cols
Create Date: 2026-07-10 15:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "add_walk_forward_tables"
down_revision: Union[str, None] = "add_market_regime_cols"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # checkfirst=True is the PostgreSQL-safe equivalent of "CREATE TABLE IF NOT EXISTS"
    op.create_table(
        "walk_forward_summary",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("symbol", sa.String(length=16), nullable=False, index=True),
        sa.Column("window_label", sa.String(length=100), nullable=False),
        # TIMESTAMP WITH TIME ZONE — stores UTC, displays in session TZ
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("champ_net_return", sa.Float(), nullable=False),
        sa.Column("chal_net_return", sa.Float(), nullable=False),
        sa.Column("champ_trade_count", sa.Integer(), nullable=False),
        sa.Column("chal_trade_count", sa.Integer(), nullable=False),
        sa.Column("veto_count", sa.Integer(), nullable=False),
        sa.Column("veto_rate", sa.Float(), nullable=False),
        sa.Column("champ_expectancy", sa.Float(), nullable=False),
        sa.Column("chal_expectancy", sa.Float(), nullable=False),
        sa.Column("champ_profit_factor", sa.Float(), nullable=False),
        sa.Column("chal_profit_factor", sa.Float(), nullable=False),
        sa.Column("champ_drawdown", sa.Float(), nullable=False),
        sa.Column("chal_drawdown", sa.Float(), nullable=False),
        sa.Column("champ_win_rate", sa.Float(), nullable=False),
        sa.Column("chal_win_rate", sa.Float(), nullable=False),
        sa.Column("opt_vix_caution", sa.Float(), nullable=True),
        sa.Column("opt_vix_highrisk", sa.Float(), nullable=True),
        sa.Column("opt_breadth_caution", sa.Float(), nullable=True),
        sa.Column("opt_breadth_weak", sa.Float(), nullable=True),
        sa.Column("verdict", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()"), index=True),
        checkfirst=True
    )

    op.create_table(
        "veto_history",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("window_label", sa.String(length=100), nullable=True),
        sa.Column("scan_date", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("symbol", sa.String(length=16), nullable=False, index=True),
        sa.Column("gate_name", sa.String(length=50), nullable=False),
        sa.Column("original_signal", sa.String(length=20), nullable=False),
        sa.Column("challenger_signal", sa.String(length=20), nullable=False),
        sa.Column("veto_triggered", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("engine_version", sa.String(length=10), nullable=False, server_default="1.0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()"), index=True),
        checkfirst=True
    )

def downgrade() -> None:
    op.drop_table("veto_history", if_exists=True)
    op.drop_table("walk_forward_summary", if_exists=True)
