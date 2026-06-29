import asyncio
from backend.app.config import settings
from backend.app.db.session import AsyncSessionLocal
from sqlalchemy import text
from backend.app.services.technical_analysis_service import TechnicalAnalysisService
from backend.app.schemas import AnalysisMode, OHLCVPoint
from datetime import datetime

async def main():
    tech_service = TechnicalAnalysisService()
    universe = settings.nifty500_symbols
    
    universe_candles = {}
    valid_symbols = 0
    
    print("Fetching candles from DB...")
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
    
    filtered_candles = {}
    for sym, candles in universe_candles.items():
        if len(candles) >= 240:
            filtered_candles[sym] = candles
            valid_symbols += 1

    print(f"Valid symbols with 240+ candles: {valid_symbols}")
    
    print("Running analyze_bulk...")
    tech_results = tech_service.analyze_bulk(filtered_candles, AnalysisMode.swing)
    
    stats = {
        'Close > SMA50': {'pass': 0, 'fail': 0},
        'SMA50 > SMA200': {'pass': 0, 'fail': 0},
        'Close > EMA20': {'pass': 0, 'fail': 0},
        'Supertrend Positive': {'pass': 0, 'fail': 0},
        'MACD > Signal': {'pass': 0, 'fail': 0},
        'RSI >= 50': {'pass': 0, 'fail': 0},
        'Volume > 50k & Price 100-500k': {'pass': 0, 'fail': 0},
        'Technical Score >= 48': {'pass': 0, 'fail': 0},
        'Avg 20d Volume > 100k': {'pass': 0, 'fail': 0},
        'Overall Broad Trend Pass': {'pass': 0, 'fail': 0}
    }
    
    for sym, res in tech_results.items():
        c = res.indicators
        latest_close = filtered_candles[sym][-1].close
        avg_vol = sum(cd.volume for cd in filtered_candles[sym][-20:]) / 20.0
        
        c_sma50 = latest_close > c.get("sma_50", 0.0)
        sma50_200 = c.get("sma_50", 0.0) > c.get("sma_200", 0.0)
        c_ema20 = c.get("close_above_ema20", False)
        st_pos = c.get("supertrend_positive", False)
        macd_pos = c.get("macd_positive", False)
        rsi_pass = c.get("rsi_supportive", False)
        liq_pass = c.get("basic_liquidity_filter_pass", False)
        tech_score_pass = res.score >= 48
        avg_vol_pass = avg_vol > 100000
        
        hard_filters_pass = c.get("hard_filters_pass", False)
        
        overall = c_sma50 and sma50_200 and hard_filters_pass and tech_score_pass and avg_vol_pass
        
        stats['Close > SMA50']['pass' if c_sma50 else 'fail'] += 1
        stats['SMA50 > SMA200']['pass' if sma50_200 else 'fail'] += 1
        stats['Close > EMA20']['pass' if c_ema20 else 'fail'] += 1
        stats['Supertrend Positive']['pass' if st_pos else 'fail'] += 1
        stats['MACD > Signal']['pass' if macd_pos else 'fail'] += 1
        stats['RSI >= 50']['pass' if rsi_pass else 'fail'] += 1
        stats['Volume > 50k & Price 100-500k']['pass' if liq_pass else 'fail'] += 1
        stats['Technical Score >= 48']['pass' if tech_score_pass else 'fail'] += 1
        stats['Avg 20d Volume > 100k']['pass' if avg_vol_pass else 'fail'] += 1
        stats['Overall Broad Trend Pass']['pass' if overall else 'fail'] += 1
        
    for k, v in stats.items():
        print(f"{k} -> Pass: {v['pass']}, Fail: {v['fail']}")

if __name__ == '__main__':
    asyncio.run(main())
