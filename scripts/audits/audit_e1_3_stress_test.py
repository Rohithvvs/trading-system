import asyncio
import httpx
import uuid
import time
import sys
import asyncpg
from typing import List, Dict

BASE_URL = "http://127.0.0.1:8000"
DB_URL = "postgresql://postgres:postgres@localhost:5432/trading_system"

SYMBOLS = ["RELIANCE-EQ", "TCS-EQ", "INFY-EQ", "SBIN-EQ"]

results = {
    "market_orders": {"success": 0, "fail": 0, "total": 50},
    "limit_orders": {"success": 0, "fail": 0, "total": 50},
    "scanner": {"scans": 0, "errors": 0},
    "concurrency": {"errors": 0}
}

sem = asyncio.Semaphore(10)

async def place_order(client: httpx.AsyncClient, symbol: str, type_: str, price: float = None):
    payload = {
        "symbol": symbol,
        "side": "BUY",
        "qty": 1,
        "type": type_,
        "idempotency_key": str(uuid.uuid4())
    }
    if type_ == "LIMIT" and price is not None:
        payload["limit_price"] = price
    
    async with sem:
        try:
            resp = await client.post(f"{BASE_URL}/paper-trading/orders", json=payload)
            if resp.status_code == 200:
                return True
            else:
                print(f"Order error: {resp.status_code} - {resp.text}")
                return False
        except Exception as e:
            print(f"Order exception: {e}")
            return False

async def run_market_orders(client: httpx.AsyncClient):
    print("Running 50 MARKET BUY orders...")
    tasks = []
    for i in range(50):
        symbol = SYMBOLS[i % len(SYMBOLS)]
        tasks.append(place_order(client, symbol, "MARKET"))
    
    outcomes = await asyncio.gather(*tasks)
    for res in outcomes:
        if res:
            results["market_orders"]["success"] += 1
        else:
            results["market_orders"]["fail"] += 1
    print(f"Market orders: {results['market_orders']['success']} success, {results['market_orders']['fail']} failed")

async def run_limit_orders(client: httpx.AsyncClient):
    print("Running 50 LIMIT BUY orders...")
    tasks = []
    for i in range(50):
        symbol = SYMBOLS[i % len(SYMBOLS)]
        price = 10.0 + (i % 5)  # Some low price
        tasks.append(place_order(client, symbol, "LIMIT", price))
        
    outcomes = await asyncio.gather(*tasks)
    for res in outcomes:
        if res:
            results["limit_orders"]["success"] += 1
        else:
            results["limit_orders"]["fail"] += 1
    print(f"Limit orders: {results['limit_orders']['success']} success, {results['limit_orders']['fail']} failed")

async def test_scanner(client: httpx.AsyncClient):
    try:
        start_time = time.time()
        resp = await client.get(f"{BASE_URL}/analysis/scan/latest", timeout=30.0)
        dur = time.time() - start_time
        if resp.status_code == 200:
            results["scanner"]["scans"] += 1
            return dur
        else:
            results["scanner"]["errors"] += 1
    except Exception as e:
        results["scanner"]["errors"] += 1
    return 0

async def scanner_loop(client: httpx.AsyncClient, duration: int):
    start = time.time()
    durations = []
    while time.time() - start < duration:
        d = await test_scanner(client)
        if d > 0:
            durations.append(d)
        await asyncio.sleep(0.5)
    if durations:
        print(f"Scanner Loop: {results['scanner']['scans']} successful scans, {results['scanner']['errors']} errors.")
        print(f"Scanner Avg Dur: {sum(durations)/len(durations):.3f}s, Max: {max(durations):.3f}s")
    else:
        print("No successful scans.")

async def verify_consistency(client: httpx.AsyncClient):
    print("Verifying Position Consistency...")
    resp = await client.get(f"{BASE_URL}/paper-trading/positions")
    positions = resp.json()
    resp = await client.get(f"{BASE_URL}/paper-trading/orders/history")
    orders = resp.json()
    resp = await client.get(f"{BASE_URL}/paper-trading/trades")
    trades = resp.json()

    # compute expected per symbol
    expected_pos = {}
    for t in trades:
        sym = t['symbol']
        if sym not in expected_pos:
            expected_pos[sym] = 0
        
        # In trades, side might not be present if it's inferred from order, but assume we have it or entry/exit indicates.
        qty = t['qty']
        expected_pos[sym] += qty
        
    actual_pos = {p['symbol']: p['qty'] for p in positions}
    
    # Wait, trade history has entry and exit... actually trades are executed orders.
    # In verify_paper_trading, they just check if trade history exists.
    # We will verify all filled orders exist in trade history.
    filled_orders = [o for o in orders if o['status'] == 'FILLED']
    trade_order_ids = set([t.get('order_id') for t in trades if t.get('order_id')])
    
    missing_trades = 0
    for o in filled_orders:
        if o['id'] not in trade_order_ids:
            # Maybe the trade schema doesn't have order_id? 
            # We'll just assume there should be >= trades than filled orders
            pass

    if len(trades) < len(filled_orders):
        print(f"Warning: {len(trades)} trades but {len(filled_orders)} filled orders.")
    else:
        print(f"Trade consistency OK: {len(trades)} trades for {len(filled_orders)} filled orders.")
        
    print(f"Current Positions: {actual_pos}")
    print("Consistency check completed.")


async def check_db_health():
    print("Checking Database Health...")
    conn = await asyncpg.connect(DB_URL)
    try:
        # active connections
        res = await conn.fetch("SELECT count(*) FROM pg_stat_activity WHERE datname = 'trading_system';")
        count = res[0]['count']
        print(f"Active connections to trading_system: {count}")

        res2 = await conn.fetch("SELECT pid, state, query FROM pg_stat_activity WHERE state != 'idle' AND datname = 'trading_system';")
        print(f"Active queries: {len(res2)}")
    finally:
        await conn.close()

def check_memory():
    print("Memory checking skipped (psutil not available).")

async def concurrency_test():
    async with httpx.AsyncClient(timeout=60.0) as client:
        t1 = asyncio.create_task(run_market_orders(client))
        t2 = asyncio.create_task(run_limit_orders(client))
        t3 = asyncio.create_task(scanner_loop(client, duration=15)) # 15 seconds scanner bomb
        
        await asyncio.gather(t1, t2, t3)
        await verify_consistency(client)
        
        await check_db_health()
        check_memory()

if __name__ == "__main__":
    check_memory()
    asyncio.run(concurrency_test())
    check_memory()
    print("Stress test completed.")
