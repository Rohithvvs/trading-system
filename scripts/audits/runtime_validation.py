import asyncio
import aiohttp
import time
import subprocess
import os
import signal
import sys

async def test_dashboard(session, i):
    start = time.time()
    try:
        async with session.get("http://localhost:8000/api/v1/paper-trading/dashboard", timeout=5) as resp:
            status = resp.status
            await resp.read()
            latency = time.time() - start
            return status, latency, None
    except asyncio.TimeoutError:
        return None, time.time() - start, "timeout"
    except Exception as e:
        return None, time.time() - start, str(e)

async def run_dashboard_test():
    print("--- Running Dashboard Test ---")
    async with aiohttp.ClientSession() as session:
        tasks = [test_dashboard(session, i) for i in range(100)]
        results = await asyncio.gather(*tasks)
        
        status_500 = sum(1 for r in results if r[0] == 500)
        timeouts = sum(1 for r in results if r[2] == "timeout")
        latencies = [r[1] for r in results if r[1] is not None]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        
        print(f"500 Count: {status_500}")
        print(f"Timeout Count: {timeouts}")
        print(f"Average Latency: {avg_latency:.4f}s")
        return {"500": status_500, "timeout": timeouts, "latency": avg_latency}

async def test_order(session, i):
    payload = {
        "symbol": "TCS.NS",
        "side": "BUY",
        "type": "MARKET",
        "product_type": "INTRADAY",
        "qty": 1,
        "idempotency_key": f"test_order_new_{i}"
    }
    try:
        async with session.post("http://localhost:8000/api/v1/paper-trading/order", json=payload, timeout=10) as resp:
            return resp.status, await resp.text()
    except Exception as e:
        return None, str(e)

async def run_order_test():
    print("--- Running Market Orders Test ---")
    async with aiohttp.ClientSession() as session:
        tasks = [test_order(session, i) for i in range(50)]
        results = await asyncio.gather(*tasks)
        
        success = sum(1 for r in results if r[0] in (200, 201))
        failure = sum(1 for r in results if r[0] not in (200, 201) and r[0] is not None)
        exceptions = sum(1 for r in results if r[0] is None)
        
        print(f"Success Count: {success}")
        print(f"Failure Count: {failure}")
        print(f"Exceptions/Timeouts: {exceptions}")
        return {"success": success, "failure": failure + exceptions}

async def run_scanner_test():
    print("--- Running Scanner Test ---")
    async with aiohttp.ClientSession() as session:
        completions = 0
        timeouts = 0
        for i in range(3):
            try:
                # Trigger a scan
                async with session.post("http://localhost:8000/api/v1/scanner/run", json={"mode": "swing"}, timeout=15) as resp:
                    if resp.status == 200:
                        completions += 1
            except asyncio.TimeoutError:
                timeouts += 1
            except Exception as e:
                timeouts += 1
        
        print(f"Scanner Completions: {completions}")
        print(f"Scanner Timeouts: {timeouts}")

async def main():
    print("Starting backend...")
    # Start backend in a subprocess
    env = os.environ.copy()
    env["DATABASE_URL"] = "postgresql+asyncpg://postgres:postgres@localhost:5432/trading_system"
    # To capture logs correctly
    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env
    )
    
    # Give it time to start
    await asyncio.sleep(10)
    
    # Run tests
    await run_dashboard_test()
    await run_order_test()
    await run_scanner_test()
    
    # Stop backend
    print("Stopping backend...")
    backend_proc.terminate()
    try:
        backend_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        backend_proc.kill()
    
    # Parse logs
    print("--- Parsing Backend Logs ---")
    logs = backend_proc.stdout.read()
    
    errors_to_track = [
        "RuntimeError",
        "coroutine was never awaited",
        "event loop is closed",
        "asyncio.run() cannot be called",
        "Deadlock",
        "TimeoutError",
        "deadlock detected"
    ]
    
    for error in errors_to_track:
        count = logs.lower().count(error.lower())
        print(f"{error}: {count}")

if __name__ == "__main__":
    asyncio.run(main())
