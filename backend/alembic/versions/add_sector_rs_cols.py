"""add sector relative strength columns

Revision ID: add_sector_rs_cols
Revises: add_backtest_realism_metrics
Create Date: 2026-07-10 13:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "add_sector_rs_cols"
down_revision: Union[str, None] = "add_backtest_realism_metrics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('analysis_history')]

    new_cols = [
        ('mapped_sector', sa.String(length=50), True),
        ('sector_rs_20', sa.Float(), True),
        ('sector_close_vs_ema20', sa.Boolean(), True),
        ('sector_filter_triggered', sa.Boolean(), True),
        ('original_signal', sa.String(length=20), True),
        ('challenger_signal', sa.String(length=20), True),
        ('reason_codes', sa.String(length=100), True)
    ]

    for name, type_, nullable in new_cols:
        if name not in columns:
            op.add_column('analysis_history', sa.Column(name, type_, nullable=nullable))

def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('analysis_history')]

    new_cols = [
        'mapped_sector',
        'sector_rs_20',
        'sector_close_vs_ema20',
        'sector_filter_triggered',
        'original_signal',
        'challenger_signal',
        'reason_codes'
    ]

    with op.batch_alter_table('analysis_history') as batch_op:
        for name in new_cols:
            if name in columns:
                batch_op.drop_column(name)
