import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata

from backend.app.db.base import Base
import backend.app.models
import backend.app.models.paper_trading
import backend.app.models.analysis
import backend.app.models.stock
import backend.app.models.system_log

from backend.app.config import settings

def main():
    sync_url = settings.database_url.replace("+asyncpg", "+psycopg2")
    engine = create_engine(sync_url)
    
    tables_to_exclude = {
        'migration_checkpoints', 'idempotency_records', 'live_accounts', 'live_orders', 'live_positions',
        'broker_execution_logs', 'order_execution_events', 'dead_letter_jobs', 'api_request_logs',
        'service_health', 'system_locks', 'blacklisted_symbols', 'historical_candles', 'empty_gaps',
        'ltp_cache', 'scan_results'
    }

    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        diff = compare_metadata(context, Base.metadata)
        
        missing_objects = []
        for op in diff:
            op_type = op[0]
            if op_type == 'add_table':
                if op[1].name in tables_to_exclude or op[1].schema == 'market_data':
                    continue
                missing_objects.append(op)
            elif op_type == 'add_column':
                if op[2] in tables_to_exclude or op[1] == 'market_data':
                    continue
                missing_objects.append(op)
            elif op_type == 'add_index':
                if op[1].table.name in tables_to_exclude or op[1].table.schema == 'market_data':
                    continue
                missing_objects.append(op)
                
        if missing_objects:
            print("X VALIDATION FAILED: The following baseline objects are STILL MISSING in production:")
            for op in missing_objects:
                print(f"  - {op}")
            print("\nSTOP. Do NOT execute `alembic stamp 7fa0ff0cccb8`.")
            sys.exit(1)
        else:
            print("OK VALIDATION SUCCESS: All baseline tables, columns, and indexes exist in production.")
            print("It is now safe to execute `alembic stamp 7fa0ff0cccb8`.")
            sys.exit(0)

if __name__ == "__main__":
    main()
