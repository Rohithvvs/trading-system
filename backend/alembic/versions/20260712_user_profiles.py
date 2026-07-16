"""Add user_profiles table for cross-device profile sync.

Revision ID: user_profiles_001
Revises: paper_daily_journal_001
Create Date: 2026-07-12

Chained after paper_daily_journal_001 so there is a single Alembic head
(avoids dual-head startup validation failure).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "user_profiles_001"
down_revision: Union[str, Sequence[str], None] = "paper_daily_journal_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    if "user_profiles" in tables:
        return

    op.create_table(
        "user_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("username", sa.String(100), nullable=True),
        sa.Column("phone", sa.String(40), nullable=True),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("state", sa.String(100), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("language", sa.String(50), nullable=True),
        sa.Column("timezone", sa.String(80), nullable=True),
        sa.Column("currency", sa.String(16), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("postal_code", sa.String(32), nullable=True),
        sa.Column("date_of_birth", sa.String(32), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("trading_experience", sa.String(50), nullable=True),
        sa.Column("risk_profile", sa.String(50), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("preferences", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_user_profiles_user_id", "user_profiles", ["user_id"], unique=True)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "user_profiles" not in inspector.get_table_names():
        return
    op.drop_index("ix_user_profiles_user_id", table_name="user_profiles")
    op.drop_table("user_profiles")
