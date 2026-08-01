"""Add feature_permissions table and seed default features (Sprint 3).

Revision ID: 20260730_001_feature_permissions
Revises: 20260728_001_rbac_role_normalization
Create Date: 2026-07-30
"""

from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260730_001_feature_permissions"
down_revision: Union[str, Sequence[str], None] = "20260728_001_rbac_role_normalization"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEED_FEATURES = [
    ("admin_panel", "Access to the administrative console", '["admin"]', True),
    ("user_management", "List users and change roles", '["admin"]', True),
    ("system_logs", "View system and operational logs", '["admin"]', True),
    ("export_data", "Export data from the platform", '["admin"]', True),
    ("watchlist", "Watchlist management and views", '["trader", "admin"]', True),
    (
        "portfolio_analytics",
        "Portfolio analytics and reports",
        '["trader", "admin"]',
        True,
    ),
    (
        "advanced_scanner",
        "Advanced scanner tools and views",
        '["trader", "admin"]',
        True,
    ),
]


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    if "feature_permissions" not in tables:
        op.create_table(
            "feature_permissions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("feature_key", sa.String(64), nullable=False),
            sa.Column("description", sa.String(255), nullable=False),
            sa.Column(
                "allowed_roles",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            # Unique constraint provides the only index on feature_key (L-1: no redundant ix)
            sa.UniqueConstraint(
                "feature_key", name="uq_feature_permissions_feature_key"
            ),
        )

    # Idempotent seed: app-generated UUIDs (M-4: no gen_random_uuid / pgcrypto dependency)
    for key, desc, roles_json, active in SEED_FEATURES:
        row_id = str(uuid.uuid4())
        op.execute(
            sa.text(
                """
                INSERT INTO feature_permissions (
                    id, feature_key, description, allowed_roles, is_active, created_at, updated_at
                )
                SELECT CAST(:id AS uuid), :key, :desc, CAST(:roles AS jsonb), :active, now(), now()
                WHERE NOT EXISTS (
                    SELECT 1 FROM feature_permissions WHERE feature_key = :key
                )
                """
            ).bindparams(
                id=row_id, key=key, desc=desc, roles=roles_json, active=active
            )
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "feature_permissions" in inspector.get_table_names():
        op.drop_table("feature_permissions")
