"""rename_article_dedup_log_if_present

Revision ID: 104d02035305
Revises: 104d02035304
Create Date: 2026-07-21

Safe follow-up for environments that already applied the interim
``article_dedup_log`` table name before FR-009 alignment.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "104d02035305"
down_revision: Union[str, Sequence[str], None] = "104d02035304"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "article_dedup_log" in tables and "news_deduplication_audit" not in tables:
        op.rename_table("article_dedup_log", "news_deduplication_audit")
        # Best-effort index renames (ignore if names differ)
        for old, new in (
            ("ix_article_dedup_log_id", "ix_news_deduplication_audit_id"),
            ("ix_article_dedup_log_symbol", "ix_news_deduplication_audit_symbol"),
        ):
            try:
                op.execute(sa.text(f'ALTER INDEX IF EXISTS "{old}" RENAME TO "{new}"'))
            except Exception:
                pass
        # Re-inspect after rename so index names are current
        inspector = sa.inspect(bind)
        existing = {
            idx["name"]
            for idx in inspector.get_indexes("news_deduplication_audit")
        }
        if "ix_news_deduplication_audit_kept_dedup" not in existing:
            op.create_index(
                "ix_news_deduplication_audit_kept_dedup",
                "news_deduplication_audit",
                ["kept_id", "deduplicated_id"],
                unique=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "news_deduplication_audit" in tables and "article_dedup_log" not in tables:
        try:
            op.drop_index(
                "ix_news_deduplication_audit_kept_dedup",
                table_name="news_deduplication_audit",
            )
        except Exception:
            pass
        op.rename_table("news_deduplication_audit", "article_dedup_log")
