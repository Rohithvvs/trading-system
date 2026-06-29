import asyncio
from sqlalchemy import text
from backend.app.db.session import engine

async def check_accounting():
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT balance, reserved_cash FROM paper_accounts WHERE id = 1"))
        row = res.fetchone()
        if not row:
            print("No paper account found.")
            return
        balance, reserved_cash = row
        print(f"Current Cash: {balance}")
        print(f"Reserved Cash: {reserved_cash}")
        
        # open position value
        res = await conn.execute(text("SELECT SUM(quantity * average_price) FROM paper_positions WHERE account_id = 1 AND status = 'OPEN'"))
        open_position_val = res.scalar() or 0.0
        print(f"Open Position Value: {open_position_val}")
        
        # closed trade pnl
        res = await conn.execute(text("SELECT SUM(realized_pnl) FROM paper_trades WHERE account_id = 1"))
        closed_trade_pnl = res.scalar() or 0.0
        print(f"Closed Trade PnL: {closed_trade_pnl}")
        
        # Assuming starting cash was 1000000.0 (from Finding 3)
        starting_cash = 1000000.0
        
        expected_equity = balance + reserved_cash + open_position_val
        actual_equity = starting_cash + closed_trade_pnl
        
        print(f"Expected Equity (Cash + Reserved + Positions): {expected_equity}")
        print(f"Actual Equity (Starting Cash + PnL): {actual_equity}")
        print(f"Difference: {actual_equity - expected_equity}")

asyncio.run(check_accounting())
