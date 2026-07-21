"""add_situation_tags_and_backfill_progress

Revision ID: 6ee2afcfc7b5
Revises: 104d02035305
Create Date: 2026-07-21 19:25:59.072415

Hardening (M4): GIN index create/drop uses Alembic autocommit_block so
CREATE/DROP INDEX CONCURRENTLY is not nested inside a transaction.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6ee2afcfc7b5"
down_revision: Union[str, Sequence[str], None] = "104d02035305"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_GIN_INDEX = "ix_analysis_history_situation_tags"


def upgrade() -> None:
    """Upgrade schema."""
    from sqlalchemy.dialects import postgresql

    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # 1. Add situation_tags column to analysis_history
    if is_pg:
        op.add_column(
            "analysis_history",
            sa.Column(
                "situation_tags",
                postgresql.ARRAY(sa.Text()),
                server_default="{}",
                nullable=False,
            ),
        )
    else:
        # Non-Postgres (e.g. local sqlite) — TEXT JSON-compatible column
        op.add_column(
            "analysis_history",
            sa.Column("situation_tags", sa.Text(), server_default="{}", nullable=False),
        )

    # 2. Create backfill_progress table
    op.create_table(
        "backfill_progress",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.String(length=50), nullable=False),
        sa.Column("last_processed_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="RUNNING"),
        sa.Column("processed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_count", sa.Integer(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()" if is_pg else "CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()" if is_pg else "CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_backfill_progress")),
    )
    op.create_index(op.f("ix_backfill_progress_id"), "backfill_progress", ["id"], unique=False)
    op.create_index(
        op.f("ix_backfill_progress_job_id"), "backfill_progress", ["job_id"], unique=True
    )

    # 3. GIN index concurrently outside a transaction block (Postgres only)
    if is_pg:
        with op.get_context().autocommit_block():
            op.execute(
                sa.text(
                    f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {_GIN_INDEX} "
                    f"ON analysis_history USING gin (situation_tags)"
                )
            )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        with op.get_context().autocommit_block():
            op.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {_GIN_INDEX}"))
    else:
        try:
            op.drop_index(_GIN_INDEX, table_name="analysis_history")
        except Exception:
            pass

    op.drop_column("analysis_history", "situation_tags")

    op.drop_index(op.f("ix_backfill_progress_job_id"), table_name="backfill_progress")
    op.drop_index(op.f("ix_backfill_progress_id"), table_name="backfill_progress")
    op.drop_table("backfill_progress")
