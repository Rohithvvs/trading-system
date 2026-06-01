import asyncio, httpx, time
async def run_market(client, count):
    tasks = [client.post("/paper-trading/orders", json={"symbol":"INFY-EQ","side":"BUY","order_type":"MARKET","qty":10}) for _ in range(count)]
    res = await asyncio.gather(*tasks, return_exceptions=True)
    for r in res:
        if isinstance(r, httpx.Response) and r.status_code != 200:
            print(r.status_code, r.text)
        elif isinstance(r, Exception):
            print(r)

async def main():
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=120.0) as client:
        await run_market(client, 1)

if __name__ == '__main__':
    asyncio.run(main())
