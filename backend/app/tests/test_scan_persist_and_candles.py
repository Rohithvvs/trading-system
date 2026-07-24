"""Regression tests for scanner KeyError + empty save_latest_scan counts."""
from __future__ import annotations

import pytest

from app.db.scan_store import _count_scan_items, _normalize_scan_payload
from app.services.latest_scan_service import _close_price, _swing_indicators
from app.schemas import (
    AnalysisMode,
    FinalRecommendation,
    FullAnalysisResponse,
    OHLCVPoint,
    RecommendationReasoning,
    ScreenerConditionResult,
    ScreenerResponse,
    StockAnalysisResult,
    TechnicalAnalysisResult,
)


def _rec(action: str, score: float = 70.0) -> FinalRecommendation:
    return FinalRecommendation(
        action=action,
        confidence=0.7,
        score=score,
        reasoning=RecommendationReasoning(
            bullets=["t"], risk_factors=[], invalidation_signals=[]
        ),
        trade_plans=[],
        summary=f"{action} setup",
    )


def test_normalize_screener_response_counts_buy_watch():
    """save_latest_scan previously read payload['items'] which ScreenerResponse lacks."""
    payload = {
        "scanned_symbols": 500,
        "shortlisted_symbols": ["RAIN-EQ", "TCS-EQ", "INFY-EQ"],
        "buy_candidate_symbols": ["RAIN-EQ", "TCS-EQ"],
        "watch_candidate_symbols": ["INFY-EQ"],
        "all_analyzed_stocks": [
            {"symbol": "RAIN-EQ", "matched": True, "technical_signal": "bullish", "screener_score": 90},
            {"symbol": "TCS-EQ", "matched": True, "technical_signal": "bullish", "screener_score": 85},
            {"symbol": "INFY-EQ", "matched": True, "technical_signal": "neutral", "screener_score": 70},
            {"symbol": "XYZ-EQ", "matched": False, "technical_signal": "bearish", "screener_score": 10},
        ],
        "matches": [
            {"symbol": "RAIN-EQ", "matched": True},
            {"symbol": "TCS-EQ", "matched": True},
            {"symbol": "INFY-EQ", "matched": True},
        ],
        "analysis": {
            "items": [
                {"symbol": "RAIN-EQ", "recommendation": {"action": "BUY", "score": 88}},
                {"symbol": "TCS-EQ", "recommendation": {"action": "BUY", "score": 82}},
                {"symbol": "INFY-EQ", "recommendation": {"action": "WATCH", "score": 65}},
            ]
        },
    }
    normalized = _normalize_scan_payload(payload)
    assert len(normalized["items"]) >= 3
    total, shortlisted, buy, watch = _count_scan_items(normalized)
    assert shortlisted == 3
    assert buy == 2
    assert watch == 1
    # Must not report Total stored = 0 when lists are populated
    assert total >= 3


def test_normalize_legacy_items_payload_still_works():
    payload = {
        "items": [
            {"symbol": "RELIANCE", "matched": True, "signal": "BUY"},
            {"symbol": "TCS", "matched": True, "signal": "WATCH"},
            {"symbol": "BAD", "matched": False, "signal": "REJECT"},
        ]
    }
    normalized = _normalize_scan_payload(payload)
    total, shortlisted, buy, watch = _count_scan_items(normalized)
    assert total == 3
    assert shortlisted == 2
    assert buy == 1
    assert watch == 1


def test_swing_indicators_from_technical_list():
    item = StockAnalysisResult(
        symbol="RAIN-EQ",
        ohlcv=[
            OHLCVPoint(
                timestamp="2026-01-01T00:00:00",
                open=1,
                high=2,
                low=0.5,
                close=1.5,
                volume=100,
            )
        ],
        technical=[
            TechnicalAnalysisResult(
                mode=AnalysisMode.swing,
                signal="bullish",
                score=80,
                indicators={"sma_50": 10.0, "sma_200": 9.0, "rsi_14": 55.0, "macd": 0.1},
                summary="ok",
            )
        ],
        news_articles=[],
        news_summary="",
        news_sentiment_label="NEUTRAL",
        news_sentiment_score=0.5,
        fundamental=None,
        backtests=[],
        recommendation=_rec("BUY"),
        disclaimer="x",
    )
    tech = _swing_indicators(item)
    assert tech["sma_50"] == 10.0
    assert tech["rsi_14"] == 55.0
    assert _close_price(item) == 1.5


def test_candles_dict_safe_access_pattern():
    """Document the fixed access pattern — never bare [symbol] without ensure."""
    modes = [AnalysisMode.swing]
    candles_by_symbol_and_mode = {
        "TCS-EQ": {AnalysisMode.swing: [object()]},
        # RAIN-EQ intentionally missing (prefetched partial)
    }
    request_symbols = ["TCS-EQ", "RAIN-EQ", "SENCO-EQ"]

    missing = [s for s in request_symbols if s not in candles_by_symbol_and_mode]
    assert missing == ["RAIN-EQ", "SENCO-EQ"]

    # After fill simulation
    for s in missing:
        candles_by_symbol_and_mode[s] = {AnalysisMode.swing: []}

    for symbol in request_symbols:
        candles = candles_by_symbol_and_mode.get(symbol)
        assert candles is not None  # never KeyError
        series = candles.get(AnalysisMode.swing) or []
        # empty series → DATA_UNAVAILABLE path, not crash
        if not series:
            assert symbol in missing


@pytest.mark.asyncio
async def test_save_latest_scan_counts_screener_shape(monkeypatch):
    """Integration: save_latest_scan logging path uses buy/watch lists."""
    from app.db import scan_store

    class _FakeResult:
        def __init__(self):
            pass

    class _FakeDB:
        async def connection(self):
            class C:
                dialect = type("D", (), {"name": "sqlite"})()

            return C()

        async def execute(self, *a, **k):
            return _FakeResult()

        async def commit(self):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(scan_store, "AsyncSessionLocal", lambda: _FakeDB())

    payload = {
        "scanned_symbols": 100,
        "shortlisted_symbols": ["A", "B", "C"],
        "buy_candidate_symbols": ["A", "B"],
        "watch_candidate_symbols": ["C"],
        "all_analyzed_stocks": [
            {"symbol": "A", "matched": True},
            {"symbol": "B", "matched": True},
            {"symbol": "C", "matched": True},
        ],
        "matches": [],
        "analysis": {"items": []},
    }
    await scan_store.save_latest_scan(payload)
    # If we got here without exception, upsert path works with normalized payload
    total, shortlisted, buy, watch = _count_scan_items(_normalize_scan_payload(payload))
    assert buy == 2 and watch == 1 and shortlisted == 3
