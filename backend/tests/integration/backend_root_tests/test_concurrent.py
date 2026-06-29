import asyncio
import httpx

async def fetch(client):
    response = await client.get('http://127.0.0.1:8000/paper-trading/account')
    return response.status_code, response.text

async def main():
    async with httpx.AsyncClient(timeout=10) as client:
        tasks = [fetch(client) for _ in range(10)]
        results = await asyncio.gather(*tasks)
        for code, text in results:
            print(f'Code: {code}')
            if code == 500:
                print(text)

asyncio.run(main())
