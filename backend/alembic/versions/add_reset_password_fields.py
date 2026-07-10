"""add reset_password_token and reset_password_expires_at to users

Revision ID: add_reset_password_fields
Revises: add_google_oauth_fields
Create Date: 2026-07-09 05:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "add_reset_password_fields"
down_revision: Union[str, None] = "add_google_oauth_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("reset_password_token", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("reset_password_expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "reset_password_expires_at")
    op.drop_column("users", "reset_password_token")
