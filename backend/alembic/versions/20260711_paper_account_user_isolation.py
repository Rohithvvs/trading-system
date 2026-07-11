"""Add user_id to paper_trading_accounts for multi-user isolation.

Revision ID: paper_user_isolation_001
Revises: add_reset_password_fields
Create Date: 2026-07-11

Every authenticated user gets an independent paper trading account.
Child tables (positions, orders, trades, …) remain scoped via account_id FK.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "paper_user_isolation_001"
down_revision: Union[str, Sequence[str], None] = "add_reset_password_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "paper_trading_accounts" not in tables:
        return

    columns = {c["name"] for c in inspector.get_columns("paper_trading_accounts")}

    if "user_id" not in columns:
        op.add_column(
            "paper_trading_accounts",
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        )

    # Backfill: if exactly one orphan account and one user, bind them (legacy shared account)
    # Otherwise leave orphans NULL — they will not be used by multi-user paths.
    try:
        conn.execute(
            sa.text(
                """
                UPDATE paper_trading_accounts a
                SET user_id = u.id
                FROM (
                    SELECT id FROM users ORDER BY created_at ASC NULLS LAST LIMIT 1
                ) u
                WHERE a.user_id IS NULL
                  AND (SELECT COUNT(*) FROM paper_trading_accounts WHERE user_id IS NULL) = 1
                  AND (SELECT COUNT(*) FROM users) >= 1
                  AND a.id = (SELECT MIN(id) FROM paper_trading_accounts WHERE user_id IS NULL)
                """
            )
        )
    except Exception:
        # SQLite / empty users — ignore backfill
        pass

    # Unique index on user_id (allows multiple NULLs on Postgres for orphans)
    indexes = {ix["name"] for ix in inspector.get_indexes("paper_trading_accounts")}
    if "ix_paper_trading_accounts_user_id" not in indexes and "uq_paper_trading_accounts_user_id" not in indexes:
        try:
            op.create_index(
                "ix_paper_trading_accounts_user_id",
                "paper_trading_accounts",
                ["user_id"],
                unique=True,
            )
        except Exception:
            op.create_index(
                "ix_paper_trading_accounts_user_id",
                "paper_trading_accounts",
                ["user_id"],
                unique=False,
            )

    fks = {fk["name"] for fk in inspector.get_foreign_keys("paper_trading_accounts")}
    if "fk_paper_trading_accounts_user_id_users" not in fks:
        try:
            op.create_foreign_key(
                "fk_paper_trading_accounts_user_id_users",
                "paper_trading_accounts",
                "users",
                ["user_id"],
                ["id"],
                ondelete="CASCADE",
            )
        except Exception:
            pass


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "paper_trading_accounts" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("paper_trading_accounts")}
    if "user_id" not in columns:
        return
    try:
        op.drop_constraint("fk_paper_trading_accounts_user_id_users", "paper_trading_accounts", type_="foreignkey")
    except Exception:
        pass
    try:
        op.drop_index("ix_paper_trading_accounts_user_id", table_name="paper_trading_accounts")
    except Exception:
        pass
    op.drop_column("paper_trading_accounts", "user_id")
