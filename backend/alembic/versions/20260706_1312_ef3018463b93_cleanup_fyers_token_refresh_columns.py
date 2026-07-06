"""cleanup_fyers_token_refresh_columns

Revision ID: ef3018463b93
Revises: beaf8450de15
Create Date: 2026-07-06

Remove all refresh token and auto-renewal columns from fyers_tokens.
Only access token support remains.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ef3018463b93'
down_revision: Union[str, Sequence[str], None] = 'beaf8450de15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop refresh/auto-renewal columns if they exist (idempotent)."""
    # Use IF EXISTS for safety across environments where prior remove migration may or may not have run.
    op.execute("ALTER TABLE fyers_tokens DROP COLUMN IF EXISTS refresh_token")
    op.execute("ALTER TABLE fyers_tokens DROP COLUMN IF EXISTS refresh_token_expires_at")
    op.execute("ALTER TABLE fyers_tokens DROP COLUMN IF EXISTS last_auto_renewal_at")
    op.execute("ALTER TABLE fyers_tokens DROP COLUMN IF EXISTS last_auto_renewal_status")


def downgrade() -> None:
    """Re-add columns (for rollback only - data will be NULL)."""
    op.add_column('fyers_tokens', sa.Column('refresh_token', sa.Text(), nullable=True))
    op.add_column('fyers_tokens', sa.Column('refresh_token_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('fyers_tokens', sa.Column('last_auto_renewal_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('fyers_tokens', sa.Column('last_auto_renewal_status', sa.String(length=32), nullable=True))
