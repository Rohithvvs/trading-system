"""Add experiments table for sprint1 governance baseline.

Creates the experiments table used by ExperimentService
(002-sprint1-baseline).

Revision ID: add_experiments_001
Revises: merge_research_broker_heads
Create Date: 2026-07-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "add_experiments_001"
down_revision: Union[str, Sequence[str], None] = "merge_research_broker_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    experiment_status = postgresql.ENUM(
        "active",
        "paused",
        "completed",
        "failed",
        name="experiment_status",
        create_type=False,
    )
    # Create enum type if missing (idempotent)
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE experiment_status AS ENUM (
                'active', 'paused', 'completed', 'failed'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
        """
    )

    if "experiments" in tables:
        return

    op.create_table(
        "experiments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            experiment_status,
            nullable=False,
            server_default="active",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_experiments_name"),
    )
    op.create_index("ix_experiments_name", "experiments", ["name"], unique=False)
    op.create_index("ix_experiments_status", "experiments", ["status"], unique=False)
    # At most one active experiment (PostgreSQL partial unique index)
    op.execute(
        """
        CREATE UNIQUE INDEX uq_experiments_single_active
        ON experiments (status)
        WHERE status = 'active';
        """
    )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "experiments" not in set(inspector.get_table_names()):
        return
    op.execute("DROP INDEX IF EXISTS uq_experiments_single_active")
    op.drop_index("ix_experiments_status", table_name="experiments")
    op.drop_index("ix_experiments_name", table_name="experiments")
    op.drop_table("experiments")
    op.execute("DROP TYPE IF EXISTS experiment_status")
