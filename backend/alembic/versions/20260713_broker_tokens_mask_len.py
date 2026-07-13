"""Widen broker_tokens.token_masked for long JWT previews.

Fyers access tokens are long JWTs. Even when masked, a proportional mask
overflowed VARCHAR(64) and failed INSERT with StringDataRightTruncationError.
Masking is now fixed-length; column is widened as defense in depth.

Revision ID: broker_tokens_mask_len
Revises: broker_tokens_001
Create Date: 2026-07-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "broker_tokens_mask_len"
down_revision: Union[str, Sequence[str], None] = "broker_tokens_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "broker_tokens" not in inspector.get_table_names():
        return
    cols = {c["name"]: c for c in inspector.get_columns("broker_tokens")}
    if "token_masked" not in cols:
        return
    op.alter_column(
        "broker_tokens",
        "token_masked",
        existing_type=sa.String(length=64),
        type_=sa.String(length=128),
        existing_nullable=True,
    )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "broker_tokens" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("broker_tokens")}
    if "token_masked" not in cols:
        return
    op.alter_column(
        "broker_tokens",
        "token_masked",
        existing_type=sa.String(length=128),
        type_=sa.String(length=64),
        existing_nullable=True,
    )
