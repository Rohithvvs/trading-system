"""add backtest realism metrics

Revision ID: add_backtest_realism_metrics
Revises: add_reset_password_fields
Create Date: 2026-07-10 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "add_backtest_realism_metrics"
down_revision: Union[str, None] = "add_reset_password_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('backtest_history')]
    
    new_cols = [
        ('gross_total_return', sa.Float(), True),
        ('gross_cagr', sa.Float(), True),
        ('gross_max_drawdown', sa.Float(), True),
        ('gross_win_rate', sa.Float(), True),
        ('gross_profit_factor', sa.Float(), True),
        ('gross_sharpe_ratio', sa.Float(), True),
        ('cost_scenario', sa.String(length=20), True),
        ('total_transaction_costs', sa.Float(), True),
        ('total_slippage', sa.Float(), True),
        ('position_sizing_pct', sa.Float(), True)
    ]
    
    for name, type_, nullable in new_cols:
        if name not in columns:
            op.add_column('backtest_history', sa.Column(name, type_, nullable=nullable))

def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('backtest_history')]
    
    new_cols = [
        'gross_total_return',
        'gross_cagr',
        'gross_max_drawdown',
        'gross_win_rate',
        'gross_profit_factor',
        'gross_sharpe_ratio',
        'cost_scenario',
        'total_transaction_costs',
        'total_slippage',
        'position_sizing_pct'
    ]
    
    with op.batch_alter_table('backtest_history') as batch_op:
        for name in new_cols:
            if name in columns:
                batch_op.drop_column(name)

