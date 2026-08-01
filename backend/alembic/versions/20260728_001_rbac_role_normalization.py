"""Normalize user role values and add check constraint.

Revision ID: 20260728_001_rbac_role_normalization
Revises: 20260723_widen_reason_codes
Create Date: 2026-07-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260728_001_rbac_role_normalization"
down_revision: Union[str, Sequence[str], None] = "20260723_widen_reason_codes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Keep in sync with backend/app/models/auth.py CheckConstraint name.
ROLE_CHECK_CONSTRAINT = "ck_users_role_valid"


def _has_check_constraint(inspector: sa.Inspector, table: str, name: str) -> bool:
    """Return True if a check constraint with the given name exists (best-effort)."""
    try:
        for c in inspector.get_check_constraints(table):
            if c.get("name") == name:
                return True
    except NotImplementedError:
        # Dialect cannot list check constraints — fall through to SQL probe.
        pass
    except Exception:
        pass

    # Fallback: probe information_schema / sqlite_master (L-4).
    bind = inspector.bind
    try:
        dialect = bind.dialect.name
        if dialect == "postgresql":
            row = bind.execute(
                sa.text(
                    "SELECT 1 FROM pg_constraint "
                    "WHERE conname = :name AND contype = 'c' LIMIT 1"
                ),
                {"name": name},
            ).fetchone()
            return row is not None
        if dialect == "sqlite":
            # SQLite stores CHECK inline; name may appear in table SQL.
            row = bind.execute(
                sa.text("SELECT sql FROM sqlite_master WHERE type='table' AND name=:t"),
                {"t": table},
            ).fetchone()
            if row and row[0] and name in row[0]:
                return True
    except Exception:
        return False
    return False


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    if "users" not in tables:
        return

    # 1. Normalize existing role values (case-insensitive admin; everything else trader).
    op.execute("UPDATE users SET role = 'admin' WHERE LOWER(role) = 'admin'")
    op.execute("UPDATE users SET role = 'trader' WHERE LOWER(role) != 'admin' OR role IS NULL")

    # 2. Set server default + NOT NULL.
    op.alter_column(
        "users",
        "role",
        server_default="trader",
        existing_type=sa.String(50),
        nullable=False,
    )

    # 3. Add CHECK constraint idempotently — do not swallow real create failures.
    if not _has_check_constraint(inspector, "users", ROLE_CHECK_CONSTRAINT):
        op.create_check_constraint(
            ROLE_CHECK_CONSTRAINT,
            "users",
            "role IN ('trader', 'admin')",
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "users" not in inspector.get_table_names():
        return

    if _has_check_constraint(inspector, "users", ROLE_CHECK_CONSTRAINT):
        op.drop_constraint(ROLE_CHECK_CONSTRAINT, "users", type_="check")
