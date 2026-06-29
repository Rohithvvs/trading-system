import asyncio
from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import Session
from backend.app.config import settings
from backend.app.db.base import Base
# ensure all models are imported
from backend.app.models import analysis, fyers_token, market_data, paper_trading, stock, system_log, workstation
import json

def check_schema():
    sync_url = settings.database_url.replace("+asyncpg", "+psycopg2").replace("sqlite+aiosqlite", "sqlite")
    engine = create_engine(sync_url)
    
    # Reflect the current database schema
    db_metadata = MetaData()
    db_metadata.reflect(bind=engine)
    
    db_tables = set(db_metadata.tables.keys())
    model_tables = set(Base.metadata.tables.keys())
    
    missing_in_db = model_tables - db_tables
    extra_in_db = db_tables - model_tables
    
    report = {
        "missing_tables": list(missing_in_db),
        "extra_tables": list(extra_in_db),
        "missing_columns": {}
    }
    
    # For common tables, check missing columns
    for table_name in db_tables.intersection(model_tables):
        db_cols = set(db_metadata.tables[table_name].columns.keys())
        model_cols = set(Base.metadata.tables[table_name].columns.keys())
        
        missing_cols = model_cols - db_cols
        if missing_cols:
            report["missing_columns"][table_name] = list(missing_cols)
            
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    check_schema()
