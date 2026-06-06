import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from sqlalchemy.schema import CreateTable, CreateIndex

from app.db.base import Base
import app.models
import app.models.paper_trading
import app.models.analysis
import app.models.stock
import app.models.system_log

from app.config import settings

def main(out_f):
    sync_url = settings.database_url.replace("+asyncpg", "+psycopg2")
    engine = create_engine(sync_url)
    
    # Exclude objects from migrations *after* 7fa0ff0cccb8
    tables_to_exclude = {
        'migration_checkpoints', 'idempotency_records', 'live_accounts', 'live_orders', 'live_positions',
        'broker_execution_logs', 'order_execution_events', 'dead_letter_jobs', 'api_request_logs',
        'service_health', 'system_locks', 'blacklisted_symbols', 'historical_candles', 'empty_gaps',
        'ltp_cache', 'scan_results'
    }

    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        diff = compare_metadata(context, Base.metadata)
        
        out_f.write("-- ==========================================================\n")
        out_f.write("-- PHASE 3 PRE-STAMP RECOVERY SCRIPT\n")
        out_f.write("-- Generated dynamically from Alembic schema comparison\n")
        out_f.write("-- ==========================================================\n\n")
        
        for op in diff:
            op_type = op[0]
            
            if op_type == 'add_table':
                table = op[1]
                if table.name in tables_to_exclude or table.schema == 'market_data':
                    continue
                create_stmt = str(CreateTable(table).compile(engine)).replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS")
                out_f.write(f"-- Table missing: {table.name}\n")
                out_f.write(f"{create_stmt.strip()};\n\n")
                
                for idx in table.indexes:
                    idx_stmt = str(CreateIndex(idx).compile(engine)).replace("CREATE INDEX", "CREATE INDEX IF NOT EXISTS")
                    out_f.write(f"{idx_stmt.strip()};\n\n")

            elif op_type == 'add_column':
                schema, table_name, column_obj = op[1], op[2], op[3]
                column_name = column_obj.name
                
                if table_name in tables_to_exclude or schema == 'market_data':
                    continue
                    
                col_type = str(column_obj.type.compile(dialect=engine.dialect))
                default_clause = ""
                if column_obj.server_default is not None:
                    if hasattr(column_obj.server_default.arg, 'text'):
                        default_clause = f" DEFAULT {column_obj.server_default.arg.text}"
                    else:
                        default_clause = f" DEFAULT '{column_obj.server_default.arg}'"
                
                out_f.write(f"-- Column missing: {table_name}.{column_name}\n")
                out_f.write(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {col_type}{default_clause};\n\n")
                
            elif op_type == 'add_index':
                index_obj = op[1]
                if index_obj.table.name in tables_to_exclude or index_obj.table.schema == 'market_data':
                    continue
                idx_stmt = str(CreateIndex(index_obj).compile(engine)).replace("CREATE INDEX", "CREATE INDEX IF NOT EXISTS")
                out_f.write(f"-- Index missing: {index_obj.name}\n")
                out_f.write(f"{idx_stmt.strip()};\n\n")

        out_f.write("-- ==========================================================\n")
        out_f.write("-- END OF RECOVERY SCRIPT\n")
        out_f.write("-- ==========================================================\n")

if __name__ == "__main__":
    with open("backend/production_recovery.sql", "w", encoding="utf-8") as f:
        main(f)
