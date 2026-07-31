"""026_remove_multi_user: decouple broker/paper FKs and drop multi-user tables

Revision ID: 026_remove_multi_user
Revises: 20260723_widen_reason_codes
Create Date: 2026-07-31

PRODUCTION CUTOVER (mandatory before upgrade):
1. Take a full PostgreSQL snapshot / backup. This revision is NOT reversible via
   ``alembic downgrade`` (auth tables are dropped permanently).
2. Confirm deploy topology is trusted-only (private network / VPN / allowlisted
   reverse proxy). User JWT auth is removed after this migration.
3. Ensure ``TOKEN_ENCRYPTION_KEY`` and ``API_KEY`` are set for production.

Multi-row safety:
- Paper accounts: unique(user_id) may exist. Only ONE account is bound to the
  static owner UUID; other accounts keep user_id NULL (orphans; still reachable
  by id for ops if needed).
- Broker tokens: at most one row per broker is retained (prefer active + newest);
  survivors are assigned the static owner UUID so UNIQUE(user_id, broker) holds.
"""

from __future__ import annotations

import logging

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "026_remove_multi_user"
down_revision = "20260723_widen_reason_codes"
branch_labels = None
depends_on = None

SYSTEM_OWNER_ID = "00000000-0000-0000-0000-000000000001"
logger = logging.getLogger("alembic.026_remove_multi_user")


