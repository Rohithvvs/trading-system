import asyncio
import os

from backend.app.services.market_data_service import MarketDataService
from backend.app.schemas import AnalysisMode

async def run_step2():
    print("=== STEP 2: LIVE DATA VALIDATION ===")
    md_service = MarketDataService()
    from backend.app.services.fyers_service import FyersService
    fyers = FyersService()
    
    symbols = ["INFY-EQ", "SBIN-EQ", "RELIANCE-EQ", "TCS-EQ"]
    for sym in symbols:
        print(f"\n--- Symbol: {sym} ---")
        ltp = await fyers.fetch_ltp(f"NSE:{sym}")
        print(f"LTP: {ltp}")
        
        # We need historical candles for swing
        hist_df = await md_service.get_historical_candles(sym, "1d", 240, AnalysisMode.swing, False)
        print(f"Candle count: {len(hist_df) if hist_df is not None else 0}")
        if hist_df is not None and not hist_df.empty:
            print(f"Latest candle timestamp: {hist_df.index[-1]}")
        
        source = fyers.get_ohlcv_source(sym, AnalysisMode.swing, "1d")
        print(f"Data source used: {source}")

if __name__ == "__main__":
    asyncio.run(run_step2())
