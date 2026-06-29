import asyncio
import httpx
import time

async def fetch_scanner(client):
    start = time.perf_counter()
    resp = await client.post('http://127.0.0.1:8000/analysis/screener/full', json={
        "symbols": ["RELIANCE-EQ", "INFY-EQ", "TCS-EQ"],
        "strategies": ["volume_breakout"],
        "resolution": "1d"
    })
    end = time.perf_counter()
    return resp.status_code, end - start, resp.json() if resp.status_code == 200 else resp.text

async def main():
    async with httpx.AsyncClient(timeout=120.0) as client:
        tasks = [fetch_scanner(client) for _ in range(20)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
    success_count = 0
    fail_count = 0
    
    for r in results:
        if isinstance(r, Exception):
            fail_count += 1
            print('Exception:', repr(r))
        else:
            status, latency, data = r
            if status == 200:
                success_count += 1
            else:
                fail_count += 1
                print('Failed status:', status, data)
                
    print('Scanner Success:', success_count)
    print('Scanner Fail:', fail_count)

asyncio.run(main())
