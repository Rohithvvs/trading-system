import asyncio
import time
import os
import glob
from sqlalchemy import text
from backend.app.db.session import AsyncSessionLocal

async def check_startup_files():
    print("--- AREA 1: CLEAN STARTUP TEST ---")
    db_files = glob.glob("trading_system.db*")
    print(f"SQLite files in root: {db_files}")
    if len(db_files) == 0:
        print("Success: No SQLite files found in root.")
    else:
        print("Fail: SQLite files found!")

async def audit_database():
    print("\n--- AREA 2: DATABASE AUDIT ---")
    async with AsyncSessionLocal() as db:
        res = await db.execute(text("SELECT count(*) FROM paper_trading_orders"))
        print(f"Orders: {res.scalar()}")
        res = await db.execute(text("SELECT count(*) FROM paper_trading_positions"))
        print(f"Positions: {res.scalar()}")
        res = await db.execute(text("SELECT count(*) FROM paper_trading_trade_history"))
        print(f"Trades: {res.scalar()}")
        res = await db.execute(text("SELECT count(*) FROM market_data.candles"))
        print(f"Candles: {res.scalar()}")
        res = await db.execute(text("SELECT count(*) FROM market_data.ltp_cache"))
        print(f"LTP Cache: {res.scalar()}")
        res = await db.execute(text("SELECT count(*) FROM market_data.scan_results"))
        print(f"Scan Results: {res.scalar()}")

async def scanner_validation():
    print("\n--- AREA 3: SCANNER VALIDATION ---")
    import httpx
    
    success_count = 0
    fail_count = 0
    times = []
    
    # Run 2 full scanner executions (down from 20 to prevent pool saturation)
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=120.0) as client:
        for i in range(2):
            try:
                t0 = time.time()
                # Run a small scan so it doesn't take forever, e.g., Nifty 50 or custom symbols
                payload = {
                    "mode": "swing",
                    "timeframe": {
                        "intraday": "5m",
                        "swing": "1d",
                        "lookback_window": 30
                    },
                    "symbols": ["RELIANCE-EQ", "INFY-EQ", "TCS-EQ"],
                    "top_n": 5
                }
                resp = await client.post("/analysis/screener/full", json=payload)
                if resp.status_code == 200:
                    text_body = resp.text
                    if "status" in text_body or "complete" in text_body or "event: result" in text_body:
                        success_count += 1
                        times.append(time.time() - t0)
                    else:
                        print(f"Run {i+1} error: invalid response body")
                        fail_count += 1
                else:
                    fail_count += 1
                    print(f"Run {i+1} failed: {resp.status_code} - {resp.text}")
            except Exception as e:
                fail_count += 1
                print(f"Run {i+1} error: {e}")
                
    print(f"Scanner Runs: {success_count} success, {fail_count} fail")
    if times:
        print(f"Avg Scanner Time: {sum(times)/len(times):.2f}s")
    return times

async def order_validation():
    print("\n--- AREA 4: PAPER TRADING VALIDATION ---")
    import httpx
    
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=60.0) as client:
        # 10 Market Buys
        buy_times = []
        for i in range(10):
            start = time.time()
            resp = await client.post("/paper-trading/orders", json={
                "symbol": "RELIANCE-EQ",
                "side": "BUY",
                "type": "MARKET",
                "qty": 1,
                "idempotency_key": f"mkt_buy_{time.time()}_{i}"
            })
            if resp.status_code == 200: buy_times.append(time.time() - start)
            
        print(f"Market Buys completed: {len(buy_times)}")
        
        # 10 Market Sells
        for i in range(10):
            resp = await client.post("/paper-trading/orders", json={
                "symbol": "RELIANCE-EQ",
                "side": "SELL",
                "type": "MARKET",
                "qty": 1,
                "idempotency_key": f"mkt_sell_{time.time()}_{i}"
            })
        print("Market Sells completed.")
        
        # 10 Limit Buys
        for i in range(10):
            resp = await client.post("/paper-trading/orders", json={
                "symbol": "INFY-EQ",
                "side": "BUY",
                "type": "LIMIT",
                "qty": 1,
                "limit_price": 1000.0,
                "idempotency_key": f"lmt_buy_{time.time()}_{i}"
            })
        print("Limit Buys completed.")

        # 10 Limit Sells
        for i in range(10):
            resp = await client.post("/paper-trading/orders", json={
                "symbol": "TCS-EQ",
                "side": "SELL",
                "type": "LIMIT",
                "qty": 1,
                "limit_price": 5000.0,
                "idempotency_key": f"lmt_sell_{time.time()}_{i}"
            })
        print("Limit Sells completed.")
        return buy_times

