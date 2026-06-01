import asyncio
import json
from backend.app.db.session import AsyncSessionLocal
from sqlalchemy import text
from backend.app.services.technical_analysis_service import TechnicalAnalysisService
from backend.app.schemas import AnalysisMode, OHLCVPoint
from backend.app.config import settings
from collections import defaultdict

async def main():
    tech = TechnicalAnalysisService()
    
    universe_candles = {}
    universe = settings.nifty500_symbols
    
    async with AsyncSessionLocal() as db:
        res = await db.execute(text("SELECT symbol, timestamp, open, high, low, close, volume FROM historical_candles WHERE resolution = '1D' ORDER BY symbol, timestamp"))
        for row in res.fetchall():
            sym = row[0]
            if sym not in universe_candles:
                universe_candles[sym] = []
            universe_candles[sym].append(OHLCVPoint(
                timestamp=row[1], open=row[2], high=row[3], low=row[4], close=row[5], volume=row[6]
            ))
            
    filtered_candles = {sym: candles for sym, candles in universe_candles.items() if len(candles) >= 240}
    bulk_results = tech.analyze_bulk(filtered_candles, AnalysisMode.swing)
    from backend.app.services.screener_service import ScreenerService
    screener = ScreenerService()
    
    # Run the scoring loop
    class MockMDService: pass
    screener.market_data = MockMDService()
    
    final_results = []
    
    for symbol, candles in filtered_candles.items():
        technical = bulk_results.get(symbol)
        if not technical: continue
        
        latest = candles[-1]
        previous = candles[-2]
        
        broad_eligibility = screener._passes_broad_trend(candles, technical)
        conds = screener._build_conditions(technical.indicators, latest, previous, broad_eligibility, technical)
        score = screener._weighted_score(candles, technical, conds)
        
        is_matched = conds.get("broad_trend_eligibility", False)
        
        rec = "REJECTED"
        if is_matched:
            rec = "BUY" if score >= 72 else "WATCH"
            
        final_results.append({
            "symbol": symbol,
            "rec": rec,
            "score": score,
            "tech_score": technical.score,
            "indicators": technical.indicators,
            "close": latest.close
        })
        
    buys = [r for r in final_results if r["rec"] == "BUY"]
    watches = [r for r in final_results if r["rec"] == "WATCH"]
    rejects = [r for r in final_results if r["rec"] == "REJECTED"]
    
    buys.sort(key=lambda x: -x["score"])
    watches.sort(key=lambda x: -x["score"])
    
    print(f"Total Buys: {len(buys)}, Total Watches: {len(watches)}, Total Rejects: {len(rejects)}")
    
    def print_syms(label, lst):
        print(f"\n=== {label} ===")
        for i, r in enumerate(lst[:10]):
            c = r["indicators"]
            print(f"{i+1}. {r['symbol']}")
            print(f"  Close: {r['close']}, SMA50: {c.get('sma_50')}, SMA200: {c.get('sma_200')}")
            print(f"  RSI: {c.get('rsi_14')}, MACD: {c.get('macd')} (Sig: {c.get('macd_signal')})")
            print(f"  Supertrend: {c.get('supertrend')}, Tech Score: {r['tech_score']}, Screener Score: {r['score']}")
            print(f"  Rec: {r['rec']}")
            
    print_syms("BUY CANDIDATES", buys)
    print_syms("WATCH CANDIDATES", watches)
    print_syms("REJECTED CANDIDATES", rejects)

if __name__ == '__main__':
    asyncio.run(main())
