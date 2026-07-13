"""Add broker_tokens table for encrypted user-scoped broker credentials.

Revision ID: broker_tokens_001
Revises: user_profiles_001
Create Date: 2026-07-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "broker_tokens_001"
down_revision: Union[str, Sequence[str], None] = "user_profiles_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    if "broker_tokens" in tables:
        return

    op.create_table(
        "broker_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("broker", sa.String(length=32), nullable=False, server_default="FYERS"),
        sa.Column("encrypted_token", sa.Text(), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=True),
        sa.Column("encrypted_api_secret", sa.Text(), nullable=True),
        sa.Column("token_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("token_masked", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "broker", name="uq_broker_tokens_user_broker"),
    )
    op.create_index("ix_broker_tokens_user_id", "broker_tokens", ["user_id"])
    op.create_index("ix_broker_tokens_broker", "broker_tokens", ["broker"])
    op.create_index("ix_broker_tokens_status", "broker_tokens", ["status"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "broker_tokens" not in inspector.get_table_names():
        return
    op.drop_index("ix_broker_tokens_status", table_name="broker_tokens")
    op.drop_index("ix_broker_tokens_broker", table_name="broker_tokens")
    op.drop_index("ix_broker_tokens_user_id", table_name="broker_tokens")
    op.drop_table("broker_tokens")
