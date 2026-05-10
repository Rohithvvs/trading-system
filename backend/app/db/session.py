from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import settings
from .base import Base


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from ..models import analysis as analysis_models  # noqa: F401
    from ..models import paper_trading as paper_trading_models  # noqa: F401
    from ..models import stock as stock_models  # noqa: F401
    from ..models import fyers_token as fyers_token_models  # noqa: F401
    from ..models import workstation as workstation_models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    # Ensure new schema changes are applied for existing SQLite DBs.
    # Specifically add the `status` column to `paper_trading_positions` if missing.
    if settings.database_url.startswith("sqlite"):
        try:
            with engine.begin() as conn:
                res = conn.exec_driver_sql("PRAGMA table_info('paper_trading_positions')").mappings().all()
                cols = [r.get('name') for r in res] if res else []
                if 'status' not in cols:
                    conn.exec_driver_sql("ALTER TABLE paper_trading_positions ADD COLUMN status TEXT DEFAULT 'OPEN'")
                    conn.exec_driver_sql("UPDATE paper_trading_positions SET status = 'OPEN' WHERE status IS NULL")
                # Add missing columns to `paper_trading_orders` if present in models but absent in DB.
                res2 = conn.exec_driver_sql("PRAGMA table_info('paper_trading_orders')").mappings().all()
                cols2 = [r.get('name') for r in res2] if res2 else []
                # Define expected optional columns and the ALTER statements to add them.
                expected_cols = {
                    'product_type': "TEXT DEFAULT 'CNC'",
                    'order_price': "REAL",
                    'stop_price': "REAL",
                    'stop_loss': "REAL",
                    'target': "REAL",
                    'status': "TEXT DEFAULT 'PENDING'",
                    'filled_price': "REAL",
                    'filled_at': "TEXT",
                    'cancelled_at': "TEXT",
                }
                for col, col_def in expected_cols.items():
                    if col not in cols2:
                        try:
                            conn.exec_driver_sql(f"ALTER TABLE paper_trading_orders ADD COLUMN {col} {col_def}")
                        except Exception:
                            # best-effort: continue if column cannot be added
                            pass
                # Ensure no NULLs for defaults where applicable
                try:
                    if 'product_type' in expected_cols and 'product_type' in cols2:
                        conn.exec_driver_sql("UPDATE paper_trading_orders SET product_type = 'CNC' WHERE product_type IS NULL")
                except Exception:
                    pass
                # Add missing columns to `paper_trading_trade_history` if necessary
                res3 = conn.exec_driver_sql("PRAGMA table_info('paper_trading_trade_history')").mappings().all()
                cols3 = [r.get('name') for r in res3] if res3 else []
                if 'exit_reason' not in cols3:
                    try:
                        conn.exec_driver_sql("ALTER TABLE paper_trading_trade_history ADD COLUMN exit_reason TEXT")
                    except Exception:
                        pass
                # Best-effort: ensure any other missing columns present in SQLAlchemy models
                try:
                    from sqlalchemy import Integer, Float, String, Text, DateTime, Boolean

                    for table in Base.metadata.sorted_tables:
                        tname = table.name
                        res_t = conn.exec_driver_sql(f"PRAGMA table_info('{tname}')").mappings().all()
                        existing = {r.get('name') for r in res_t} if res_t else set()
                        for col in table.columns:
                            if col.name in existing:
                                continue
                            # map SQLAlchemy types to SQLite affinity
                            col_type = col.type
                            if isinstance(col_type, Integer):
                                sql_type = 'INTEGER'
                            elif isinstance(col_type, Float):
                                sql_type = 'REAL'
                            elif isinstance(col_type, (String, Text)):
                                sql_type = 'TEXT'
                            elif isinstance(col_type, DateTime):
                                sql_type = 'TEXT'
                            elif isinstance(col_type, Boolean):
                                sql_type = 'INTEGER'
                            else:
                                sql_type = 'TEXT'
                            # Attempt to add the column without NOT NULL constraints
                            try:
                                conn.exec_driver_sql(f"ALTER TABLE {tname} ADD COLUMN {col.name} {sql_type}")
                            except Exception:
                                pass
                except Exception:
                    pass
        except Exception as e:
            print(f"ERROR running init_db migration for paper_trading_positions.status: {e}")
