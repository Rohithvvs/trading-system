import asyncio
import httpx
import uuid

async def place_order(client, symbol, type_, price=None):
    payload = {
        "symbol": symbol,
        "side": "BUY",
        "type": type_,
        "qty": 1,
        "idempotency_key": str(uuid.uuid4()),
    }
    if type_ == "LIMIT":
        payload["limit_price"] = price
    resp = await client.post("http://127.0.0.1:8000/paper-trading/orders", json=payload)
    return resp.status_code, resp.text

async def main():
    async with httpx.AsyncClient(timeout=120.0) as client:
        symbols = ["RELIANCE-EQ", "INFY-EQ", "TCS-EQ", "SBIN-EQ"]
        print("--- TEST SUITE 2: MARKET BUY ---")
        tasks = []
        for i in range(50):
            sym = symbols[i % len(symbols)]
            tasks.append(place_order(client, sym, "MARKET"))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success = 0
        failed = 0
        for r in results:
            if isinstance(r, Exception):
                failed += 1
                print("Exception:", r)
            else:
                status, text = r
                if status in (200, 201):
                    success += 1
                else:
                    failed += 1
                    print(status, text)
        print("Market Orders Success:", success, "Failed:", failed)
        
        print("\n--- TEST SUITE 3: LIMIT BUY ---")
        tasks = []
        for i in range(50):
            sym = symbols[i % len(symbols)]
            tasks.append(place_order(client, sym, "LIMIT", price=100.0))
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success = 0
        failed = 0
        for r in results:
            if isinstance(r, Exception):
                failed += 1
                print("Exception:", r)
            else:
                status, text = r
                if status in (200, 201):
                    success += 1
                else:
                    failed += 1
                    print(status, text)
        print("Limit Orders Success:", success, "Failed:", failed)

asyncio.run(main())
