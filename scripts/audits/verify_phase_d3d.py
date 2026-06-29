import asyncio
import os
import sys

from backend.app.services.fyers_service import FyersService
from backend.app.db.session import AsyncSessionLocal
from backend.app.services.token_service import get_current_access_token

async def run_step1():
    print("=== STEP 1: TOKEN VALIDATION ===")
    async with AsyncSessionLocal() as session:
        token = await get_current_access_token(session)
        print("Token loaded successfully:")
        print(f"Token length: {len(token) if token else 0}")
        print(f"Token prefix: {token[:10]}..." if token else "No token")

    fyers = FyersService()
    profile = fyers._client().get_profile()
    print("Profile Response:", profile)
    
    # Try LTP
    ltp = fyers.fetch_ltp(["NSE:RELIANCE-EQ"])
    print("LTP Response:", ltp)
    
    # Try History
    import datetime
    today = datetime.date.today()
    start = today - datetime.timedelta(days=5)
    hist = fyers._client().history(data={
        "symbol": "NSE:RELIANCE-EQ",
        "resolution": "1D",
        "date_format": "1",
        "range_from": start.strftime("%Y-%m-%d"),
        "range_to": today.strftime("%Y-%m-%d"),
        "cont_flag": "1"
    })
    print("History Response keys:", hist.keys() if isinstance(hist, dict) else hist)
    if isinstance(hist, dict) and "candles" in hist:
        print("Candle count:", len(hist["candles"]))

if __name__ == "__main__":
    asyncio.run(run_step1())
