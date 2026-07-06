"""remove_refresh_token

Revision ID: 7b6abc0bf8bc
Revises: beaf8450de15
Create Date: 2026-07-04

Remove legacy refresh token columns (this file was previously deleted; restored for history consistency).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7b6abc0bf8bc'
down_revision: Union[str, Sequence[str], None] = 'ef3018463b93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE fyers_tokens DROP COLUMN IF EXISTS refresh_token")
    op.execute("ALTER TABLE fyers_tokens DROP COLUMN IF EXISTS refresh_token_expires_at")
    op.execute("ALTER TABLE fyers_tokens DROP COLUMN IF EXISTS last_auto_renewal_at")
    op.execute("ALTER TABLE fyers_tokens DROP COLUMN IF EXISTS last_auto_renewal_status")


def downgrade() -> None:
    op.add_column('fyers_tokens', sa.Column('refresh_token', sa.Text(), nullable=True))
    op.add_column('fyers_tokens', sa.Column('refresh_token_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('fyers_tokens', sa.Column('last_auto_renewal_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('fyers_tokens', sa.Column('last_auto_renewal_status', sa.String(length=32), nullable=True))
