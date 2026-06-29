import asyncio
from app.services.fyers_service import FyersService
from app.schemas import AnalysisMode
from app.utils import configure_logging

configure_logging()

async def main():
    f = FyersService(20.0)
    res = await f.fetch_ohlcv('ABB', AnalysisMode.swing, '1d', 90, True)
    print("SUCCESS, fetched:", len(res) if res else "None")

asyncio.run(main())
