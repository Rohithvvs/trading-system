from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
import json
import pytest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.schemas.analysis import OHLCVPoint
from backend.app.db.session import AsyncSessionLocal
from backend.app.services.admin_bootstrap_service import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_PASSWORD,
    ensure_default_admin,
)
from backend.app.services.feature_permission_service import ensure_default_feature_permissions
from tests.utils.db_assertions import assert_scan_history_stored, write_db_snapshot


def _run(coro):
    return asyncio.run(coro)


async def _bootstrap_admin_async() -> None:
    async with AsyncSessionLocal() as db:
        await ensure_default_admin(db)
        await ensure_default_feature_permissions(db, commit=True)
        await db.commit()


def _admin_headers(client) -> dict:
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
    
    base_date = datetime(2023, 1, 1)
    candles = [
        OHLCVPoint(
            timestamp=base_date + timedelta(days=i), 
            open=100.0 + (i * 0.1), high=105.0 + (i * 0.1), low=95.0 + (i * 0.1), close=102.0 + (i * 0.1), volume=100000 + i
        )
        for i in range(250)
    ]
    
    class FakeFyersService:
        def __init__(self, *args, **kwargs): pass
        def get_candles_cached(self, *args, **kwargs): return candles
        async def fetch_ohlcv(self, *args, **kwargs): return candles
        def fetch_incremental_ohlcv(self, *args, **kwargs): return candles
        def combine_candles(self, *args, **kwargs): return candles
        def get_ohlcv_source(self, *args, **kwargs): return "MOCK"
        def _cache_symbol(self, symbol: str) -> str: return symbol
        def _is_fyers_configured(self) -> bool: return True
        
    monkeypatch.setattr(fyers, "FyersService", FakeFyersService)
    monkeypatch.setattr(orch_mod, "FyersService", FakeFyersService)
    
    import backend.app.services.screener_service as screener_service
    monkeypatch.setattr(screener_service, "FyersService", FakeFyersService)


@pytest.mark.integration
def test_screener_full_persists_latest_scan_and_history(db_session, test_engine, mock_externals, artifact_dir):
    # Real async get_db (no sync client fixture override) for Sprint 5 auth gates
    with TestClient(app) as client:
        headers = _admin_headers(client)
        with patch("backend.app.agents.fundamental_analysis_agent.yf.Ticker") as mock_ticker, \
             patch("backend.app.agents.news_analysis_agent.NewsService.fetch_recent_news") as mock_news, \
             patch("backend.app.services.sentiment_service.LLMService.analyze_sentiment") as mock_llm:
            
            mock_ticker.return_value.info = {"revenueGrowth": 0.15, "profitMargins": 0.2}
            mock_news.return_value = []
            mock_llm.return_value = 0.5
        
            response = client.post(
                "/analysis/screener/full",
                json={"mode": "swing", "timeframe": {"intraday": "5m", "swing": "1d", "lookback_window": 30}, "symbols": ["INFY-EQ"], "top_n": 1},
                headers=headers,
            )
        assert response.status_code == 200, response.text
        
        # Parse SSE stream to find the final result
        final_result = None
        for line in response.text.split("\n"):
            if line.startswith("data: "):
                data = json.loads(line[6:])
                if data.get("status") == "complete":
                    final_result = data.get("result")
        
        assert final_result is not None, "SSE stream did not emit a complete result"
        assert "INFY-EQ" in final_result["shortlisted_symbols"]

        history_row = assert_scan_history_stored(db_session)
        assert history_row["shortlisted_count"] >= 1

        latest_scan = client.get("/analysis/scan/latest", headers=headers)
        assert latest_scan.status_code == 200
        assert latest_scan.json()["available"] is True

        diagnostic = client.get("/test-diagnostics/scan-store")
        assert diagnostic.status_code == 200
        assert diagnostic.json()["stored_in_sqlite"] is True

    write_db_snapshot(db_session, artifact_dir, "scanner-persistence", ["scan_history_snapshots"])
