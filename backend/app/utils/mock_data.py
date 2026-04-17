from __future__ import annotations

from datetime import datetime, timedelta, timezone


def generate_mock_ohlcv(symbol: str, points: int) -> list[dict[str, float | int | datetime]]:
    now = datetime.now(timezone.utc)
    base_price = 800 + (sum(ord(char) for char in symbol) % 1800)
    candles: list[dict[str, float | int | datetime]] = []

    for index in range(points):
        ts = now - timedelta(days=points - index)
        drift = (index * 0.8) + ((len(symbol) % 4) * 1.2)
        close = round(base_price + drift + ((index % 5) - 2) * 2.4, 2)
        open_price = round(close - 3.2, 2)
        high = round(close + 5.5, 2)
        low = round(close - 6.1, 2)
        volume = 100000 + (index * 1700) + ((base_price % 9) * 1250)
        candles.append(
            {
                "timestamp": ts,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )

    return candles


def generate_mock_articles(symbol: str) -> list[dict[str, str | float | datetime]]:
    now = datetime.now(timezone.utc)
    return [
        {
            "title": f"{symbol} attracts renewed trader focus ahead of earnings season",
            "description": f"{symbol} is seeing stronger watchlist activity as traders look for setup confirmation.",
            "source": "Mock Market Wire",
            "url": f"https://example.com/{symbol.lower()}-earnings",
            "published_at": now - timedelta(hours=3),
            "sentiment_score": 0.42,
        },
        {
            "title": f"Analysts weigh margin trends and demand outlook for {symbol}",
            "description": f"Recent commentary on {symbol} remains balanced with an eye on execution and sector rotation.",
            "source": "Mock Finance Desk",
            "url": f"https://example.com/{symbol.lower()}-margin",
            "published_at": now - timedelta(hours=7),
            "sentiment_score": 0.08,
        },
    ]
