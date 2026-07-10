import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from httpx import AsyncClient
import pytest
from sqlalchemy import select, update, delete

from backend.app.main import app
from backend.app.db.session import AsyncSessionLocal
from backend.app.models.paper_trading import PaperPosition, PaperTradeHistory, PaperTradingAccount, PaperTransaction
from backend.app.services.market_engine_service import MarketEngineService, market_engine

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("validation")

from fastapi.testclient import TestClient

async def run_validations():
    print("=========================================")
    print("PHASE UI-5 PRODUCTION VALIDATION")
    print("=========================================")
    
    with TestClient(app) as client:
        # VALIDATION 1 - ENGINE STATUS API
        print("\n--- VALIDATION 1: ENGINE STATUS API ---")
        start = datetime.utcnow()
        response = client.get("/paper-trading/engine-status")
        end = datetime.utcnow()
        print(f"HTTP Status: {response.status_code}")
        print(f"Response Time: {(end-start).total_seconds()*1000:.2f} ms")
        print(f"Payload: {response.json()}")
        
        # Setup Test Account
        async with AsyncSessionLocal() as db:
            account = db.scalar(select(PaperTradingAccount).limit(1))
            if not account:
                account = PaperTradingAccount(name="Validation Test", cash_balance=100000, starting_balance=100000)
                db.add(account)
                await db.commit()
                await db.refresh(account)
            
            # Clean up old
            db.execute(delete(PaperPosition))
            db.execute(delete(PaperTradeHistory))
            db.execute(delete(PaperTransaction))
            await db.commit()

        # VALIDATION 4 - MANUAL EXIT SOURCE
        print("\n--- VALIDATION 4: MANUAL EXIT SOURCE ---")
        # Open position via API
        open_res = client.post("/paper-trading/orders", json={
            "symbol": "TCS",
            "side": "BUY",
            "qty": 10,
            "order_type": "MARKET"
        })
        print(f"Open Order Response: {open_res.status_code}")
        
        # Let's get the position ID
        async with AsyncSessionLocal() as db:
            pos = db.scalar(select(PaperPosition).where(PaperPosition.symbol == "TCS"))
            if pos:
                # Close manually
                close_res = client.post(f"/paper-trading/positions/{pos.id}/close")
                print(f"Close Position Response: {close_res.status_code}")
                
                trade = db.scalar(select(PaperTradeHistory).where(PaperTradeHistory.symbol == "TCS"))
                if trade:
                    print(f"DB Row exit_source: {trade.exit_source}")
                    print(f"DB Row exit_reason: {trade.exit_reason}")
                
                hist_res = client.get("/paper-trading/history")
                print(f"History API Response exit_source: {hist_res.json()[0]['exit_source']}")

        # VALIDATION 8 & 9 - WATERMARK PROGRESSION & RECONCILIATION EXIT
        print("\n--- VALIDATION 8 & 9: WATERMARK PROGRESSION & RECONCILIATION ---")
        t_created = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(hours=1)
        async with AsyncSessionLocal() as db:
            pos2 = PaperPosition(
                account_id=account.id,
                symbol="RELIANCE",
                qty=Decimal("10"),
                avg_entry_price=Decimal("2500"),
                status="OPEN",
                target=Decimal("2550"),
                created_at=t_created,
                last_evaluated_at=t_created,
                last_reconciled_at=t_created
            )
            db.add(pos2)
            await db.commit()
            await db.refresh(pos2)
            print(f"Watermark BEFORE: {pos2.last_reconciled_at}")

        # Simulate gap
        # We'll mock FYERS fetch_ohlcv to return a candle that hits target
        original_fetch = market_engine.fyers.fetch_ohlcv
        async def mock_fetch(*args, **kwargs):
            class MockCandle:
                def __init__(self, ts, h, l):
                    self.timestamp = ts
                    self.high = h
                    self.low = l
            return [MockCandle(t_created + timedelta(minutes=5), 2560, 2490)]
        
        market_engine.fyers.fetch_ohlcv = mock_fetch
        try:
            await market_engine._reconcile_ohlcv_sequence(account.id)
        except Exception as e:
            print(f"Reconciliation error: {e}")
        finally:
            market_engine.fyers.fetch_ohlcv = original_fetch

        async with AsyncSessionLocal() as db:
            pos2_check = db.scalar(select(PaperPosition).where(PaperPosition.symbol == "RELIANCE"))
            if pos2_check:
                print(f"Watermark AFTER (if still open): {pos2_check.last_reconciled_at}")
            trade2 = db.scalar(select(PaperTradeHistory).where(PaperTradeHistory.symbol == "RELIANCE"))
            if trade2:
                print(f"Trade recovered exit_source: {trade2.exit_source}")
                print(f"Trade recovered exit_reason: {trade2.exit_reason}")

if __name__ == "__main__":
    asyncio.run(run_validations())
