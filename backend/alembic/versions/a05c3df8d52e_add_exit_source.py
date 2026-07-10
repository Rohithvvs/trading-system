"""add exit_source

Revision ID: a05c3df8d52e
Revises: 303dcf639306
Create Date: 2026-06-18 18:13:25.323646

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a05c3df8d52e'
down_revision: Union[str, Sequence[str], None] = '303dcf639306'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    columns = [col['name'] for col in inspector.get_columns('paper_trading_trade_history')]
    if 'exit_source' not in columns:
        op.add_column('paper_trading_trade_history', sa.Column('exit_source', sa.String(length=32), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    columns = [col['name'] for col in inspector.get_columns('paper_trading_trade_history')]
    if 'exit_source' in columns:
        op.drop_column('paper_trading_trade_history', 'exit_source')
