"""Merge research persistence and broker tokens branches.

Revision ID: merge_research_broker_heads
Revises: add_research_persistence_tables, broker_tokens_schema_widen
Create Date: 2026-07-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "merge_research_broker_heads"
down_revision: Union[str, Sequence[str], None] = (
    "add_research_persistence_tables",
    "broker_tokens_schema_widen",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
