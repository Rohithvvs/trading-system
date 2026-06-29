import asyncio
import httpx
import json
import time
import subprocess
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Path and configs
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))
from backend.app.config import settings

async def main():
    print("Dropping scan_snapshots...")
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS scan_snapshots CASCADE"))
    print("Done dropping.")

    print("Recreating tables...")
    proc_create = subprocess.run(["python", "create_tables.py"], capture_output=True, text=True)
    print(proc_create.stdout)

    print("Booting uvicorn...")
    server = subprocess.Popen(["python", "-m", "uvicorn", "backend.app.main:app", "--port", "8008"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    await asyncio.sleep(4)

    client = httpx.AsyncClient(base_url="http://127.0.0.1:8008", headers={"X-Scheduler-Secret": os.environ.get("SCHEDULER_SECRET", "test_secret")})
    
    # We don't have SCHEDULER_SECRET in os.environ for uvicorn process possibly, so it might return 403 or 401. Let's see. 
    # Actually, uvicorn inherits environment. 

    try:
        print("--- Validation 1: Start Scan ---")
        payload = {"mode": "FULL", "symbols": ["TCS", "INFY"], "timeframe": {}}
        res1 = await client.post("/scheduler/daily-scan", json=payload)
        print("Response 1:", res1.status_code, res1.text)
        
        await asyncio.sleep(1)

        print("--- Validation 2: Overlap Scan ---")
        res2 = await client.post("/scheduler/daily-scan", json=payload)
        print("Response 2:", res2.status_code, res2.text)

        print("--- Validation 3: Status While Running ---")
        res3 = await client.get("/scheduler/status")
        print("Response 3:", res3.status_code, res3.json())

        print("Waiting for scan to complete...")
        for _ in range(15):
            await asyncio.sleep(1)
            r = await client.get("/scheduler/status")
            if r.json().get("last_scan_status") == "COMPLETED":
                print("--- Validation 4: Status After Complete ---")
                print("Response 4:", r.status_code, r.json())
                break
        else:
            print("Timeout waiting for completion.")

        print("--- Validation 5: DB Verification ---")
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT scan_id, status, error_type, scan_duration_ms FROM scan_snapshots ORDER BY scan_timestamp DESC LIMIT 1"))
            row = result.fetchone()
            if row:
                print(f"DB Row: scan_id={row[0]}, status={row[1]}, error_type={row[2]}, duration_ms={row[3]}")
            else:
                print("DB Row: Not found")

        print("--- Validation 6: Failure Path ---")
        # Simulating failure by triggering a scan with a mode that causes exception?
        # Let's send invalid timeframe to trigger pydantic error, but that fails before execute_scan.
        # How to trigger orchestrator crash? Pass unknown symbol that throws.
        payload_fail = {"mode": "FULL", "symbols": ["CRASH_SYMBOL"], "timeframe": {}}
        res_fail = await client.post("/scheduler/daily-scan", json=payload_fail)
        print("Response Fail Start:", res_fail.status_code, res_fail.text)
        
        for _ in range(15):
            await asyncio.sleep(1)
            r = await client.get("/scheduler/status")
            if r.json().get("last_scan_status") == "FAILED":
                print("--- Validation 6: Status After Failure ---")
                print("Response 6:", r.status_code, r.json())
                break
        
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT scan_id, status, error_type, scan_duration_ms FROM scan_snapshots ORDER BY scan_timestamp DESC LIMIT 1"))
            row = result.fetchone()
            if row:
                print(f"DB Row (Fail): scan_id={row[0]}, status={row[1]}, error_type={row[2]}, duration_ms={row[3]}")

    finally:
        print("Shutting down uvicorn...")
        server.terminate()
        server.wait(timeout=5)
        
        # Read server logs
        stdout, stderr = server.communicate()
        with open("server_validation_logs.txt", "w") as f:
            f.write(stdout)
            f.write("\n--- STDERR ---\n")
            f.write(stderr)
        print("Logs saved to server_validation_logs.txt")

if __name__ == "__main__":
    asyncio.run(main())
