import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.models.analysis import AnalysisHistory
from backend.app.services.analytics_service import AnalyticsService


@pytest.fixture
def mock_fyers():
    with patch("backend.app.services.analytics_service.FyersService") as MockFyers:
        mock_instance = MockFyers.return_value
        mock_instance.fetch_ltp = AsyncMock(return_value=110.0)

        candle_mock = MagicMock()
        candle_mock.close = 100.0
        candle_mock.timestamp = datetime.datetime.now() - datetime.timedelta(days=5)
        mock_instance.fetch_ohlcv = AsyncMock(return_value=[candle_mock])

        yield mock_instance


@pytest.mark.asyncio
async def test_track_strategy_drift_alpha_calculation(mock_fyers):
    history_mock = MagicMock(spec=AnalysisHistory)
    history_mock.created_at = datetime.datetime.now() - datetime.timedelta(days=5)
    history_mock.recommendation = "BUY"
    history_mock.sentiment_score = 0.8
    history_mock.technical_score = 65.0
    history_mock.backtest_score = 20.0

    mock_db = AsyncMock()
    # First target day (5d) returns one BUY record; subsequent days empty.
    execute_result_with_rows = MagicMock()
    execute_result_with_rows.all.return_value = [(history_mock, "RELIANCE.NS")]
    execute_result_empty = MagicMock()
    execute_result_empty.all.return_value = []
    execute_result_empty.scalar_one_or_none.return_value = None

    # track_strategy_drift loops 5/10/20 days; also queries StrategyPerformanceLog.
    mock_db.execute = AsyncMock(
        side_effect=[
            execute_result_with_rows,  # day 5 history
            execute_result_empty,  # day 5 existing log lookup
            execute_result_empty,  # day 10 history
            execute_result_empty,  # day 20 history
        ]
    )
    mock_db.add = MagicMock()

    service = AnalyticsService()
    await service.track_strategy_drift(mock_db)

    assert mock_fyers.fetch_ltp.called
    assert mock_fyers.fetch_ohlcv.called
    assert mock_db.add.called

    args, _kwargs = mock_db.add.call_args
    log_entry = args[0]
    # (110 - 100) / 100 * 100 = 10.0% alpha
    assert log_entry.realized_return_5d == 10.0
    assert log_entry.symbol == "RELIANCE.NS"
    assert log_entry.dominant_agent == "News/Sentiment Catalyst"
