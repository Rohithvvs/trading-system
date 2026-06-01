import asyncio
from backend.app.services.paper_trading_service import PaperTradingService
from backend.app.db.session import AsyncSessionLocal
import uuid

async def test_service():
    print("=== STEP 5-8: ORDERS & POSITIONS VIA DIRECT SERVICE ===")
    async with AsyncSessionLocal() as db:
        service = PaperTradingService(db)
        
        print("\n--- Place Market Order ---")
        from backend.app.schemas.paper_trading import PaperOrderCreateRequest
        try:
            req = PaperOrderCreateRequest(
                symbol="INFY-EQ",
                side="BUY",
                order_type="market",
                qty=10,
                idempotency_key=str(uuid.uuid4())
            )
            order = await service.place_order(req)
            print("Market Order Created:", order.id)
            await db.commit()
        except Exception as e:
            print("Error creating market order:", e)

        print("\n--- Place Limit Order ---")
        try:
            req = PaperOrderCreateRequest(
                symbol="TCS-EQ",
                side="BUY",
                order_type="limit",
                qty=5,
                price=3000,
                idempotency_key=str(uuid.uuid4())
            )
            order = await service.place_order(req)
            print("Limit Order Created:", order.id)
            await db.commit()
        except Exception as e:
            print("Error creating limit order:", e)

        print("\n--- Waiting for Market Engine ---")
        await asyncio.sleep(5)

        print("\n--- Positions ---")
        try:
            positions = await service.get_positions()
            for p in positions:
                print("Position:", p.symbol, "Qty:", p.quantity, "LTP:", p.current_price, "Unrealized PnL:", p.unrealized_pnl)
        except Exception as e:
            import traceback
            traceback.print_exc()
            
        print("\n--- History ---")
        try:
            history = await service.get_transactions()
            print("History count:", len(history.items))
            for h in history.items:
                print("Trade:", h.symbol, h.side, "Price:", h.price, "Qty:", h.quantity)
        except Exception as e:
            print("Error fetching history:", e)

if __name__ == "__main__":
    asyncio.run(test_service())
