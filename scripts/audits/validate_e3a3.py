import asyncio
import httpx
import json
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from backend.app.db.session import AsyncSessionLocal

async def capture_pg_stat():
    async with AsyncSessionLocal() as db:
        res = await db.execute(text("""
            SELECT state, count(*) 
            FROM pg_stat_activity 
            WHERE backend_type = 'client backend' 
            AND datname = current_database()
            GROUP BY state
        """))
        return dict(res.fetchall())

async def run_dashboard_tests(client, count):
    print(f"Executing {count} concurrent dashboard requests...")
    t0 = time.time()
    tasks = [client.get("/paper-trading/account") for _ in range(count)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    success = sum(1 for r in results if getattr(r, 'status_code', 0) == 200)
    failed = len(results) - success
    print(f"Dashboard: {success} passed, {failed} failed in {time.time()-t0:.2f}s")
    return success, failed
    
async def run_market_orders(client, count):
    print(f"Executing {count} concurrent market orders...")
    t0 = time.time()
    payload = {
        "symbol": "INFY-EQ",
        "side": "BUY",
        "type": "MARKET",
        "qty": 1,
        "idempotency_key": ""
    }
    tasks = []
    for i in range(count):
        p = payload.copy()
        p["idempotency_key"] = f"MKT_ORDER_{time.time()}_{i}"
        tasks.append(client.post("/paper-trading/orders", json=p))
        
    results = await asyncio.gather(*tasks, return_exceptions=True)
    success = sum(1 for r in results if getattr(r, 'status_code', 0) == 200)
    failed = len(results) - success
    print(f"Market Orders: {success} passed, {failed} failed in {time.time()-t0:.2f}s")
    return success, failed

async def run_limit_orders(client, count):
    print(f"Executing {count} concurrent limit orders...")
    t0 = time.time()
    payload = {
        "symbol": "RELIANCE-EQ",
        "side": "BUY",
        "type": "LIMIT",
        "qty": 1,
        "stop_price": 2000.0,
        "idempotency_key": ""
    }
    tasks = []
    for i in range(count):
        p = payload.copy()
        p["idempotency_key"] = f"LMT_ORDER_{time.time()}_{i}"
        tasks.append(client.post("/paper-trading/orders", json=p))
        
    results = await asyncio.gather(*tasks, return_exceptions=True)
    success = sum(1 for r in results if getattr(r, 'status_code', 0) == 200)
    failed = len(results) - success
    print(f"Limit Orders: {success} passed, {failed} failed in {time.time()-t0:.2f}s")
    return success, failed

async def run_scanner(client, count):
    print(f"Executing {count} concurrent scanner executions...")
    t0 = time.time()
    payload = {
        "mode": "swing",
        "timeframe": {"swing": "1d"},
        "symbols": ["INFY-EQ", "RELIANCE-EQ"]
    }
    tasks = [client.post("/scanner/run", json=payload, timeout=120.0) for _ in range(count)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    success = sum(1 for r in results if getattr(r, 'status_code', 0) == 200)
    failed = len(results) - success
    print(f"Scanner: {success} passed, {failed} failed in {time.time()-t0:.2f}s")
    for r in results:
        if isinstance(r, Exception):
            print(f"Scanner Exception: {r}")
        elif r.status_code != 200:
            print(f"Scanner Error: {r.status_code} {r.text}")
    return success, failed

async def main():
    print("Capturing pg_stat_activity BEFORE tests...")
    stat_before = await capture_pg_stat()
    print(f"pg_stat_activity BEFORE: {stat_before}")
    
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=120.0) as client:
        res = await asyncio.gather(
            run_dashboard_tests(client, 100),
            run_market_orders(client, 50),
            run_limit_orders(client, 50),
            run_scanner(client, 20)
        )
        
    print("Capturing pg_stat_activity AFTER tests...")
    stat_after = await capture_pg_stat()
    print(f"pg_stat_activity AFTER: {stat_after}")
    
    with open("E3A3_VALIDATION_REPORT.md", "w") as f:
        f.write("# E.3A.3 Remediation Verification Report\n\n")
        f.write("## 1. Environment State Before Load\n")
        f.write(f"```json\n{json.dumps(stat_before, indent=2)}\n```\n\n")
        
        f.write("## 2. Load Execution Results\n")
        f.write(f"- **Dashboard (100)**: {res[0][0]} passed, {res[0][1]} failed\n")
        f.write(f"- **Market Orders (50)**: {res[1][0]} passed, {res[1][1]} failed\n")
        f.write(f"- **Limit Orders (50)**: {res[2][0]} passed, {res[2][1]} failed\n")
        f.write(f"- **Scanner (20)**: {res[3][0]} passed, {res[3][1]} failed\n\n")
        
        f.write("## 3. Environment State After Load\n")
        f.write(f"```json\n{json.dumps(stat_after, indent=2)}\n```\n\n")
        
        idle_before = stat_before.get('idle in transaction', 0)
        idle_after = stat_after.get('idle in transaction', 0)
        
        f.write("## 4. Verification Check\n")
        f.write(f"- `idle in transaction` = 0: **{'PASS' if idle_after == 0 else 'FAIL'}** (was {idle_before}, now {idle_after})\n")
        if all(r[1] == 0 for r in res):
            f.write("- No timeouts / Failures (Dashboard/Orders/Scanner): **PASS**\n")
            f.write("\n### Final status\n\n**READY_FOR_E4**\n")
        else:
            f.write("- No timeouts / Failures (Dashboard/Orders/Scanner): **FAIL**\n")
            f.write("\n### Final status\n\n**BLOCKED_WITH_FINDINGS**\n")

if __name__ == "__main__":
    asyncio.run(main())
