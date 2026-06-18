"""Memory audit test script - mocks FYERS to test scanner memory profile locally."""
import asyncio
import os
import sys
from unittest.mock import MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.services.screener_service import ScreenerService
from backend.app.config.settings import settings


class FakeFyersService:
    """Minimal FYERS mock that returns empty candles (DB-only mode)."""
    _network_pool = None

    def __init__(self):
        from concurrent.futures import ThreadPoolExecutor
        self._network_pool = ThreadPoolExecutor(max_workers=3)

    def fetch_incremental_ohlcv(self, symbol, cached_candles):
        return []

    def get_ohlcv_source(self, symbol, mode, resolution):
        return "CANDLE_CACHE_DB"

    def get_candles_cached(self, **kwargs):
        return []


async def main():
    fake_fyers = FakeFyersService()
    service = ScreenerService(fyers_service=fake_fyers)
    symbols = settings.nifty500_symbols
    print(f"Triggering scanner on {len(symbols)} symbols...")
    await service.screen_symbols_swing(symbols, 260, "MemoryAudit")


if __name__ == "__main__":
    asyncio.run(main())
