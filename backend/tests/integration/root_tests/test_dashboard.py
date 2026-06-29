import asyncio
import httpx
import time
import statistics

async def fetch(client):
    start = time.perf_counter()
    resp = await client.get("http://127.0.0.1:8000/paper-trading/dashboard")
    end = time.perf_counter()
    return resp.status_code, end - start

async def main():
    async with httpx.AsyncClient(timeout=30.0) as client:
        tasks = [fetch(client) for _ in range(100)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
    success_count = 0
    fail_count = 0
    latencies = []
    
    for r in results:
        if isinstance(r, Exception):
            fail_count += 1
            print("Exception:", r)
        else:
            status, latency = r
            if status == 200:
                success_count += 1
                latencies.append(latency)
            else:
                fail_count += 1
                print("Failed status:", status)
                
    latencies.sort()
    
    print("Success:", success_count)
    print("Fail:", fail_count)
    if latencies:
        print("Avg Latency:", sum(latencies)/len(latencies))
        p95 = latencies[int(len(latencies) * 0.95)]
        p99 = latencies[int(len(latencies) * 0.99)]
        print("P95 Latency:", p95)
        print("P99 Latency:", p99)

asyncio.run(main())
