"""
FEAT-001 — Swing Trading architecture correction regression tests.

These tests prove that the recommendation pipeline always runs in Swing
mode and that intraday analysis is never selected by default or coerced
into the pipeline, while preserving existing Swing behaviour and the
AnalysisMode.intraday enum value for non-recommendation modules.
"""
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


import pytest
from unittest.mock import MagicMock, patch

from backend.app.schemas.analysis import (
    AnalysisMode,
    AnalysisRequest,
    ScreenerRequest,
    TimeframeConfig,
)
from backend.app.agents.orchestrator_agent import OrchestratorAgent


# ---------------------------------------------------------------------------
# 1. Schema defaults
# ---------------------------------------------------------------------------

def test_analysis_request_defaults_to_swing():
    req = AnalysisRequest(symbols=["TCS-EQ"])
    assert req.mode == AnalysisMode.swing


def test_screener_request_defaults_to_swing():
    req = ScreenerRequest()
    assert req.mode == AnalysisMode.swing


def test_analysis_request_explicit_swing_unchanged():
    req = AnalysisRequest(symbols=["TCS-EQ"], mode=AnalysisMode.swing)
    assert req.mode == AnalysisMode.swing


def test_analysis_request_accepts_both_without_error():
    req = AnalysisRequest(symbols=["TCS-EQ"], mode=AnalysisMode.both)
    assert req.mode == AnalysisMode.both


def test_analysis_request_accepts_intraday_without_error():
    req = AnalysisRequest(symbols=["TCS-EQ"], mode=AnalysisMode.intraday)
    assert req.mode == AnalysisMode.intraday


# ---------------------------------------------------------------------------
# 2. Orchestrator _resolve_modes — intraday never enters the pipeline
# ---------------------------------------------------------------------------

def _make_orchestrator():
    return OrchestratorAgent.__new__(OrchestratorAgent)


def test_resolve_modes_swing_returns_swing_only():
    orch = _make_orchestrator()
    result = orch._resolve_modes(AnalysisMode.swing)
    assert result == [AnalysisMode.swing]


def test_resolve_modes_both_returns_swing_only():
    orch = _make_orchestrator()
    result = orch._resolve_modes(AnalysisMode.both)
    assert result == [AnalysisMode.swing]
    assert AnalysisMode.intraday not in result


def test_resolve_modes_intraday_returns_swing_only():
    orch = _make_orchestrator()
    result = orch._resolve_modes(AnalysisMode.intraday)
    assert result == [AnalysisMode.swing]
    assert AnalysisMode.intraday not in result


def test_resolve_modes_never_contains_intraday():
    orch = _make_orchestrator()
    for mode in AnalysisMode:
        result = orch._resolve_modes(mode)
        assert AnalysisMode.intraday not in result, (
            f"_resolve_modes({mode.value}) returned {result} which contains intraday"
        )


def test_resolve_modes_always_returns_swing():
    orch = _make_orchestrator()
    for mode in AnalysisMode:
        result = orch._resolve_modes(mode)
        assert result == [AnalysisMode.swing], (
            f"_resolve_modes({mode.value}) returned {result}, expected [swing]"
        )


# ---------------------------------------------------------------------------
# 3. Enum preservation — intraday not deleted for other modules
# ---------------------------------------------------------------------------

def test_analysis_mode_intraday_enum_still_exists():
    assert hasattr(AnalysisMode, "intraday")
    assert AnalysisMode.intraday.value == "intraday"


def test_analysis_mode_both_enum_still_exists():
    assert hasattr(AnalysisMode, "both")
    assert AnalysisMode.both.value == "both"


def test_analysis_mode_all_values_preserved():
    values = {m.value for m in AnalysisMode}
    assert values == {"intraday", "swing", "both"}


# ---------------------------------------------------------------------------
# 4. API-level: /analysis/full without mode defaults to swing
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_externals(monkeypatch):
    import datetime
    import backend.app.services.fyers_service as fyers
    import backend.app.agents.orchestrator_agent as orch_mod
    from backend.app.schemas.analysis import OHLCVPoint

    base_date = datetime.datetime(2023, 1, 1)
    candles = [
        OHLCVPoint(
            timestamp=base_date + datetime.timedelta(days=i),
            open=100.0 + (i * 0.1),
            high=105.0 + (i * 0.1),
            low=95.0 + (i * 0.1),
            close=102.0 + (i * 0.1),
            volume=100000 + i,
        )
        for i in range(250)
    ]

    class FakeFyersService:
        def __init__(self, *args, **kwargs):
            pass

        def get_candles_cached(self, *args, **kwargs):
            return candles

        async def fetch_ohlcv(self, *args, **kwargs):
            return candles

        def fetch_incremental_ohlcv(self, *args, **kwargs):
            return candles

        def combine_candles(self, *args, **kwargs):
            return candles

        def get_ohlcv_source(self, *args, **kwargs):
            return "MOCK"

        def _cache_symbol(self, symbol: str) -> str:
            return symbol

        def _is_fyers_configured(self) -> bool:
            return True

        def has_fyers_credentials(self) -> bool:
            return False

        def is_fyers_sdk_available(self) -> bool:
            return False

    monkeypatch.setattr(fyers, "FyersService", FakeFyersService)
    monkeypatch.setattr(orch_mod, "FyersService", FakeFyersService)

    import backend.app.services.screener_service as screener_service
    monkeypatch.setattr(screener_service, "FyersService", FakeFyersService)


