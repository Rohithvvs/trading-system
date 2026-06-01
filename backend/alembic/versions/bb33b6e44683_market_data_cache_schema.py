"""market_data_cache_schema

Revision ID: bb33b6e44683
Revises: 86d16197228e
Create Date: 2026-05-29 09:00:41.872469

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bb33b6e44683'
down_revision: Union[str, Sequence[str], None] = '86d16197228e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    if conn.dialect.name == 'sqlite':
        op.execute("""
            CREATE TABLE candles (
                symbol VARCHAR NOT NULL,
                resolution VARCHAR NOT NULL,
                date TIMESTAMP NOT NULL,
                open NUMERIC(18,8),
                high NUMERIC(18,8),
                low NUMERIC(18,8),
                close NUMERIC(18,8),
                volume BIGINT,
                fetched_at TIMESTAMP,
                PRIMARY KEY (symbol, resolution, date)
            )
        """)
        op.execute("""
            CREATE TABLE scan_results (
                id INT PRIMARY KEY,
                payload TEXT NOT NULL,
                computed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        op.execute("""
            CREATE TABLE empty_gaps (
                symbol VARCHAR NOT NULL,
                gap_date DATE NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                PRIMARY KEY (symbol, gap_date)
            )
        """)
        op.execute("""
            CREATE TABLE ltp_cache (
                symbol VARCHAR PRIMARY KEY,
                ltp NUMERIC(18,8),
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    else:
        # Create the schema
        op.execute("CREATE SCHEMA IF NOT EXISTS market_data")

        # 1. market_data.candles (Partitioned by resolution and date)
        op.execute("""
            CREATE TABLE market_data.candles (
                symbol VARCHAR NOT NULL,
                resolution VARCHAR NOT NULL,
                date TIMESTAMPTZ NOT NULL,
                open NUMERIC(18,8),
                high NUMERIC(18,8),
                low NUMERIC(18,8),
                close NUMERIC(18,8),
                volume BIGINT,
                fetched_at TIMESTAMPTZ,
                PRIMARY KEY (symbol, resolution, date)
            ) PARTITION BY LIST (resolution);
        """)

        # Create initial tier 1 partitions (which are themselves partitioned by RANGE on date)
        op.execute("""
            CREATE TABLE market_data.candles_1d PARTITION OF market_data.candles
                FOR VALUES IN ('1D', '1d', 'D')
                PARTITION BY RANGE (date);
        """)
        op.execute("""
            CREATE TABLE market_data.candles_15m PARTITION OF market_data.candles
                FOR VALUES IN ('15m', '15', '15M')
                PARTITION BY RANGE (date);
        """)
        op.execute("""
            CREATE TABLE market_data.candles_1m PARTITION OF market_data.candles
                FOR VALUES IN ('1m', '1', '1M')
                PARTITION BY RANGE (date);
        """)

        # 2. market_data.scan_results (Singleton JSONB)
        op.execute("""
            CREATE TABLE market_data.scan_results (
                id INT PRIMARY KEY,
                payload JSONB NOT NULL,
                computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # 3. market_data.empty_gaps (UNLOGGED)
        op.execute("""
            CREATE UNLOGGED TABLE market_data.empty_gaps (
                symbol VARCHAR NOT NULL,
                gap_date DATE NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                PRIMARY KEY (symbol, gap_date)
            )
        """)
        
        # 4. market_data.ltp_cache (UNLOGGED) - optimization mentioned in review
        op.execute("""
            CREATE UNLOGGED TABLE market_data.ltp_cache (
                symbol VARCHAR PRIMARY KEY,
                ltp NUMERIC(18,8),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    if conn.dialect.name == 'sqlite':
        op.execute("DROP TABLE IF EXISTS ltp_cache")
        op.execute("DROP TABLE IF EXISTS empty_gaps")
        op.execute("DROP TABLE IF EXISTS scan_results")
        op.execute("DROP TABLE IF EXISTS candles")
    else:
        op.execute("DROP TABLE IF EXISTS market_data.ltp_cache")
        op.execute("DROP TABLE IF EXISTS market_data.empty_gaps")
        op.execute("DROP TABLE IF EXISTS market_data.scan_results")
        op.execute("DROP TABLE IF EXISTS market_data.candles CASCADE")
        op.execute("DROP SCHEMA IF EXISTS market_data")
