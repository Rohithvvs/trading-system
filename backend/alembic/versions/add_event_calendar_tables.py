"""create event calendar and coverage tables

Revision ID: add_event_calendar_tables
Revises: add_walk_forward_tables
Create Date: 2026-07-10 16:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "add_event_calendar_tables"
down_revision: Union[str, None] = "add_walk_forward_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "event_calendar",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("symbol", sa.String(length=16), nullable=True, index=True),
        sa.Column("event_scope", sa.String(length=20), nullable=False, index=True),
        sa.Column("event_type", sa.String(length=50), nullable=False, index=True),
        sa.Column("severity", sa.String(length=10), nullable=False, index=True),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("source_priority", sa.Integer(), nullable=False),
        # All business timestamps stored as TIMESTAMP WITH TIME ZONE (UTC on write, correct on read)
        sa.Column("event_date", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("event_time", sa.String(length=10), nullable=True),
        sa.Column("announced_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("effective_start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("raw_reference", sa.Text(), nullable=True),
        sa.Column("is_confirmed", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()"), index=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )

    op.create_table(
        "event_calendar_coverage",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("coverage_date", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("source", sa.String(length=50), nullable=False, index=True),
        sa.Column("scope", sa.String(length=20), nullable=False, index=True),
        sa.Column("symbols_checked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_loaded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("coverage_status", sa.String(length=20), nullable=False),
        sa.Column("freshness_status", sa.String(length=20), nullable=False),
        sa.Column("warnings", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )

    op.create_table(
        "event_ingestion_run",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("source", sa.String(length=50), nullable=False, index=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("records_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inserted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
    )

def downgrade() -> None:
    op.drop_table("event_ingestion_run", if_exists=True)
    op.drop_table("event_calendar_coverage", if_exists=True)
    op.drop_table("event_calendar", if_exists=True)
