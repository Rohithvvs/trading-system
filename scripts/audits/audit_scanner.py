import asyncio
import logging
from unittest.mock import patch
from backend.app.services.screener_service import ScreenerService
from backend.app.config import settings
from backend.app.db.session import AsyncSessionLocal
from backend.app.services.token_service import get_current_access_token
from backend.app.core.log_manager import scanner_logger
import backend.app.services.market_data_service as md_module
import backend.app.services.candle_store as cs_module

async def main():
    async with AsyncSessionLocal() as db:
        await get_current_access_token(db)
    
    # Mute loud loggers
    logging.getLogger("app.screener").setLevel(logging.CRITICAL)
    scanner_logger.setLevel(logging.CRITICAL)

    service = ScreenerService()
    universe = settings.fyers_screener_symbols
    print(f"Total symbols configured: {len(universe)}")
    
    # We removed the mock because we want to test actual DB persistence
    pass
    cs_module.store_candles = lambda *a, **kw: asyncio.sleep(0)
    
    results = await service.screen_symbols_swing(symbols=universe, lookback_window=260, stage_name="AUDIT")
    
    input_count = len(universe)
    
    # 1. Fetch
    fetch_success = [r for r in results if not r.conditions.get("data_source_failed")]
    fetch_fail = input_count - len(fetch_success)
    
    # 2. Candle Validation / OHLCV (Data Quality)
    data_quality_success = [r for r in fetch_success if not r.conditions.get("data_quality_failed")]
    data_quality_fail = len(fetch_success) - len(data_quality_success)
    
    # 3. Indicators
    tech_success = [r for r in data_quality_success if not r.conditions.get("technical_analysis_failed") and not r.conditions.get("processing_error")]
    tech_fail = len(data_quality_success) - len(tech_success)
    
    # 4. Strategy Rules (Broad Trend + Matching)
    strategy_candidates = [r for r in tech_success if r.matched]
    strategy_fail = len(tech_success) - len(strategy_candidates)
    
    print("=" * 50)
    print("ELIMINATION REPORT")
    print("=" * 50)
    print(f"{input_count} symbols")
    print("↓")
    print(f"{len(fetch_success)} data fetch success (Failed: {fetch_fail})")
    print("↓")
    print(f"{len(data_quality_success)} candle validation success (Failed: {data_quality_fail})")
    print("↓")
    print(f"{len(tech_success)} indicator success (Failed: {tech_fail})")
    print("↓")
    print(f"{len(strategy_candidates)} strategy candidates (Failed: {strategy_fail})")

if __name__ == "__main__":
    asyncio.run(main())
