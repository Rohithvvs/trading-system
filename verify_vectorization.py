import asyncio
import pandas as pd
import numpy as np
from ta.trend import SMAIndicator
from ta.momentum import RSIIndicator
from backend.app.services.technical_analysis_service import TechnicalAnalysisService
from backend.app.schemas import AnalysisMode, OHLCVPoint
from backend.app.db.session import AsyncSessionLocal
from sqlalchemy import text
from backend.app.config import settings

async def main():
    tech = TechnicalAnalysisService()
    test_symbols = ['RELIANCE-EQ', 'INFY-EQ', 'TCS-EQ', 'SBIN-EQ', 'HDFCBANK-EQ']
    
    universe = settings.nifty500_symbols
    universe_candles = {}
    
    print("Fetching ALL candles from DB to recreate the bulk environment...")
    async with AsyncSessionLocal() as db:
        for chunk in [universe[i:i+100] for i in range(0, len(universe), 100)]:
            symbols_list = "', '".join(chunk)
            query = f"SELECT symbol, timestamp, open, high, low, close, volume FROM historical_candles WHERE symbol IN ('{symbols_list}') AND resolution = '1D' ORDER BY symbol, timestamp"
            res = await db.execute(text(query))
            for row in res:
                sym = row[0]
                if sym not in universe_candles:
                    universe_candles[sym] = []
                universe_candles[sym].append(OHLCVPoint(
                    timestamp=row[1], open=row[2], high=row[3], low=row[4], close=row[5], volume=row[6]
                ))
    
    filtered_candles = {sym: candles for sym, candles in universe_candles.items() if len(candles) >= 240}
    
    # 1. Compute Individual Indicators
    individual_results = {}
    for sym in test_symbols:
        if sym not in filtered_candles:
            print(f"Skipping {sym}, not enough data")
            continue
            
        candles = filtered_candles[sym]
        df = pd.DataFrame([{'close': c.close, 'high': c.high, 'low': c.low} for c in candles])
        
        sma50 = SMAIndicator(close=df['close'], window=50).sma_indicator().iloc[-1]
        sma200 = SMAIndicator(close=df['close'], window=200).sma_indicator().iloc[-1]
        
        # RSI 14 (we should use the same logic as TechnicalAnalysisService)
        # The service uses ewm(alpha=1/14)
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0.0).ewm(alpha=1/14, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0.0)).ewm(alpha=1/14, adjust=False).mean()
        rs = gain / loss
        rsi14 = 100.0 - (100.0 / (1.0 + rs))
        rsi14_val = rsi14.iloc[-1]
        
        individual_results[sym] = {
            'close': df['close'].iloc[-1],
            'sma50': sma50,
            'sma200': sma200,
            'rsi14': rsi14_val
        }

    # 2. Compute Bulk Indicators
    print("Running analyze_bulk on all symbols...")
    bulk_results = tech.analyze_bulk(filtered_candles, AnalysisMode.swing)
    
    # Let's intercept the unstack operation to see if NaNs are introduced
    # We will build the unstacked frame manually to count NaNs
    records = []
    for sym, candles in filtered_candles.items():
        for c in candles:
            records.append({"timestamp": c.timestamp, "symbol": sym, "close": c.close})
            
    frame = pd.DataFrame(records)
    frame.set_index(["timestamp", "symbol"], inplace=True)
    frame.sort_index(inplace=True)
    close_unstack = frame["close"].unstack(level="symbol")
    
    print("\n--- RESULTS ---")
    for sym in test_symbols:
        if sym not in individual_results:
            continue
            
        ind = individual_results[sym]
        bulk_ind = bulk_results[sym].indicators
        
        print(f"Symbol: {sym}")
        print(f"Latest Close: {ind['close']}")
        print(f"Individual SMA50: {ind['sma50']} | Bulk SMA50: {bulk_ind.get('sma_50', np.nan)}")
        print(f"Individual SMA200: {ind['sma200']} | Bulk SMA200: {bulk_ind.get('sma_200', np.nan)}")
        print(f"Individual RSI: {ind['rsi14']} | Bulk RSI: {bulk_ind.get('rsi_14', np.nan)}")
        print("---")
        
    print(f"Total NaNs in unstacked close series for RELIANCE-EQ: {close_unstack['RELIANCE-EQ'].isna().sum()}")
    print(f"Total rows in unstacked dataframe: {len(close_unstack)}")

if __name__ == '__main__':
    asyncio.run(main())