def test_full_analysis_no_mode_defaults_to_swing(client, db_session, mock_externals):
    payload = {
        "symbols": ["HDFCBANK-EQ"],
        "timeframe": {
            "intraday": "5m",
            "swing": "1D",
            "lookback_window": 180,
        },
    }

    with patch("backend.app.agents.fundamental_analysis_agent.yf.Ticker") as mock_ticker, \
         patch("backend.app.agents.news_analysis_agent.NewsService.fetch_recent_news") as mock_news, \
         patch("backend.app.services.sentiment_service.LLMService.analyze_sentiment") as mock_llm:

        mock_ticker.return_value.info = {"revenueGrowth": 0.15, "profitMargins": 0.2}
        mock_news.return_value = [{"title": "News", "link": "url"}]
        mock_llm.return_value = 0.8

        response = client.post("/analysis/full", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1

    technical_modes = [
        tech.get("mode") for tech in data["items"][0].get("technical", [])
    ]
    assert all(m == "swing" for m in technical_modes), (
        f"Expected all technical results to be swing, got {technical_modes}"
    )
    assert "intraday" not in technical_modes


def test_full_analysis_explicit_both_coerced_to_swing(client, db_session, mock_externals):
    payload = {
        "symbols": ["HDFCBANK-EQ"],
        "mode": "both",
        "timeframe": {
            "intraday": "5m",
            "swing": "1D",
            "lookback_window": 180,
        },
    }

    with patch("backend.app.agents.fundamental_analysis_agent.yf.Ticker") as mock_ticker, \
         patch("backend.app.agents.news_analysis_agent.NewsService.fetch_recent_news") as mock_news, \
         patch("backend.app.services.sentiment_service.LLMService.analyze_sentiment") as mock_llm:

        mock_ticker.return_value.info = {"revenueGrowth": 0.15, "profitMargins": 0.2}
        mock_news.return_value = [{"title": "News", "link": "url"}]
        mock_llm.return_value = 0.8

        response = client.post("/analysis/full", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1

    technical_modes = [
        tech.get("mode") for tech in data["items"][0].get("technical", [])
    ]
    assert all(m == "swing" for m in technical_modes), (
        f"Expected all technical results to be swing, got {technical_modes}"
    )
    assert "intraday" not in technical_modes


def test_full_analysis_explicit_intraday_coerced_to_swing(client, db_session, mock_externals):
    payload = {
        "symbols": ["HDFCBANK-EQ"],
        "mode": "intraday",
        "timeframe": {
            "intraday": "5m",
            "swing": "1D",
            "lookback_window": 180,
        },
    }

    with patch("backend.app.agents.fundamental_analysis_agent.yf.Ticker") as mock_ticker, \
         patch("backend.app.agents.news_analysis_agent.NewsService.fetch_recent_news") as mock_news, \
         patch("backend.app.services.sentiment_service.LLMService.analyze_sentiment") as mock_llm:

        mock_ticker.return_value.info = {"revenueGrowth": 0.15, "profitMargins": 0.2}
        mock_news.return_value = [{"title": "News", "link": "url"}]
        mock_llm.return_value = 0.8

        response = client.post("/analysis/full", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1

    technical_modes = [
        tech.get("mode") for tech in data["items"][0].get("technical", [])
    ]
    assert all(m == "swing" for m in technical_modes), (
        f"Expected all technical results to be swing, got {technical_modes}"
    )
    assert "intraday" not in technical_modes


def test_full_analysis_explicit_swing_unchanged(client, db_session, mock_externals):
    payload = {
        "symbols": ["HDFCBANK-EQ"],
        "mode": "swing",
        "timeframe": {
            "intraday": "5m",
            "swing": "1D",
            "lookback_window": 180,
        },
    }

    with patch("backend.app.agents.fundamental_analysis_agent.yf.Ticker") as mock_ticker, \
         patch("backend.app.agents.news_analysis_agent.NewsService.fetch_recent_news") as mock_news, \
         patch("backend.app.services.sentiment_service.LLMService.analyze_sentiment") as mock_llm:

        mock_ticker.return_value.info = {"revenueGrowth": 0.15, "profitMargins": 0.2}
        mock_news.return_value = [{"title": "News", "link": "url"}]
        mock_llm.return_value = 0.8

        response = client.post("/analysis/full", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1

    technical_modes = [
        tech.get("mode") for tech in data["items"][0].get("technical", [])
    ]
    assert all(m == "swing" for m in technical_modes), (
        f"Expected all technical results to be swing, got {technical_modes}"
    )
