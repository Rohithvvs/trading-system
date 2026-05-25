import asyncio
import traceback
from datetime import datetime
from ..db.session import SessionLocal
from ..models.system_log import SystemLog

def log_to_db_sync(level: str, module: str, message: str, endpoint: str = None, tb: str = None):
    try:
        with SessionLocal() as db:
            log_entry = SystemLog(
                timestamp=datetime.utcnow(),
                level=level,
                module=module,
                message=message,
                endpoint=endpoint,
                traceback=tb
            )
            db.add(log_entry)
            db.commit()
    except Exception as e:
        print(f"Failed to log to DB: {e}")

async def log_to_db(level: str, module: str, message: str, endpoint: str = None, tb: str = None):
    # Run DB operation in a separate thread to ensure async-safety and fast execution
    await asyncio.to_thread(log_to_db_sync, level, module, message, endpoint, tb)
