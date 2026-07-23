from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from app.schemas.shadow_telemetry import MarketBreadthTelemetry


class StockBreadthItem(BaseModel):
    symbol: str
    current_price: float | None = None
    sma_200: float | None = None


def calculate_market_breadth(
    universe_prices: list[StockBreadthItem | dict[str, Any]],
    min_universe_size: int = 10,
    scan_time: datetime | None = None,
) -> MarketBreadthTelemetry:
    """Pure function calculating market breadth percentage and soft regime contribution.

    - Breadth % = (count of stocks with current_price > sma_200) / valid_stock_count * 100
    - Regime thresholds:
        >= 70%: strong (+15.0)
        55% - 69%: favorable (+7.5)
        45% - 54%: neutral (0.0)
        30% - 44%: weak (-7.5)
        < 30%: very_weak (-15.0)
    - Small universe guard rail: if valid_stock_count < min_universe_size -> unreliable (0.0)
    - Zero side-effects
    """
    if scan_time is None:
        scan_time = datetime.now(timezone.utc)

    universe_size = len(universe_prices)
    valid_stock_count = 0
    above_200ma_count = 0

    for item in universe_prices:
        if isinstance(item, dict):
            price = item.get("current_price")
            sma200 = item.get("sma_200")
        else:
            price = item.current_price
            sma200 = item.sma_200

        if price is not None and sma200 is not None and sma200 > 0:
            valid_stock_count += 1
            if price > sma200:
                above_200ma_count += 1

    if valid_stock_count < min_universe_size:
        return MarketBreadthTelemetry(
            universe_size=universe_size,
            valid_stock_count=valid_stock_count,
            above_200ma_count=above_200ma_count,
            breadth_percentage=0.0,
            regime_label="unreliable",
            soft_score_contribution=0.0,
            is_valid=False,
            executed_at=scan_time.isoformat(),
        )

    breadth_pct = (above_200ma_count / valid_stock_count) * 100.0

    if breadth_pct >= 70.0:
        regime = "strong"
        soft_contribution = 15.0
    elif breadth_pct >= 55.0:
        regime = "favorable"
        soft_contribution = 7.5
    elif breadth_pct >= 45.0:
        regime = "neutral"
        soft_contribution = 0.0
    elif breadth_pct >= 30.0:
        regime = "weak"
        soft_contribution = -7.5
    else:
        regime = "very_weak"
        soft_contribution = -15.0

    return MarketBreadthTelemetry(
        universe_size=universe_size,
        valid_stock_count=valid_stock_count,
        above_200ma_count=above_200ma_count,
        breadth_percentage=round(breadth_pct, 2),
        regime_label=regime,
        soft_score_contribution=soft_contribution,
        is_valid=True,
        executed_at=scan_time.isoformat(),
    )