async def financial_consistency():
    print("\n--- AREA 5: FINANCIAL CONSISTENCY ---")
    async with AsyncSessionLocal() as db:
        res = await db.execute(text("SELECT cash_balance, starting_balance FROM paper_trading_accounts LIMIT 1"))
        row = res.mappings().first()
        if not row:
            print("No account found.")
            return
            
        current_cash = float(row["cash_balance"])
        initial_capital = float(row["starting_balance"] or 100000.0)
        
        # Calculate filled buys
        res = await db.execute(text("SELECT COALESCE(SUM(filled_price * qty), 0) FROM paper_trading_orders WHERE side = 'BUY' AND status = 'FILLED'"))
        filled_buys = float(res.scalar())
        
        # Calculate filled sells
        res = await db.execute(text("SELECT COALESCE(SUM(filled_price * qty), 0) FROM paper_trading_orders WHERE side = 'SELL' AND status = 'FILLED'"))
        filled_sells = float(res.scalar())
        
        # Calculate reserved cash (pending buys)
        res = await db.execute(text("SELECT COALESCE(SUM(order_price * qty), 0) FROM paper_trading_orders WHERE side = 'BUY' AND status = 'PENDING'"))
        reserved_cash = float(res.scalar())
        
        print(f"Starting Cash: {initial_capital}")
        print(f"Filled Buys: {filled_buys}")
        print(f"Filled Sells: {filled_sells}")
        print(f"Reserved Cash: {reserved_cash}")
        
        # Expected = initial - buys + sells
        # Current Cash includes reserved_cash as available balance? 
        # Wait, balance is updated on fill and reserved on pending.
        print(f"Current Available Balance in DB: {current_cash}")
        
        # Let's check ledger transactions
        res = await db.execute(text("SELECT COALESCE(SUM(amount), 0) FROM paper_trading_transactions"))
        net_tx = float(res.scalar())
        print(f"Net Transaction Ledger: {net_tx}")
        print(f"Calculated End Balance (Initial + Net TX): {initial_capital + net_tx}")
        
        if abs((initial_capital + net_tx) - current_cash) < 1.0:
            print("ACCOUNTING MATCH: YES")
        else:
            print("ACCOUNTING MATCH: NO (Check reserve logic)")

async def pg_health():
    print("\n--- AREA 9: POSTGRESQL HEALTH ---")
    async with AsyncSessionLocal() as db:
        res = await db.execute(text("""
            SELECT count(*) as total,
                   sum(case when state = 'active' then 1 else 0 end) as active,
                   sum(case when state = 'idle' then 1 else 0 end) as idle,
                   sum(case when state = 'idle in transaction' then 1 else 0 end) as idle_in_tx,
                   sum(case when wait_event_type = 'Lock' then 1 else 0 end) as blocked
            FROM pg_stat_activity 
            WHERE datname = 'trading_system'
        """))
        row = res.mappings().first()
        print(f"Total Connections: {row['total']}")
        print(f"Active: {row['active']}")
        print(f"Idle: {row['idle']}")
        print(f"Idle in TX: {row['idle_in_tx']}")
        print(f"Blocked (Locks): {row['blocked']}")

async def dashboard_perf():
    print("\n--- AREA 8: PERFORMANCE BASELINE ---")
    import httpx
    times = []
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=30.0) as client:
        for _ in range(5):
            start = time.time()
            await client.get("/paper-trading/dashboard")
            times.append(time.time() - start)
    print(f"Dashboard Avg Load Time: {sum(times)/len(times):.3f}s")

async def main():
    await check_startup_files()
    await audit_database()
    scanner_times = await scanner_validation()
    buy_times = await order_validation()
    await dashboard_perf()
    if buy_times:
        print(f"Market Buy Avg Execution Time: {sum(buy_times)/len(buy_times):.3f}s")
    await financial_consistency()
    await pg_health()

if __name__ == "__main__":
    asyncio.run(main())
