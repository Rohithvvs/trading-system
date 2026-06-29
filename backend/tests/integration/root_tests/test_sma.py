import asyncio
from backend.app.services.technical_analysis_service import TechnicalAnalysisService
from backend.app.schemas import AnalysisMode, OHLCVPoint
from backend.app.db.session import AsyncSessionLocal
from sqlalchemy import text

async def main():
    async with AsyncSessionLocal() as db:
        res = await db.execute(text("SELECT timestamp, open, high, low, close, volume FROM historical_candles WHERE symbol = 'RELIANCE-EQ' ORDER BY timestamp DESC LIMIT 250"))
        rows = res.fetchall()
        rows.reverse()
        candles = [OHLCVPoint(timestamp=r[0], open=r[1], high=r[2], low=r[3], close=r[4], volume=r[5]) for r in rows]
        tech = TechnicalAnalysisService()
        result = tech.analyze_bulk({'RELIANCE-EQ': candles}, AnalysisMode.swing)
        print('latest close:', candles[-1].close, 'at', candles[-1].timestamp)
        print('indicators:', result['RELIANCE-EQ'].indicators)

asyncio.run(main())
