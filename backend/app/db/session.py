from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from ..config import settings
from .base import Base


connect_args = {}
pool_kwargs = {"pool_pre_ping": True}

if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    connect_args["timeout"] = 15
else:
    # Increase connection timeout to 120s to allow Render free tier Postgres to wake up
    connect_args["connect_timeout"] = 120
    # Connection Pooling Limits for Neon Serverless
    if "pgbouncer" in settings.database_url.lower():
        from sqlalchemy import NullPool
        pool_kwargs["poolclass"] = NullPool
    else:
        pool_kwargs["pool_size"] = 5
        pool_kwargs["max_overflow"] = 10
        pool_kwargs["pool_timeout"] = 30

engine = create_engine(settings.database_url, connect_args=connect_args, **pool_kwargs)

if not settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_postgres_timeouts(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("SET statement_timeout = '30s'")
        cursor.execute("SET lock_timeout = '5s'")
        cursor.execute("SET idle_in_transaction_session_timeout = '30s'")
        cursor.close()

if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA cache_size=-64000")
        cursor.execute("PRAGMA temp_store=MEMORY")
        
        # Verify and log WAL mode enforcement
        try:
            from ..utils import get_logger
            logger = get_logger("app.db.session")
            
            cursor.execute("PRAGMA journal_mode")
            jm = cursor.fetchone()
            if jm and jm[0].lower() != "wal":
                logger.warning("SQLITE_WAL_WARNING", extra={"expected": "wal", "actual": jm[0]})
                # Attempt correction
                cursor.execute("PRAGMA journal_mode=WAL")
                
            cursor.execute("PRAGMA synchronous")
            sync = cursor.fetchone()
            if sync and str(sync[0]) not in ("1", "NORMAL"):
                logger.warning("SQLITE_SYNC_WARNING", extra={"expected": "NORMAL (1)", "actual": sync[0]})
        except Exception as e:
            print(f"Error verifying pragmas: {e}")
            
        cursor.close()

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
    from ..models import market_data as market_data_models  # noqa: F401
    from ..models import system_log as system_log_models  # noqa: F401

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
                    'lifecycle_state': "TEXT DEFAULT 'PENDING_ENTRY'",
                    'requested_entry_price': "REAL",
                    'monitor_enabled': "INTEGER DEFAULT 1",
                    'paused_reason': "TEXT",
                    'last_evaluated_at': "TEXT",
                    'last_seen_ltp': "REAL",
                    'filled_price': "REAL",
                    'filled_at': "TEXT",
                    'cancelled_at': "TEXT",
                    'idempotency_key': "TEXT",
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
                    conn.exec_driver_sql("UPDATE paper_trading_orders SET lifecycle_state = CASE WHEN status = 'FILLED' THEN 'ENTRY_FILLED' WHEN status = 'CANCELLED' THEN 'CANCELLED' ELSE 'PENDING_ENTRY' END WHERE lifecycle_state IS NULL")
                    conn.exec_driver_sql("UPDATE paper_trading_orders SET requested_entry_price = order_price WHERE requested_entry_price IS NULL")
                    conn.exec_driver_sql("UPDATE paper_trading_orders SET monitor_enabled = 1 WHERE monitor_enabled IS NULL")
                except Exception:
                    pass
                res_pos = conn.exec_driver_sql("PRAGMA table_info('paper_trading_positions')").mappings().all()
                pos_cols = [r.get('name') for r in res_pos] if res_pos else []
                pos_expected = {
                    'lifecycle_state': "TEXT DEFAULT 'OPEN_POSITION'",
                    'monitor_enabled': "INTEGER DEFAULT 1",
                    'paused_reason': "TEXT",
                }
                for col, col_def in pos_expected.items():
                    if col not in pos_cols:
                        try:
                            conn.exec_driver_sql(f"ALTER TABLE paper_trading_positions ADD COLUMN {col} {col_def}")
                        except Exception:
                            pass
                try:
                    conn.exec_driver_sql("UPDATE paper_trading_positions SET lifecycle_state = 'OPEN_POSITION' WHERE lifecycle_state IS NULL")
                    conn.exec_driver_sql("UPDATE paper_trading_positions SET monitor_enabled = 1 WHERE monitor_enabled IS NULL")
                except Exception:
                    pass
                res_notif = conn.exec_driver_sql("PRAGMA table_info('paper_trading_notifications')").mappings().all()
                notif_cols = [r.get('name') for r in res_notif] if res_notif else []
                for col, col_def in {
                    'event_type': "TEXT",
                    'entity_type': "TEXT",
                    'entity_id': "INTEGER",
                    'dedupe_key': "TEXT",
                }.items():
                    if col not in notif_cols:
                        try:
                            conn.exec_driver_sql(f"ALTER TABLE paper_trading_notifications ADD COLUMN {col} {col_def}")
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
                for table_name, col_defs in {
                    "paper_trading_execution_events": {
                        "event_id": "TEXT",
                        "dedupe_key": "TEXT",
                    },
                    "market_replay_sessions": {
                        "replay_key": "TEXT",
                        "status": "TEXT",
                        "gap_start": "TEXT",
                        "gap_end": "TEXT",
                        "checkpoint_symbol": "TEXT",
                        "started_at": "TEXT",
                        "completed_at": "TEXT",
                        "error_message": "TEXT",
                    },
                }.items():
                    res_extra = conn.exec_driver_sql(f"PRAGMA table_info('{table_name}')").mappings().all()
                    extra_cols = {r.get("name") for r in res_extra} if res_extra else set()
                    for col, col_def in col_defs.items():
                        if col not in extra_cols:
                            try:
                                conn.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {col} {col_def}")
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
