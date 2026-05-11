from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.app.schemas import OHLCVPoint


def fake_candles(days: int = 90, start_price: float = 100.0) -> list[OHLCVPoint]:
    base = datetime.now(timezone.utc) - timedelta(days=days)
    candles: list[OHLCVPoint] = []
    for index in range(days):
        close = start_price + index * 0.2
        candles.append(
            OHLCVPoint(
                timestamp=base + timedelta(days=index),
                open=close - 0.3,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=100000 + index,
            )
        )
    return candles


class FakeFyersService:
    def fetch_ltp(self, symbol: str) -> float:
        return 100.0

    def fetch_ohlcv(self, symbol: str, analysis_mode, interval: str, lookback_days: int, allow_mock: bool = False):
        return fake_candles(min(lookback_days, 90), 100.0)
