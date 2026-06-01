import asyncio
import traceback
from datetime import datetime

from ..models.system_log import SystemLog
from ..db.session import AsyncSessionLocal

async def log_to_db(level: str, module: str, message: str, endpoint: str = None, tb: str = None):
    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                log_entry = SystemLog(
                    timestamp=datetime.utcnow(),
                    level=level,
                    module=module,
                    message=message,
                    endpoint=endpoint,
                    traceback=tb
                )
                db.add(log_entry)
    except Exception as e:
        print(f"Failed to log to DB: {e}")
