import asyncio
import os
import sys
import uuid
import datetime
import logging
from sqlalchemy import select

# Configure path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from backend.app.models.market_data import ScanSnapshot
from backend.app.db.session import AsyncSessionLocal
from backend.app.services.scan_execution_service import ScanExecutionService
from backend.app.services.lock_service import DistributedLockService
from backend.app.schemas import ScreenerRequest, AnalysisMode, TimeframeConfig

# Basic schema wrapper
class TestScreenerRequest(ScreenerRequest):
    def __init__(self, **data):
        super().__init__(**data)

async def check_scan_snapshot(scan_id):
    async with AsyncSessionLocal() as db:
        stmt = select(ScanSnapshot).where(ScanSnapshot.scan_id == scan_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

async def main():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("audit_observability")
    
    logger.info("Starting Observability Audit...")

    payload = ScreenerRequest(
        mode=AnalysisMode.FULL,
        symbols=["TCS", "INFY"],
        timeframe=TimeframeConfig()
    )

    # 1. Test Lock Overlap
    logger.info("=== Test 1: Lock Overlap ===")
    lock = DistributedLockService("scan_execution", ttl_seconds=3600)
    acquired = await lock.acquire(timeout_seconds=0)
    
    if acquired:
        logger.info("Lock successfully acquired for mock background.")
        
        # Now try to call execute_scan which should fail and raise LockAcquisitionError
        try:
            await ScanExecutionService.execute_scan(payload, None, trigger_source="cron")
            logger.error("Test 1 Failed: Overlap did not raise LockAcquisitionError")
        except Exception as e:
            if type(e).__name__ == "LockAcquisitionError":
                logger.info("Test 1 Passed: Overlap raised LockAcquisitionError cleanly.")
            else:
                logger.error(f"Test 1 Failed: Wrong exception {e}")
        finally:
            await lock.release()
    else:
        logger.error("Could not acquire initial lock for Test 1")

if __name__ == "__main__":
    asyncio.run(main())
