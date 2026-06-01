import asyncio, httpx, time, uuid
async def run_dashboard(client, count):
    tasks = [client.get("/paper-trading/account") for _ in range(count)]
    res = await asyncio.gather(*tasks, return_exceptions=True)
    success = sum(1 for r in res if isinstance(r, httpx.Response) and r.status_code == 200)
    if success < count:
        for r in res: 
            if isinstance(r, httpx.Response) and r.status_code != 200: print("Dashboard:", r.status_code, r.text)
    return success, count

async def run_market(client, count):
    tasks = [client.post("/paper-trading/orders", json={"symbol":"INFY-EQ","side":"BUY","order_type":"MARKET","qty":10}, headers={"Idempotency-Key": str(uuid.uuid4())}) for _ in range(count)]
    res = await asyncio.gather(*tasks, return_exceptions=True)
    success = sum(1 for r in res if isinstance(r, httpx.Response) and r.status_code == 200)
    if success < count:
        for r in res: 
            if isinstance(r, httpx.Response) and r.status_code != 200: print("Market:", r.status_code, r.text)
    return success, count

async def run_limit(client, count):
    tasks = [client.post("/paper-trading/orders", json={"symbol":"TCS-EQ","side":"BUY","order_type":"LIMIT","qty":10,"limit_price":3000}, headers={"Idempotency-Key": str(uuid.uuid4())}) for _ in range(count)]
    res = await asyncio.gather(*tasks, return_exceptions=True)
    success = sum(1 for r in res if isinstance(r, httpx.Response) and r.status_code == 200)
    if success < count:
        for r in res: 
            if isinstance(r, httpx.Response) and r.status_code != 200: print("Limit:", r.status_code, r.text)
    return success, count

async def run_scanner(client, count):
    tasks = [client.post("/analysis/screener/full", json={"mode":"swing"}) for _ in range(count)]
    res = await asyncio.gather(*tasks, return_exceptions=True)
    success = sum(1 for r in res if isinstance(r, httpx.Response) and r.status_code == 200)
    if success < count:
        for r in res: 
            if isinstance(r, httpx.Response) and r.status_code != 200: print("Scanner:", r.status_code, r.text)
    return success, count

async def main():
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=120.0) as client:
        t0 = time.time()
        res = await asyncio.gather(
            run_dashboard(client, 100),
            run_market(client, 50),
            run_limit(client, 50),
            run_scanner(client, 20)
        )
        print(f"Dashboard: {res[0][0]}/{res[0][1]}")
        print(f"Market: {res[1][0]}/{res[1][1]}")
        print(f"Limit: {res[2][0]}/{res[2][1]}")
        print(f"Scanner: {res[3][0]}/{res[3][1]}")
        print(f"Elapsed: {time.time()-t0:.2f}s")

if __name__ == '__main__':
    asyncio.run(main())
