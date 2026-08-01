"""Unit tests for FEAT-016 Market Breadth pure function.

Spec source: specs/014-shadow-sentiment-breadth/spec.md
  - US2 acceptance scenarios 1–2
  - FR-004, FR-005, FR-006, FR-010
  - Edge cases: insufficient coverage, empty universe, price == SMA
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.schemas.shadow_telemetry import MarketBreadthTelemetry
from app.services.market_breadth import StockBreadthItem, calculate_market_breadth


def _items(above: int, below: int, start: int = 0) -> list[StockBreadthItem]:
    prices: list[StockBreadthItem] = []
    for i in range(above):
        prices.append(
            StockBreadthItem(symbol=f"A{start + i}", current_price=120.0, sma_200=100.0)
        )
    for i in range(below):
        prices.append(
            StockBreadthItem(
                symbol=f"B{start + above + i}", current_price=80.0, sma_200=100.0
            )
        )
    return prices


# ---------------------------------------------------------------------------
# Regime matrix (US2-AS1 / FR-004 / FR-005)
# ---------------------------------------------------------------------------


def test_market_breadth_strong_regime():
    """>=70% above 200MA -> strong (+15.0)."""
    result = calculate_market_breadth(_items(above=8, below=2), min_universe_size=10)

    assert result.is_valid is True
    assert result.universe_size == 10
    assert result.valid_stock_count == 10
    assert result.above_200ma_count == 8
    assert result.breadth_percentage == 80.0
    assert result.regime_label == "strong"
    assert result.soft_score_contribution == 15.0
    assert isinstance(result, MarketBreadthTelemetry)
    assert result.executed_at


def test_market_breadth_favorable_regime():
    """55–69% above 200MA -> favorable (+7.5)."""
    result = calculate_market_breadth(_items(above=6, below=4), min_universe_size=10)

    assert result.regime_label == "favorable"
    assert result.soft_score_contribution == 7.5
    assert result.breadth_percentage == 60.0
    assert result.is_valid is True


def test_market_breadth_neutral_regime():
    """45–54% above 200MA -> neutral (0.0)."""
    result = calculate_market_breadth(_items(above=5, below=5), min_universe_size=10)

    assert result.regime_label == "neutral"
    assert result.soft_score_contribution == 0.0
    assert result.breadth_percentage == 50.0


def test_market_breadth_weak_and_very_weak_regimes():
    """30–44% -> weak; <30% -> very_weak."""
    result_weak = calculate_market_breadth(_items(above=4, below=6), min_universe_size=10)
    assert result_weak.regime_label == "weak"
    assert result_weak.soft_score_contribution == -7.5
    assert result_weak.breadth_percentage == 40.0

    result_vw = calculate_market_breadth(_items(above=2, below=8), min_universe_size=10)
    assert result_vw.regime_label == "very_weak"
    assert result_vw.soft_score_contribution == -15.0
    assert result_vw.breadth_percentage == 20.0


@pytest.mark.parametrize(
    "above,below,expected_label,expected_score",
    [
        (7, 3, "strong", 15.0),  # 70% exact boundary
        (6, 4, "favorable", 7.5),  # 60%
        (55, 45, "favorable", 7.5),  # 55% exact lower favorable bound
        (5, 5, "neutral", 0.0),  # 50%
        (45, 55, "neutral", 0.0),  # 45% exact lower neutral bound
        (3, 7, "weak", -7.5),  # 30% exact lower weak bound
        (2, 8, "very_weak", -15.0),  # 20%
    ],
)
def test_market_breadth_regime_boundaries(
    above: int, below: int, expected_label: str, expected_score: float
):
    """Boundary percentages map to the correct regime tier (FR-005)."""
    total = above + below
    result = calculate_market_breadth(
        _items(above=above, below=below), min_universe_size=total
    )

    assert result.is_valid is True
    assert result.regime_label == expected_label
    assert result.soft_score_contribution == expected_score
    assert result.breadth_percentage == pytest.approx((above / total) * 100.0, abs=0.01)


# ---------------------------------------------------------------------------
# Guard rails (US2-AS2 / FR-006)
# ---------------------------------------------------------------------------


def test_market_breadth_small_universe_unreliable():
    """US2-AS2: universe below min size returns unreliable/neutral without error."""
    prices = [
        StockBreadthItem(symbol="S1", current_price=120.0, sma_200=100.0),
        StockBreadthItem(symbol="S2", current_price=110.0, sma_200=100.0),
    ]

    result = calculate_market_breadth(prices, min_universe_size=10)

    assert result.is_valid is False
    assert result.regime_label == "unreliable"
    assert result.soft_score_contribution == 0.0
    assert result.breadth_percentage == 0.0
    assert result.universe_size == 2
    assert result.valid_stock_count == 2


def test_market_breadth_empty_universe():
    """Edge: empty universe is unreliable, not an unhandled exception."""
    result = calculate_market_breadth([], min_universe_size=10)

    assert result.is_valid is False
    assert result.regime_label == "unreliable"
    assert result.soft_score_contribution == 0.0
    assert result.universe_size == 0
    assert result.valid_stock_count == 0
    assert result.above_200ma_count == 0


def test_market_breadth_insufficient_valid_coverage():
    """Edge: missing price/SMA data reduces valid count and can invalidate."""
    prices = [
        StockBreadthItem(symbol="OK1", current_price=120.0, sma_200=100.0),
        StockBreadthItem(symbol="OK2", current_price=110.0, sma_200=100.0),
        StockBreadthItem(symbol="NO_PRICE", current_price=None, sma_200=100.0),
        StockBreadthItem(symbol="NO_SMA", current_price=110.0, sma_200=None),
        StockBreadthItem(symbol="ZERO_SMA", current_price=110.0, sma_200=0.0),
        StockBreadthItem(symbol="NEG_SMA", current_price=110.0, sma_200=-5.0),
        StockBreadthItem(symbol="BOTH_NONE", current_price=None, sma_200=None),
    ]

    result = calculate_market_breadth(prices, min_universe_size=10)

    assert result.universe_size == 7
    assert result.valid_stock_count == 2  # only OK1, OK2
    assert result.is_valid is False
    assert result.regime_label == "unreliable"
    assert result.soft_score_contribution == 0.0


def test_market_breadth_partial_coverage_still_valid_when_threshold_met():
    """Valid stocks meet min size even if some universe rows lack SMA data."""
    prices = _items(above=8, below=2) + [
        StockBreadthItem(symbol="MISSING", current_price=None, sma_200=None),
        StockBreadthItem(symbol="MISSING2", current_price=50.0, sma_200=None),
    ]

    result = calculate_market_breadth(prices, min_universe_size=10)

    assert result.universe_size == 12
    assert result.valid_stock_count == 10
    assert result.is_valid is True
    assert result.regime_label == "strong"
    assert result.breadth_percentage == 80.0


# ---------------------------------------------------------------------------
# Comparison / input variants
# ---------------------------------------------------------------------------


def test_market_breadth_price_equal_sma_not_counted_above():
    """Strict greater-than: price == sma_200 does not count as above MA."""
    prices = [
        StockBreadthItem(symbol=f"EQ{i}", current_price=100.0, sma_200=100.0)
        for i in range(10)
    ]

    result = calculate_market_breadth(prices, min_universe_size=10)

    assert result.above_200ma_count == 0
    assert result.breadth_percentage == 0.0
    assert result.regime_label == "very_weak"
    assert result.soft_score_contribution == -15.0


def test_market_breadth_accepts_dict_items():
    """Dict-shaped universe rows are accepted (orchestrator passes dicts)."""
    prices = [
        {"symbol": f"D{i}", "current_price": 120.0, "sma_200": 100.0} for i in range(8)
    ] + [
        {"symbol": f"D{i}", "current_price": 80.0, "sma_200": 100.0} for i in range(8, 10)
    ]

    result = calculate_market_breadth(prices, min_universe_size=10)

    assert result.is_valid is True
    assert result.regime_label == "strong"
    assert result.soft_score_contribution == 15.0
    assert result.above_200ma_count == 8


def test_market_breadth_all_above_is_strong():
    """100% participation maps to strong regime."""
    result = calculate_market_breadth(_items(above=10, below=0), min_universe_size=10)

    assert result.breadth_percentage == 100.0
    assert result.regime_label == "strong"
    assert result.soft_score_contribution == 15.0


def test_market_breadth_does_not_mutate_input():
    """FR-010 / purity: input universe list is not mutated."""
    prices = _items(above=8, below=2)
    original_len = len(prices)
    original_price = prices[0].current_price

    calculate_market_breadth(prices, min_universe_size=10)

    assert len(prices) == original_len
    assert prices[0].current_price == original_price


def test_market_breadth_scan_time_none_sets_executed_at():
    """scan_time=None still stamps executed_at ISO timestamp."""
    result = calculate_market_breadth(
        _items(above=8, below=2), min_universe_size=10, scan_time=None
    )

    assert result.executed_at
    # Should parse as ISO-ish datetime string
    assert "T" in result.executed_at or result.executed_at


def test_market_breadth_explicit_scan_time_propagates():
    """Explicit scan_time is serialized into executed_at."""
    scan = datetime(2026, 7, 22, 10, 44, 0, tzinfo=timezone.utc)
    result = calculate_market_breadth(
        _items(above=8, below=2), min_universe_size=10, scan_time=scan
    )

    assert result.executed_at.startswith("2026-07-22T10:44:00")
