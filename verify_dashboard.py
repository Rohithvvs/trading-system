import asyncio
import json
from httpx import AsyncClient

async def check():
    # Since we might not have the fastapi server running natively in the test environment, we'll hit it directly via test client
    # Or start it locally if we need to. But we can just use httpx directly to the app instance or local server.
    # Actually wait, the app might not be running on a port. Let's use the fastapi TestClient or httpx with ASGITransport.
    from backend.app.main import app
    from httpx import ASGITransport
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/scanner/latest")
        if response.status_code == 200:
            data = response.json()
            print("Status: 200 OK")
            print("Scan ID:", data.get("scan_id"))
            print("Scan Timestamp:", data.get("scan_timestamp"))
            print("Buy Count:", data.get("buy_count"))
            print("Records Count:", len(data.get("records", [])))
        else:
            print("Failed:", response.status_code, response.text)

if __name__ == "__main__":
    asyncio.run(check())
