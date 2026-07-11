"""Unit tests for recursive JSON sanitization (Decimal / nested structures)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

import pytest

from backend.app.utils.json_sanitize import (
    assert_json_serializable,
    collect_decimal_paths,
    find_non_jsonable,
    sanitize_for_json,
)


class Color(Enum):
    RED = "red"


@dataclass
class Point:
    x: Decimal
    y: float


def test_decimal_to_float():
    assert sanitize_for_json(Decimal("12.50")) == 12.5
    assert isinstance(sanitize_for_json(Decimal("1")), float)


def test_nested_analytics_like_payload():
    """Mirrors paper-trading analytics fields that come from Numeric/Decimal columns."""
    raw = {
        "total_trades": 3,
        "win_rate_pct": Decimal("66.67"),
        "profit_factor": Decimal("1.85"),
        "average_profit": Decimal("250.00"),
        "average_loss": Decimal("-120.50"),
        "best_trade_symbol": "RELIANCE",
        "best_trade_amount": Decimal("500.25"),
        "worst_trade_symbol": "INFY",
        "worst_trade_amount": Decimal("-200.00"),
        "daily_pnl": [{"date": "2024-01-01", "pnl": Decimal("100.5")}],
        "cumulative_pnl": [{"date": "2024-01-01", "pnl": Decimal("100.5")}],
        "wins": 2,
        "losses": 1,
        "holding_periods": [
            {
                "symbol": "RELIANCE",
                "avg_holding_minutes": Decimal("45.5"),
                "total_trades": 2,
                "win_rate_pct": Decimal("50.0"),
            }
        ],
        "max_drawdown": Decimal("75.00"),
        "max_drawdown_pct": Decimal("0.75"),
        "current_streak_type": "win",
        "current_streak_count": 1,
    }

    paths = collect_decimal_paths(raw, "analytics")
    assert "analytics.profit_factor" in paths
    assert "analytics.best_trade_amount" in paths
    assert "analytics.daily_pnl[0].pnl" in paths
    assert "analytics.holding_periods[0].avg_holding_minutes" in paths

    safe = sanitize_for_json(raw)
    assert collect_decimal_paths(safe, "analytics") == []
    json.dumps(safe)  # must not raise

    assert safe["profit_factor"] == pytest.approx(1.85)
    assert safe["best_trade_amount"] == pytest.approx(500.25)
    assert safe["daily_pnl"][0]["pnl"] == pytest.approx(100.5)
    assert isinstance(safe["average_loss"], float)


def test_datetime_uuid_enum_dataclass():
    uid = UUID("12345678-1234-5678-1234-567812345678")
    raw = {
        "when": datetime(2024, 6, 1, 12, 30, 0),
        "day": date(2024, 6, 1),
        "id": uid,
        "color": Color.RED,
        "point": Point(Decimal("1.5"), 2.0),
        "tags": {"a", "b"},
        "coords": (Decimal("1"), Decimal("2")),
    }
    safe = sanitize_for_json(raw)
    json.dumps(safe)
    assert safe["when"].startswith("2024-06-01")
    assert safe["day"] == "2024-06-01"
    assert safe["id"] == str(uid)
    assert safe["color"] == "red"
    assert safe["point"]["x"] == 1.5
    assert isinstance(safe["tags"], list)
    assert safe["coords"] == [1.0, 2.0]


def test_assert_json_serializable_success():
    data = {"a": Decimal("1.23"), "b": [Decimal("4")]}
    out = assert_json_serializable(data, root_name="analytics")
    assert out == {"a": 1.23, "b": [4.0]}


def test_find_non_jsonable_on_unsanitized():
    raw = {"x": object()}
    paths = find_non_jsonable(raw, "analytics")
    assert any("analytics.x" in p for p in paths)


def test_round_decimal_stays_decimal_until_sanitize():
    """Python round(Decimal) returns Decimal — the historical analytics bug."""
    pnl = Decimal("100.126")
    rounded = round(pnl, 2)
    assert isinstance(rounded, Decimal)
    assert isinstance(sanitize_for_json(rounded), float)