def _table_exists(inspector: sa.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def _drop_fk_if_present(inspector: sa.Inspector, table: str, *names: str) -> None:
    if not _table_exists(inspector, table):
        return
    existing = {fk.get("name") for fk in inspector.get_foreign_keys(table)}
    for name in names:
        if name and name in existing:
            op.drop_constraint(name, table, type_="foreignkey")
            logger.info("Dropped FK %s on %s", name, table)
        else:
            # Best-effort for alternate historical names (IF EXISTS for PG)
            op.execute(f"ALTER TABLE IF EXISTS {table} DROP CONSTRAINT IF EXISTS {name};")


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    logger.info(
        "026_remove_multi_user upgrade starting | owner=%s | backup_required=true",
        SYSTEM_OWNER_ID,
    )

    # 1. Drop FK constraints pointing to users.id (names vary by historical migration)
    _drop_fk_if_present(
        inspector,
        "paper_trading_accounts",
        "fk_paper_trading_accounts_user_id_users",
        "fk_paper_trading_accounts_user_id",
        "paper_trading_accounts_user_id_fkey",
    )
    _drop_fk_if_present(
        inspector,
        "broker_tokens",
        "fk_broker_tokens_user_id",
        "broker_tokens_user_id_fkey",
    )
    _drop_fk_if_present(
        inspector,
        "user_profiles",
        "user_profiles_user_id_fkey",
        "fk_user_profiles_user_id",
    )

    # Refresh inspector after DDL
    inspector = sa.inspect(conn)

    # 2. Temporarily relax uniqueness that would block multi-row consolidation.
    if _table_exists(inspector, "paper_trading_accounts"):
        op.execute("DROP INDEX IF EXISTS ix_paper_trading_accounts_user_id;")
        op.execute(
            "ALTER TABLE IF EXISTS paper_trading_accounts "
            "DROP CONSTRAINT IF EXISTS uq_paper_trading_accounts_user_id;"
        )
    if _table_exists(inspector, "broker_tokens"):
        op.execute(
            "ALTER TABLE IF EXISTS broker_tokens "
            "DROP CONSTRAINT IF EXISTS uq_broker_tokens_user_broker;"
        )

    # 3. Paper accounts — bind exactly one primary account to SYSTEM_OWNER_ID.
    if _table_exists(inspector, "paper_trading_accounts"):
        paper_count = conn.execute(
            sa.text("SELECT COUNT(*) FROM paper_trading_accounts")
        ).scalar()
        logger.info("paper_trading_accounts rows before consolidate=%s", paper_count)
        op.execute(
            sa.text(
                """
                UPDATE paper_trading_accounts
                SET user_id = NULL
                WHERE id IS NOT NULL
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                UPDATE paper_trading_accounts
                SET user_id = '{SYSTEM_OWNER_ID}'
                WHERE id = (SELECT MIN(id) FROM paper_trading_accounts)
                """
            )
        )
        owner_bound = conn.execute(
            sa.text(
                f"""
                SELECT COUNT(*) FROM paper_trading_accounts
                WHERE user_id = '{SYSTEM_OWNER_ID}'
                """
            )
        ).scalar()
        logger.info("paper accounts bound to owner=%s (expect 0 or 1)", owner_bound)
    else:
        logger.warning("paper_trading_accounts missing; skip paper owner bind")

    # 4. Broker tokens — keep one row per broker (active preferred, then newest id).
    if _table_exists(inspector, "broker_tokens"):
        broker_count = conn.execute(sa.text("SELECT COUNT(*) FROM broker_tokens")).scalar()
        logger.info("broker_tokens rows before dedupe=%s", broker_count)
        # NOT EXISTS avoids NOT IN empty-set edge cases and is multi-row safe.
        op.execute(
            sa.text(
                """
                DELETE FROM broker_tokens bt
                WHERE EXISTS (
                    SELECT 1
                    FROM broker_tokens other
                    WHERE UPPER(other.broker) = UPPER(bt.broker)
                      AND (
                            (COALESCE(other.is_active, false) AND NOT COALESCE(bt.is_active, false))
                         OR (
                              COALESCE(other.is_active, false) = COALESCE(bt.is_active, false)
                              AND other.id > bt.id
                            )
                      )
                )
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                UPDATE broker_tokens
                SET user_id = '{SYSTEM_OWNER_ID}'
                WHERE user_id IS DISTINCT FROM '{SYSTEM_OWNER_ID}'::uuid
                   OR user_id IS NULL
                """
            )
        )
        # Explicit statement retained for ops readability / static review:
        # UPDATE broker_tokens SET user_id = owner after dedupe.

        after = conn.execute(sa.text("SELECT COUNT(*) FROM broker_tokens")).scalar()
        logger.info("broker_tokens rows after dedupe+owner bind=%s", after)
    else:
        logger.warning("broker_tokens missing; skip broker owner bind")

    # 5. Restore uniqueness under single-owner model.
    if _table_exists(inspector, "paper_trading_accounts"):
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_paper_trading_accounts_user_id "
            "ON paper_trading_accounts (user_id) "
            "WHERE user_id IS NOT NULL;"
        )
    if _table_exists(inspector, "broker_tokens"):
        op.execute(
            "ALTER TABLE IF EXISTS broker_tokens "
            "DROP CONSTRAINT IF EXISTS uq_broker_tokens_user_broker;"
        )
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = 'broker_tokens'
                ) AND NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'uq_broker_tokens_user_broker'
                ) THEN
                    ALTER TABLE broker_tokens
                    ADD CONSTRAINT uq_broker_tokens_user_broker UNIQUE (user_id, broker);
                END IF;
            END $$;
            """
        )

    # 6. Drop multi-user tables (auth / profile stack).
    op.execute("DROP TABLE IF EXISTS user_profiles CASCADE;")
    op.execute("DROP TABLE IF EXISTS otps CASCADE;")
    op.execute("DROP TABLE IF EXISTS audit_logs CASCADE;")
    op.execute("DROP TABLE IF EXISTS devices CASCADE;")
    op.execute("DROP TABLE IF EXISTS user_sessions CASCADE;")
    op.execute("DROP TABLE IF EXISTS users CASCADE;")
    logger.info("Dropped multi-user tables if present (users/sessions/devices/otps/audit/profiles)")

    logger.info(
        "026_remove_multi_user upgrade complete | irreversible=true | "
        "restore_from_snapshot_only=true"
    )


def downgrade() -> None:
    """Irreversible: multi-user auth tables are not recreated.

    Restore from the mandatory pre-upgrade database snapshot instead of
    relying on alembic downgrade for this revision.
    """
    logger.error(
        "026_remove_multi_user downgrade is a no-op; restore from pre-upgrade snapshot"
    )
    pass
