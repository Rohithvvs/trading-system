import asyncio
import httpx
import time
import uuid

async def test_orders():
    print("=== STEP 5-8: ORDERS & POSITIONS ===")
    base_url = "http://127.0.0.1:8002"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Market Order
        print("\n--- Market Order ---")
        resp = await client.post(f"{base_url}/paper-trading/orders", json={
            "symbol": "INFY-EQ",
            "side": "BUY",
            "order_type": "market",
            "qty": 10,
            "idempotency_key": str(uuid.uuid4())
        })
        print(f"Status: {resp.status_code}")
        try:
            print(f"Response: {resp.json()}")
        except Exception:
            print(f"Text: {resp.text}")
            
        # Limit Order
        print("\n--- Limit Order ---")
        resp = await client.post(f"{base_url}/paper-trading/orders", json={
            "symbol": "TCS-EQ",
            "side": "BUY",
            "order_type": "limit",
            "qty": 5,
            "price": 3000,
            "idempotency_key": str(uuid.uuid4())
        })
        print(f"Status: {resp.status_code}")
        try:
            print(f"Response: {resp.json()}")
        except Exception:
            print(f"Text: {resp.text}")
            
        # Wait 5 seconds for execution
        time.sleep(5)
            
        # Get Positions
        print("\n--- Positions ---")
        resp = await client.get(f"{base_url}/paper-trading/positions")
        print(f"Status: {resp.status_code}")
        positions = []
        try:
            positions = resp.json()
            print(f"Response: {positions}")
        except Exception:
            print(f"Text: {resp.text}")

        # Close Position
        if isinstance(positions, list) and positions:
            print("\n--- Closing Position ---")
            for pos in positions:
                if not isinstance(pos, dict) or "symbol" not in pos:
                    continue
                resp = await client.post(f"{base_url}/paper-trading/positions/close", json={
                    "symbol": pos["symbol"]
                })
                print(f"Close {pos['symbol']} Status: {resp.status_code}")
                try:
                    print(f"Close Response: {resp.json()}")
                except Exception:
                    print(f"Text: {resp.text}")
        
        # Get Trade History
        print("\n--- Trade History ---")
        resp = await client.get(f"{base_url}/paper-trading/orders/history")
        print(f"Status: {resp.status_code}")
        try:
            print(f"Response: {resp.json()}")
        except Exception:
            print(f"Text: {resp.text}")

if __name__ == "__main__":
    asyncio.run(test_orders())
