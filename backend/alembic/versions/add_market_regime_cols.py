"""add market regime columns

Revision ID: add_market_regime_cols
Revises: add_sector_rs_cols
Create Date: 2026-07-10 14:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "add_market_regime_cols"
down_revision: Union[str, None] = "add_sector_rs_cols"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('analysis_history')]

    new_cols = [
        ('market_state', sa.String(length=20), True),
        ('market_trend_state', sa.String(length=20), True),
        ('market_breadth_state', sa.String(length=20), True),
        ('market_volatility_state', sa.String(length=20), True),
        ('market_new_entry_allowed', sa.Boolean(), True),
        ('market_risk_multiplier', sa.Float(), True)
    ]

    for name, type_, nullable in new_cols:
        if name not in columns:
            op.add_column('analysis_history', sa.Column(name, type_, nullable=nullable))

def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('analysis_history')]

    new_cols = [
        'market_state',
        'market_trend_state',
        'market_breadth_state',
        'market_volatility_state',
        'market_new_entry_allowed',
        'market_risk_multiplier'
    ]

    with op.batch_alter_table('analysis_history') as batch_op:
        for name in new_cols:
            if name in columns:
                batch_op.drop_column(name)
