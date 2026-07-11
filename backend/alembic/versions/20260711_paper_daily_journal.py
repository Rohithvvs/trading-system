"""Add paper_trading_daily_journals for Daily Analytics.

Revision ID: paper_daily_journal_001
Revises: paper_user_isolation_001
Create Date: 2026-07-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "paper_daily_journal_001"
down_revision: Union[str, Sequence[str], None] = "paper_user_isolation_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "paper_trading_daily_journals" in inspector.get_table_names():
        return
    op.create_table(
        "paper_trading_daily_journals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("paper_trading_accounts.id"), nullable=False),
        sa.Column("journal_date", sa.String(length=10), nullable=False),
        sa.Column("observations", sa.Text(), nullable=True),
        sa.Column("mistakes", sa.Text(), nullable=True),
        sa.Column("lessons", sa.Text(), nullable=True),
        sa.Column("tomorrow_plan", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("account_id", "journal_date", name="uq_paper_journal_account_date"),
    )
    op.create_index("idx_paper_journal_account_date", "paper_trading_daily_journals", ["account_id", "journal_date"])
    op.create_index("ix_paper_trading_daily_journals_id", "paper_trading_daily_journals", ["id"])
    op.create_index("ix_paper_trading_daily_journals_account_id", "paper_trading_daily_journals", ["account_id"])
    op.create_index("ix_paper_trading_daily_journals_journal_date", "paper_trading_daily_journals", ["journal_date"])


def downgrade() -> None:
    op.drop_table("paper_trading_daily_journals")
