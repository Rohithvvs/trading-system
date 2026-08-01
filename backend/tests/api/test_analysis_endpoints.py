import asyncio
import pytest
import datetime
from fastapi.testclient import TestClient
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.schemas.analysis import ArticleItem, OHLCVPoint
from backend.app.models.analysis import AnalysisHistory
from backend.app.db.session import AsyncSessionLocal
from backend.app.services.admin_bootstrap_service import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_PASSWORD,
    ensure_default_admin,
)
from backend.app.services.feature_permission_service import ensure_default_feature_permissions


def _run(coro):
    return asyncio.run(coro)


async def _bootstrap_admin_async() -> None:
    async with AsyncSessionLocal() as db:
        await ensure_default_admin(db)
        await ensure_default_feature_permissions(db, commit=True)
        await db.commit()


def _admin_headers(client: TestClient) -> dict:
    """Sprint 5: screener routes require advanced_scanner + authenticated principal."""
    _run(_bootstrap_admin_async())
    res = client.post(
        "/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASSWORD},
    )
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
def mock_externals(monkeypatch):
    import backend.app.services.fyers_service as fyers
    import backend.app.agents.orchestrator_agent as orch_mod

    # Needs at least 200 points for indicators
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

    monkeypatch.setattr(fyers, "FyersService", FakeFyersService)
    monkeypatch.setattr(orch_mod, "FyersService", FakeFyersService)

    import backend.app.services.screener_service as screener_service

    monkeypatch.setattr(screener_service, "FyersService", FakeFyersService)


def test_full_analysis_endpoint(client, db_session, mock_externals):
    # Test real full_analysis hitting the actual RouterAgent -> OrchestratorAgent
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
        mock_news.return_value = [
            ArticleItem(
                title="News headline for analysis",
                description="body",
                source="Reuters",
                url="http://example.com/news",
                published_at=datetime.datetime(2023, 6, 1, 10, 0, 0),
                sentiment_score=0.8,
            )
        ]
        mock_llm.return_value = 0.8

        response = client.post("/analysis/full", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) == 1
    assert data["items"][0]["symbol"] == "HDFCBANK-EQ"


def test_screener_full_endpoint_requires_auth(test_engine, mock_externals):
    """Sprint 5: unauthenticated screener is rejected."""
    with TestClient(app) as client:
        response = client.post(
            "/analysis/screener/full",
            json={
                "mode": "swing",
                "timeframe": {"intraday": "5m", "swing": "1D", "lookback_window": 30},
                "top_n": 1,
                "symbols": ["HDFCBANK-EQ"],
            },
        )
        assert response.status_code == 401


def test_screener_full_endpoint_sse_stream(test_engine, mock_externals):
    """
    Test the /analysis/screener/full endpoint as a real SSE stream.

    Asserts progress events are yielded and the stream terminates with a
    complete/error terminal event (does not hang).
    """
    # Real async get_db path (avoid sync client fixture override)
    with TestClient(app) as client:
        headers = _admin_headers(client)
        # Use an explicit symbol shortlist so the custom-symbol path is taken
        # (avoids full-universe loading delays in unit/integration tests).
        payload = {
            "mode": "swing",
            "timeframe": {
                "intraday": "5m",
                "swing": "1D",
                "lookback_window": 260,
            },
            "top_n": 5,
            "symbols": ["HDFCBANK-EQ", "TCS-EQ"],
        }

        stages_seen: list[str] = []
        terminal_status: str | None = None

        with patch("backend.app.agents.fundamental_analysis_agent.yf.Ticker") as mock_ticker, \
             patch("backend.app.agents.news_analysis_agent.NewsService.fetch_recent_news") as mock_news, \
             patch("backend.app.services.sentiment_service.LLMService.analyze_sentiment") as mock_llm:

            mock_ticker.return_value.info = {"revenueGrowth": 0.15, "profitMargins": 0.2}
            mock_news.return_value = []
            mock_llm.return_value = 0.5

            with client.stream(
                "POST", "/analysis/screener/full", json=payload, headers=headers
            ) as response:
                assert response.status_code == 200
                assert "text/event-stream" in response.headers["content-type"]

                for chunk in response.iter_lines():
                    if not chunk:
                        continue

                    if chunk.startswith("data: "):
                        import json

                        event_data = json.loads(chunk[6:])

                        if "status" in event_data and event_data["status"] in (
                            "complete",
                            "error",
                        ):
                            terminal_status = event_data["status"]
                            break

                        if "stage" in event_data:
                            stages_seen.append(event_data["stage"])

        # Progress should have started (auth / fetch / analysis stages).
        assert len(stages_seen) >= 1, f"Expected progress stages, got {stages_seen}"
        # Stream must terminate (complete preferred; error is still non-hanging).
        assert terminal_status in {"complete", "error"}, (
            f"Expected terminal SSE status, got {terminal_status!r}; stages={stages_seen}"
        )
