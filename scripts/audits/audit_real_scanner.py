import asyncio
import time
from datetime import datetime

from backend.app.main import automated_screening_job
from backend.app.db.session import AsyncSessionLocal
from backend.app.services.diagnostics_service import diagnostics
from backend.app.services.token_service import get_current_access_token
from sqlalchemy import text

async def main():
    print("--- STARTING REAL SCANNER AUDIT ---")
    
    # Check 1: DB
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        print("1. Database connected: OK")
    except Exception as e:
        print(f"1. Database connected: FAILED ({e})")
        return
        
    # Check 2: FYERS Token
    try:
        async with AsyncSessionLocal() as db:
            token = await get_current_access_token(db)
        from backend.app.config import settings
        if token or settings.fyers_access_token:
            print("2. FYERS token valid: OK")
        else:
            print("2. FYERS token valid: FAILED (No token)")
            return
    except Exception as e:
        print(f"2. FYERS token valid: FAILED ({e})")
        return
        
    print("\n--- EXECUTING REAL SCANNER ---")
    print(f"Start Time: {datetime.utcnow().isoformat()}")
    start_time = time.perf_counter()
    
    await automated_screening_job()
    
    end_time = time.perf_counter()
    print(f"End Time: {datetime.utcnow().isoformat()}")
    total_duration = end_time - start_time
    print(f"Total Duration (seconds): {total_duration:.2f}")
    
    print("\n--- VERIFYING OUTPUT ---")
    if diagnostics.scanner_runs:
        run = diagnostics.scanner_runs[-1]
        print(f"Scanner Status: {diagnostics.last_scan_status}")
        print(f"Total Symbols: {run.get('requested_symbols')}")
        print(f"Valid Symbols: {run.get('valid_symbols')}")
        print(f"Buy Count: {run.get('buy_count')}")
        print(f"Watch Count: {run.get('watch_count')}")
        print(f"Rejected Count: {run.get('rejected_count')}")
    else:
        print("No scanner run found in diagnostics!")
        
    print("\n--- VERIFYING PERSISTENCE ---")
    async with AsyncSessionLocal() as db:
        res1 = await db.execute(text("SELECT count(*) FROM scan_snapshots"))
        res2 = await db.execute(text("SELECT count(*) FROM scan_snapshot_records"))
        
        print(f"scan_snapshots row count: {res1.scalar()}")
        print(f"scan_snapshot_records row count: {res2.scalar()}")
        
        res3 = await db.execute(text("SELECT scan_timestamp FROM scan_snapshots ORDER BY scan_timestamp DESC LIMIT 1"))
        ts = res3.scalar()
        print(f"latest snapshot timestamp: {ts}")

if __name__ == "__main__":
    asyncio.run(main())
