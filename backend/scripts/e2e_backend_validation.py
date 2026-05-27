import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.screener_service import ScreenerService, scanner_metrics
from app.services.market_data_service import MarketDataService
from app.services.fyers_service import FyersService
from app.schemas import AnalysisMode

def main():
    print("="*60)
    print("PHASE 1 - 5, 7 - 11: E2E BACKEND RUNTIME VALIDATION")
    print("="*60)
    
    md_svc = MarketDataService()
    fyers_svc = FyersService()
    screener_svc = ScreenerService(fyers_service=fyers_svc)
    
    print("\n--- Phase 1: Environment & Health Validation ---")
    universe = ["RELIANCE-EQ", "INFY-EQ", "TCS-EQ", "HDFCBANK-EQ", "ICICIBANK-EQ"]
    screener_svc.validate_startup_health(universe)
    print(f"Startup Health Metrics: {screener_svc.get_metrics()}")
    
    print("\n--- Phase 8: Invalid Symbol Injection ---")
    universe.append("INVALID-SYMBOL-EQ")
    print("Injected INVALID-SYMBOL-EQ into scan queue")
    
    print("\n--- Phase 2 & 10: Real Scanner Execution & Performance ---")
    start_time = datetime.now()
    results = screener_svc.screen_symbols_swing(
        symbols=universe,
        lookback_window=260,
        stage_name="E2E_VALIDATION"
    )
    duration = (datetime.now() - start_time).total_seconds()
    print(f"Scanner completed in {duration:.2f} seconds")
    
    print("\n--- Phase 8: Invalid Symbol Validation ---")
    if fyers_svc._is_blacklisted("INVALID-SYMBOL-EQ"):
        print("PASS: INVALID-SYMBOL-EQ was quarantined safely")
    else:
        print("FAIL: Invalid symbol was not quarantined")
        
    print("\n--- Phase 3: Database Persistence Validation ---")
    for sym in ["RELIANCE-EQ", "INFY-EQ", "TCS-EQ", "HDFCBANK-EQ", "ICICIBANK-EQ"]:
        count = md_svc.get_candle_count(sym, "1D")
        latest = md_svc.get_latest_candle_time(sym, "1D")
        print(f"{sym}: {count} candles, latest: {latest}")
        if count < 260:
            print(f"FAIL: {sym} has insufficient history ({count})")
            
    print("\n--- Phase 4 & 5: Indicator & Recommendation Validation ---")
    passed_stocks = [r for r in results if r.matched]
    print(f"Analyzed: {len(results)}, Passed: {len(passed_stocks)}")
    
    for res in results:
        if any(v is None or (isinstance(v, float) and v != v) for v in [res.sma_200, res.ema_20, res.close, res.volume]):
            print(f"FAIL: NaN indicator detected for {res.symbol}")
            
    for res in passed_stocks:
        print(f"Recommendation: {res.symbol} | Score: {res.screener_score} | SMA200: {res.sma_200} | EMA20: {res.ema_20} | Close: {res.close}")
            
    print("\n--- Phase 7: Health Endpoint Metrics ---")
    print(screener_svc.get_metrics())
    
    print("\n--- Phase 9: Corrupted Cache Recovery Simulation ---")
    print("Simulating DB corruption for INFY-EQ...")
    # Delete some rows to trigger CORRUPTED/STALE_INCOMPLETE
    from app.db.session import SessionLocal
    with SessionLocal() as db:
        from app.models.market_data import HistoricalCandle
        from sqlalchemy import delete
        stmt = delete(HistoricalCandle).where(HistoricalCandle.symbol == "INFY-EQ")
        db.execute(stmt)
        db.commit()
    
    count_after = md_svc.get_candle_count("INFY-EQ", "1D")
    print(f"INFY-EQ candles after deletion: {count_after}")
    
    print("Triggering forced rebuild scan for INFY-EQ...")
    screener_svc.screen_symbols_swing(
        symbols=["INFY-EQ"],
        lookback_window=260,
        stage_name="E2E_CORRUPTION_RECOVERY"
    )
    
    count_recovered = md_svc.get_candle_count("INFY-EQ", "1D")
    print(f"INFY-EQ candles after forced rebuild: {count_recovered}")
    if count_recovered >= 260:
        print("PASS: Cache recovered successfully from corruption")
    else:
        print("FAIL: Cache failed to recover")
        
    print("\n--- Phase 11: Observability ---")
    print("Check backend logs for forced rebuild telemetry.")

if __name__ == "__main__":
    main()
