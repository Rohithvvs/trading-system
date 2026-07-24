"""Widen analysis_history.reason_codes from VARCHAR(100) to TEXT.

Revision ID: 20260723_widen_reason_codes
Revises: 6ee2afcfc7b5
Create Date: 2026-07-23

Long sector-downgrade messages exceeded VARCHAR(100) and crashed scanner
persistence with StringDataRightTruncationError.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260723_widen_reason_codes"
down_revision: Union[str, None] = "6ee2afcfc7b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {col["name"]: col for col in inspector.get_columns("analysis_history")}
    if "reason_codes" not in columns:
        op.add_column(
            "analysis_history",
            sa.Column("reason_codes", sa.Text(), nullable=True),
        )
        return

    # PostgreSQL: ALTER COLUMN TYPE; SQLite batch_alter when needed
    dialect = conn.dialect.name
    if dialect == "postgresql":
        op.execute(
            "ALTER TABLE analysis_history ALTER COLUMN reason_codes TYPE TEXT"
        )
    else:
        with op.batch_alter_table("analysis_history") as batch_op:
            batch_op.alter_column(
                "reason_codes",
                existing_type=sa.String(length=100),
                type_=sa.Text(),
                existing_nullable=True,
            )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {col["name"] for col in inspector.get_columns("analysis_history")}
    if "reason_codes" not in columns:
        return

    dialect = conn.dialect.name
    if dialect == "postgresql":
        # Truncate before narrowing to avoid failure on long existing values
        op.execute(
            "UPDATE analysis_history SET reason_codes = LEFT(reason_codes, 100) "
            "WHERE reason_codes IS NOT NULL AND LENGTH(reason_codes) > 100"
        )
        op.execute(
            "ALTER TABLE analysis_history "
            "ALTER COLUMN reason_codes TYPE VARCHAR(100) "
            "USING LEFT(reason_codes, 100)"
        )
    else:
        with op.batch_alter_table("analysis_history") as batch_op:
            batch_op.alter_column(
                "reason_codes",
                existing_type=sa.Text(),
                type_=sa.String(length=100),
                existing_nullable=True,
            )
