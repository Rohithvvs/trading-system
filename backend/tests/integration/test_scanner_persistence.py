from __future__ import annotations

from datetime import datetime, timezone

import pytest

import backend.app.routes.analysis as analysis_routes
from backend.app.schemas.analysis import (
    AnalysisResponse,
    FullAnalysisResponse,
    RankingsResponse,
    ScreenerConditionResult,
    ScreenerResponse,
)
from tests.utils.db_assertions import assert_scan_history_stored, write_db_snapshot


def fake_screener_response() -> ScreenerResponse:
    match = ScreenerConditionResult(
        symbol="INFY-EQ",
        close=100,
        ema_20=99,
        sma_30=98,
        sma_50=97,
        sma_100=96,
        sma_200=95,
        macd=1,
        macd_signal=0.5,
        supertrend=94,
        volume=100000,
        previous_volume=90000,
        screener_score=82,
        technical_signal="bullish",
        technical_score=80,
        candles_fetched=90,
        conditions={"close_above_ema20": True},
        matched=True,
    )
    rankings = RankingsResponse(
        rankings=[],
        buy_rankings=[],
        watch_rankings=[],
        best_intraday_candidate=None,
        best_swing_candidate=None,
        disclaimer="test",
    )
    analysis = FullAnalysisResponse(
        items=[],
        rankings=rankings,
        disclaimer="test",
        generated_at=datetime.now(timezone.utc),
    )
    return ScreenerResponse(
        scanned_symbols=1,
        screener_name="Test Scanner",
        data_valid_symbols=["INFY-EQ"],
        eligible_symbols=["INFY-EQ"],
        shortlisted_symbols=["INFY-EQ"],
        buy_candidate_symbols=["INFY-EQ"],
        watch_candidate_symbols=[],
        matched_symbols=["INFY-EQ"],
        matches=[match],
        all_analyzed_stocks=[match],
        analysis=analysis,
        disclaimer="test",
        data_source="mock",
    )


@pytest.mark.integration
def test_screener_full_persists_latest_scan_and_history(client, db_session, monkeypatch, artifact_dir):
    class FakeRouterAgent:
        def __init__(self, db):
            self.db = db

        def screener_full(self, payload):
            return fake_screener_response()

    monkeypatch.setattr(analysis_routes, "RouterAgent", FakeRouterAgent)

    response = client.post(
        "/analysis/screener/full",
        json={"mode": "swing", "timeframe": {"intraday": "5m", "swing": "1d", "lookback_window": 30}, "symbols": ["INFY-EQ"], "top_n": 1},
    )
    assert response.status_code == 200, response.text
    assert response.json()["shortlisted_symbols"] == ["INFY-EQ"]

    history_row = assert_scan_history_stored(db_session)
    assert history_row["shortlisted_count"] == 1

    latest_scan = client.get("/analysis/scan/latest")
    assert latest_scan.status_code == 200
    assert latest_scan.json()["available"] is True

    diagnostic = client.get("/test-diagnostics/scan-store")
    assert diagnostic.status_code == 200
    assert diagnostic.json()["stored_in_sqlite"] is True

    write_db_snapshot(db_session, artifact_dir, "scanner-persistence", ["scan_history_snapshots"])
