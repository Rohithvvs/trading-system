import asyncio
import logging
import unittest.mock
from backend.app.config import settings

# 1. Patch database writes BEFORE importing anything that might break
async def dummy_async(*a, **kw): pass

patcher1 = unittest.mock.patch('backend.app.services.market_data_service.MarketDataService.upsert_candles', new=dummy_async)
patcher1.start()

patcher2 = unittest.mock.patch('backend.app.services.candle_store.store_candles', new=dummy_async)
patcher2.start()

async def dummy_count(*a, **kw): return 220
patcher4 = unittest.mock.patch('backend.app.services.candle_store.get_candle_count', new=dummy_count)
patcher4.start()

# Also patch yfinance to avoid rate limits
# patcher3 = unittest.mock.patch('backend.app.services.fyers_service.FyersService._fallback_to_yfinance', new=dummy_async)
# patcher3.start()

from backend.app.services.screener_service import ScreenerService
from backend.app.db.session import AsyncSessionLocal
from backend.app.services.token_service import get_current_access_token
from backend.app.core.log_manager import scanner_logger

async def main():
    async with AsyncSessionLocal() as db:
        await get_current_access_token(db)
    
    # Mute loud loggers
    logging.getLogger("app.screener").setLevel(logging.CRITICAL)
    scanner_logger.setLevel(logging.CRITICAL)

    service = ScreenerService()
    universe = settings.fyers_screener_symbols
    
    results = await service.screen_symbols_swing(symbols=universe, lookback_window=260, stage_name="AUDIT")
    
    input_count = len(universe)
    fetch_success = [r for r in results if not r.conditions.get('data_source_failed')]
    fetch_fail = input_count - len(fetch_success)
    
    data_quality_success = [r for r in fetch_success if not r.conditions.get('data_quality_failed')]
    data_quality_fail = len(fetch_success) - len(data_quality_success)
    
    tech_success = [r for r in data_quality_success if not r.conditions.get('technical_analysis_failed') and not r.conditions.get('processing_error')]
    tech_fail = len(data_quality_success) - len(tech_success)
    
    strategy_candidates = [r for r in tech_success if r.matched]
    strategy_fail = len(tech_success) - len(strategy_candidates)
    
    print('==============================')
    print('ELIMINATION REPORT')
    print('==============================')
    print(f'{input_count} symbols')
    print('↓')
    print(f'{len(fetch_success)} data fetch success')
    print('↓')
    print(f'{len(data_quality_success)} candle validation success')
    print('↓')
    print(f'{len(tech_success)} indicator success')
    print('↓')
    print(f'{len(strategy_candidates)} strategy candidates')

if __name__ == '__main__':
    asyncio.run(main())
