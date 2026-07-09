"""add google oauth fields to users

Revision ID: add_google_oauth_fields
Revises: 516667d3e077
Create Date: 2026-07-08 15:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'add_google_oauth_fields'
down_revision: Union[str, None] = '516667d3e077'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('google_id', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('provider', sa.String(length=50), nullable=False, server_default='email'))
    op.add_column('users', sa.Column('profile_picture', sa.Text(), nullable=True))
    op.create_index('ix_users_google_id', 'users', ['google_id'])


def downgrade() -> None:
    op.drop_index('ix_users_google_id', table_name='users')
    op.drop_column('users', 'profile_picture')
    op.drop_column('users', 'provider')
    op.drop_column('users', 'google_id')
