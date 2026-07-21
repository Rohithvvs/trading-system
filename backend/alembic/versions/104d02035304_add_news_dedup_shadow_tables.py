"""add_news_dedup_shadow_tables

Revision ID: 104d02035304
Revises: add_experiments_001
Create Date: 2026-07-21 13:20:51.499260

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "104d02035304"
down_revision: Union[str, Sequence[str], None] = "add_experiments_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add shadow_outputs column to analysis_history
    op.add_column(
        "analysis_history",
        sa.Column(
            "shadow_outputs",
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    # Create GIN index on shadow_outputs
    op.create_index(
        "ix_analysis_history_shadow_outputs",
        "analysis_history",
        ["shadow_outputs"],
        unique=False,
        postgresql_using="gin",
    )

    # FR-009: dedicated audit table (clarified name: news_deduplication_audit)
    op.create_table(
        "news_deduplication_audit",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=25), nullable=False),
        sa.Column("kept_id", sa.String(length=500), nullable=False),
        sa.Column("deduplicated_id", sa.String(length=500), nullable=False),
        sa.Column("kept_title", sa.Text(), nullable=False),
        sa.Column("deduplicated_title", sa.Text(), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.Column("reason", sa.String(length=250), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_news_deduplication_audit_id",
        "news_deduplication_audit",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_news_deduplication_audit_symbol",
        "news_deduplication_audit",
        ["symbol"],
        unique=False,
    )
    op.create_index(
        "ix_news_deduplication_audit_kept_dedup",
        "news_deduplication_audit",
        ["kept_id", "deduplicated_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_news_deduplication_audit_kept_dedup",
        table_name="news_deduplication_audit",
    )
    op.drop_index(
        "ix_news_deduplication_audit_symbol",
        table_name="news_deduplication_audit",
    )
    op.drop_index(
        "ix_news_deduplication_audit_id",
        table_name="news_deduplication_audit",
    )
    op.drop_table("news_deduplication_audit")
    op.drop_index("ix_analysis_history_shadow_outputs", table_name="analysis_history")
    op.drop_column("analysis_history", "shadow_outputs")
