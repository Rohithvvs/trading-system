import asyncio
import pandas as pd
from datetime import datetime, timedelta
from backend.app.schemas import AnalysisMode, OHLCVPoint
from backend.app.services.technical_analysis_service import TechnicalAnalysisService
from backend.app.services.screener_service import ScreenerService

def create_candles(count: int, close_prices: list[float]) -> list[OHLCVPoint]:
    now = datetime.utcnow()
    candles = []
    for i in range(count):
        price = close_prices[i] if i < len(close_prices) else close_prices[-1]
        candles.append(OHLCVPoint(
            timestamp=now - timedelta(days=count - i),
            open=price, high=price+1, low=price-1, close=price, volume=100000
        ))
    return candles

def get_close_prices(case_type: str, count: int):
    # Base: stable prices around 100
    prices = [100.0] * count
    if case_type == "case1":
        # EMA20 > EMA50. EMA20 reacts faster, so an uptrend works.
        # Let's just make the last 30 candles rising.
        for i in range(count - 30, count):
            prices[i] = 100.0 + (i - (count - 30)) * 2
    elif case_type == "case2":
        # EMA20 < EMA50. Downtrend.
        for i in range(count - 30, count):
            prices[i] = 100.0 - (i - (count - 30)) * 2
    return prices

async def main():
    tech = TechnicalAnalysisService()
    screener = ScreenerService()
    
    cases = [
        ("Case 1 (260 candles, EMA20 > EMA50)", 260, "case1"),
        ("Case 2 (260 candles, EMA20 < EMA50)", 260, "case2"),
        ("Case 3 (25 candles, EMA50 unavailable)", 25, "case3"),
    ]
    
    for name, count, ctype in cases:
        print(f"\n--- {name} ---")
        prices = get_close_prices(ctype, count)
        candles = create_candles(count, prices)
        
        # We must use analyze_bulk which expects dict[str, list[OHLCVPoint]]
        universe = {"TEST": candles}
        tech_results = tech.analyze_bulk(universe, AnalysisMode.swing)
        
        if "TEST" not in tech_results:
            print("Failed to analyze.")
            continue
            
        t_res = tech_results["TEST"]
        inds = t_res.indicators
        
        print(f"EMA_20: {inds.get('ema_20')}")
        print(f"EMA_50: {inds.get('ema_50')}")
        print(f"EMA50_Available: {inds.get('ema50_available')}")
        print(f"EMA20_Above_EMA50: {inds.get('ema20_above_ema50')}")
        
        # Test scoring
        conds = screener._build_conditions(inds, candles[-1], candles[-2], True, t_res)
        score = screener._weighted_score(candles, t_res, conds)
        
        print(f"Conditions -> ema20_above_ema50: {conds.get('ema20_above_ema50')}")
        print(f"Conditions -> ema50_available: {conds.get('ema50_available')}")
        print(f"Calculated Score: {score}")

if __name__ == "__main__":
    asyncio.run(main())
