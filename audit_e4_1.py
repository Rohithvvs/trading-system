import asyncio
import aiohttp
import time
import subprocess
import os
import sys
import json
import statistics
import asyncpg

results_data = {
    "dashboard": {},
    "market_orders": {},
    "limit_orders": {},
    "scanner": {}
}

db_stats = {
    "active_connections": 0,
    "idle_connections": 0,
    "idle_in_transaction": 0,
    "samples": 0
}

async def fetch_db_stats():
    try:
        conn = await asyncpg.connect("postgresql://postgres:postgres@localhost:5432/trading_system")
        rows = await conn.fetch("SELECT state, count(*) FROM pg_stat_activity GROUP BY state")
        db_stats['samples'] += 1
        for row in rows:
            state = row['state']
            count = row['count']
            if state == 'active':
                db_stats['active_connections'] += count
            elif state == 'idle':
                db_stats['idle_connections'] += count
            elif state == 'idle in transaction':
                db_stats['idle_in_transaction'] += count
        await conn.close()
    except Exception as e:
        pass

async def test_dashboard(session, i):
    start = time.time()
    try:
        async with session.get("http://localhost:8000/api/v1/paper-trading/dashboard", timeout=10) as resp:
            status = resp.status
            await resp.read()
            return status, time.time() - start, None
    except asyncio.TimeoutError:
        return None, time.time() - start, "timeout"
    except Exception as e:
        return None, time.time() - start, str(e)

async def test_order(session, i, type="MARKET", price=None):
    start = time.time()
    payload = {
        "symbol": "TCS.NS",
        "side": "BUY",
        "type": type,
        "product_type": "INTRADAY",
        "qty": 1,
        "idempotency_key": f"test_e4_1_{type}_{i}_{time.time()}"
    }
    if price:
        payload["order_price"] = price
    try:
        async with session.post("http://localhost:8000/api/v1/paper-trading/order", json=payload, timeout=10) as resp:
            status = resp.status
            await resp.text()
            return status, time.time() - start, None
    except asyncio.TimeoutError:
        return None, time.time() - start, "timeout"
    except Exception as e:
        return None, time.time() - start, str(e)

async def test_scanner(session, i):
    start = time.time()
    try:
        async with session.post("http://localhost:8000/api/v1/scanner/run", json={"mode": "swing"}, timeout=15) as resp:
            status = resp.status
            await resp.text()
            return status, time.time() - start, None
    except asyncio.TimeoutError:
        return None, time.time() - start, "timeout"
    except Exception as e:
        return None, time.time() - start, str(e)

async def db_monitor(stop_event):
    while not stop_event.is_set():
        await fetch_db_stats()
        await asyncio.sleep(0.5)

async def run_tests():
    stop_event = asyncio.Event()
    db_task = asyncio.create_task(db_monitor(stop_event))

    async with aiohttp.ClientSession() as session:
        print("1. Dashboard Test")
        tasks = [test_dashboard(session, i) for i in range(100)]
        results = await asyncio.gather(*tasks)
        process_results(results, "dashboard")

        print("2. Market Orders Test")
        tasks = [test_order(session, i, type="MARKET") for i in range(50)]
        results = await asyncio.gather(*tasks)
        process_results(results, "market_orders")

        print("3. Limit Orders Test")
        tasks = [test_order(session, i, type="LIMIT", price=3000.0) for i in range(50)]
        results = await asyncio.gather(*tasks)
        process_results(results, "limit_orders")

        print("4. Scanner Test")
        tasks = [test_scanner(session, i) for i in range(10)]
        results = await asyncio.gather(*tasks)
        process_results(results, "scanner")

    stop_event.set()
    await db_task

def process_results(results, key):
    success = sum(1 for r in results if r[0] in (200, 201))
    status_500 = sum(1 for r in results if r[0] == 500)
    timeouts = sum(1 for r in results if r[2] == "timeout")
    other_exceptions = [r[2] for r in results if r[0] is None and r[2] != "timeout"]
    failure = sum(1 for r in results if r[0] not in (200, 201) and r[0] is not None)
    latencies = [r[1] for r in results if r[1] is not None]
    
    avg_latency = statistics.mean(latencies) if latencies else 0
    p95_latency = statistics.quantiles(latencies, n=100)[94] if len(latencies) > 1 else avg_latency

    results_data[key] = {
        "success": success,
        "failure": failure,
        "timeouts": timeouts,
        "status_500": status_500,
        "other_exceptions": len(other_exceptions),
        "exception_samples": list(set(other_exceptions))[:3],
        "avg_latency": avg_latency,
        "p95_latency": p95_latency
    }

async def main():
    env = os.environ.copy()
    env["DATABASE_URL"] = "postgresql+asyncpg://postgres:postgres@localhost:5432/trading_system"
    env["PYTHONPATH"] = "."
    print("Starting backend...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env
    )
    
    await asyncio.sleep(10)
    print("Running Load Test...")
    await run_tests()
    
    print("Stopping backend...")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except:
        proc.kill()
    
    logs = proc.stdout.read()
    
    errors_to_track = [
        "RuntimeError",
        "ReadTimeout",
        "QueuePool",
        "TooManyConnectionsError",
        "PendingRollbackError",
        "coroutine was never awaited"
    ]
    
    error_counts = {}
    for error in errors_to_track:
        error_counts[error] = logs.lower().count(error.lower())
    
    if db_stats['samples'] > 0:
        db_stats['active_connections'] //= db_stats['samples']
        db_stats['idle_connections'] //= db_stats['samples']
        db_stats['idle_in_transaction'] //= db_stats['samples']
    
    with open("audit_e4_1_output.json", "w") as f:
        json.dump({
            "results": results_data,
            "db_stats": db_stats,
            "errors": error_counts
        }, f, indent=2)
    print("Output saved to audit_e4_1_output.json")

if __name__ == "__main__":
    asyncio.run(main())
