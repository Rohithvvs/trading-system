"""create research persistence tables (FEAT-008)

Revision ID: add_research_persistence_tables
Revises: add_event_calendar_tables
Create Date: 2026-07-13 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "add_research_persistence_tables"
down_revision: Union[str, None] = "add_event_calendar_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "research_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("session_label", sa.String(length=200), nullable=False, index=True),
        sa.Column("symbol", sa.String(length=25), nullable=True, index=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()"), index=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        checkfirst=True,
    )

    op.create_table(
        "research_ideas",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("session_id", sa.Integer(),
                  sa.ForeignKey("research_sessions.id"), nullable=False, index=True),
        sa.Column("parent_idea_id", sa.Integer(),
                  sa.ForeignKey("research_ideas.id"), nullable=True),
        sa.Column("symbol", sa.String(length=25), nullable=True, index=True),
        sa.Column("component_tag", sa.String(length=80), nullable=False, index=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("situation_tags", sa.Text(), nullable=False),
        sa.Column("evidence_level", sa.String(length=20), nullable=False, index=True),
        sa.Column("lifecycle_stage", sa.String(length=30), nullable=False, index=True),
        sa.Column("bucket", sa.String(length=40), nullable=False, index=True),
        sa.Column("required_data", sa.Text(), nullable=False),
        sa.Column("safe_fallback", sa.Text(), nullable=False),
        sa.Column("rollback_criteria", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()"), index=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        checkfirst=True,
    )

    op.create_table(
        "research_critiques",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("idea_id", sa.Integer(),
                  sa.ForeignKey("research_ideas.id"), nullable=False, index=True),
        sa.Column("critique_type", sa.String(length=40), nullable=False, index=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="MEDIUM"),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()"), index=True),
        checkfirst=True,
    )

    op.create_table(
        "research_syntheses",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("session_id", sa.Integer(),
                  sa.ForeignKey("research_sessions.id"), nullable=False, index=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("synthesis_text", sa.Text(), nullable=False),
        sa.Column("source_idea_ids", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()"), index=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        checkfirst=True,
    )

    op.create_table(
        "research_decisions",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("session_id", sa.Integer(),
                  sa.ForeignKey("research_sessions.id"), nullable=False, index=True),
        sa.Column("synthesis_id", sa.Integer(),
                  sa.ForeignKey("research_syntheses.id"), nullable=True, index=True),
        sa.Column("idea_id", sa.Integer(),
                  sa.ForeignKey("research_ideas.id"), nullable=True, index=True),
        sa.Column("decision_type", sa.String(length=40), nullable=False, index=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()"), index=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        checkfirst=True,
    )

    op.create_table(
        "research_rollout_states",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("decision_id", sa.Integer(),
                  sa.ForeignKey("research_decisions.id"), nullable=False, index=True),
        sa.Column("rollout_phase", sa.String(length=40), nullable=False, index=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("observations", sa.Text(), nullable=True),
        sa.Column("gating_checks_passed", sa.Boolean(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()"), index=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        checkfirst=True,
    )


def downgrade() -> None:
    op.drop_table("research_rollout_states", if_exists=True)
    op.drop_table("research_decisions", if_exists=True)
    op.drop_table("research_syntheses", if_exists=True)
    op.drop_table("research_critiques", if_exists=True)
    op.drop_table("research_ideas", if_exists=True)
    op.drop_table("research_sessions", if_exists=True)
