"""Widen broker_tokens.token_masked to VARCHAR(512).

Fernet ciphertext columns were already TEXT. token_masked was VARCHAR(64)
then 128; short masks are preferred, but schema headroom matches the
recommended contract (VARCHAR(512)) and prevents truncation under any masker.

Revision ID: broker_tokens_schema_widen
Revises: broker_tokens_mask_len
Create Date: 2026-07-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "broker_tokens_schema_widen"
down_revision: Union[str, Sequence[str], None] = "broker_tokens_mask_len"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "broker_tokens" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("broker_tokens")}
    if "token_masked" not in cols:
        return

    # Safe widen only — do not touch TEXT secret columns (already correct).
    op.alter_column(
        "broker_tokens",
        "token_masked",
        existing_type=sa.String(length=128),
        type_=sa.String(length=512),
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
        existing_type=sa.String(length=512),
        type_=sa.String(length=128),
        existing_nullable=True,
    )
