"""Add last_reconciled_at to PaperPosition

Revision ID: 303dcf639306
Revises: 761f3802942c
Create Date: 2026-06-18 17:09:25.975001

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '303dcf639306'
down_revision: Union[str, Sequence[str], None] = '761f3802942c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    # paper_trading_positions columns
    ptp_columns = [col['name'] for col in inspector.get_columns('paper_trading_positions')]
    if 'last_evaluated_at' not in ptp_columns:
        op.add_column('paper_trading_positions', sa.Column('last_evaluated_at', sa.DateTime(timezone=True), nullable=True))
    if 'last_reconciled_at' not in ptp_columns:
        op.add_column('paper_trading_positions', sa.Column('last_reconciled_at', sa.DateTime(timezone=True), nullable=True))
        
    # scan_snapshots columns
    ss_columns = [col['name'] for col in inspector.get_columns('scan_snapshots')]
    if 'status' not in ss_columns:
        # Provide a server_default just in case the table has data
        op.add_column('scan_snapshots', sa.Column('status', sa.String(length=50), nullable=False, server_default='completed'))
    if 'error_type' not in ss_columns:
        op.add_column('scan_snapshots', sa.Column('error_type', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    ss_columns = [col['name'] for col in inspector.get_columns('scan_snapshots')]
    if 'error_type' in ss_columns:
        op.drop_column('scan_snapshots', 'error_type')
    if 'status' in ss_columns:
        op.drop_column('scan_snapshots', 'status')
        
    ptp_columns = [col['name'] for col in inspector.get_columns('paper_trading_positions')]
    if 'last_reconciled_at' in ptp_columns:
        op.drop_column('paper_trading_positions', 'last_reconciled_at')
    if 'last_evaluated_at' in ptp_columns:
        op.drop_column('paper_trading_positions', 'last_evaluated_at')
    # ### end Alembic commands ###
