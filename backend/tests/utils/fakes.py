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


class FakePriceSequenceFyersService(FakeFyersService):
    def __init__(self, prices: dict[str, list[float]] | None = None) -> None:
        self.prices = prices or {}

    def fetch_ltp(self, symbol: str) -> float | None:
        values = self.prices.get(symbol, [])
        return values.pop(0) if values else None


class FakeMarketDataFeed:
    def __init__(self, on_tick, on_error, on_connection_change) -> None:
        self.on_tick = on_tick
        self.on_error = on_error
        self.on_connection_change = on_connection_change
        self.symbols: set[str] = set()
        self.connected = False
        self.start_calls = 0
        self.stop_calls = 0

    def start(self) -> None:
        self.start_calls += 1
        self.connected = True

    def stop(self, notify: bool = True) -> None:
        self.stop_calls += 1
        self.connected = False
        if notify:
            self.on_connection_change(False)

    def sync_symbols(self, symbols: set[str]) -> None:
        self.symbols = set(symbols)

    def emit(self, symbol: str, price: float) -> None:
        self.on_tick(symbol, price)

    def expire_token(self) -> None:
        self.on_error("token expired")

    def disconnect(self) -> None:
        self.on_error("socket disconnected")
