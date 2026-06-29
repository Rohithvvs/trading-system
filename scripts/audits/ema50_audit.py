import asyncio
from backend.app.config import settings
from backend.app.db.session import AsyncSessionLocal
from sqlalchemy import text
from backend.app.services.technical_analysis_service import TechnicalAnalysisService
from backend.app.services.screener_service import ScreenerService
from backend.app.schemas import AnalysisMode, OHLCVPoint
from datetime import datetime

async def main():
    tech_service = TechnicalAnalysisService()
    screener_service = ScreenerService()
    universe = settings.nifty500_symbols
    
    universe_candles = {}
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
    
    filtered_candles = {sym: candles for sym, candles in universe_candles.items() if len(candles) >= 200}
    
    print("Running analyze_bulk...")
    tech_results = tech_service.analyze_bulk(filtered_candles, AnalysisMode.swing)
    
    results = []
    results_before = []
    
    for sym, candles in filtered_candles.items():
        tech = tech_results.get(sym)
        if not tech: continue
        
        # Original logic (simulate before +5)
        conditions = screener_service._build_conditions(tech.indicators, candles[-1], candles[-2], True, tech)
        
        # New score
        score_new = screener_service._weighted_score(candles, tech, conditions)
        
        # Remove ema20_above_ema50
        cond_old = conditions.copy()
        if "ema20_above_ema50" in cond_old:
            del cond_old["ema20_above_ema50"]
        
        # Old Score simulation:
        score_old = 0.0
        score_old += tech.score * 0.5
        score_old += 12 if cond_old["broad_trend_eligibility"] else 0
        score_old += 6 if cond_old["hard_filters_pass"] else 0
        score_old += 4 if cond_old["close_above_ema20"] else 0
        score_old += 4 if cond_old["supertrend_positive"] else 0
        score_old += 4 if cond_old["macd_positive"] else 0
        score_old += 3 if cond_old["rsi_supportive"] else 0
        score_old += 4 if cond_old["sma_uptrend_20d"] else 0
        score_old += 3 if cond_old["hh_hl_2d"] else 0
        score_old += 3 if cond_old["hh_hl_3d"] else 0
        score_old += 3 if cond_old["hh_hl_4d"] else 0
        score_old += 3 if cond_old["latest_confirms_5d_structure"] else 0
        score_old += 3 if cond_old["structure_supportive"] else 0
        score_old += 2 if cond_old["hammer_or_gravestone"] else 0
        score_old += 3 if cond_old["volume_above_50000"] else 0
        score_old += 3 if cond_old["volume_above_previous_day"] else 0
        
        results.append((sym, score_new))
        results_before.append((sym, score_old))
        
    results.sort(key=lambda x: -x[1])
    results_before.sort(key=lambda x: -x[1])
    
    print("--- BEFORE EMA50 ---")
    for i, (sym, score) in enumerate(results_before[:20]):
        print(f"{i+1}. {sym}: {score}")
        
    print("\n--- AFTER EMA50 ---")
    for i, (sym, score) in enumerate(results[:20]):
        print(f"{i+1}. {sym}: {score}")

if __name__ == "__main__":
    asyncio.run(main())
