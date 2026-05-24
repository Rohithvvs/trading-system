import pytest
import datetime
from unittest.mock import AsyncMock, patch, MagicMock
from backend.app.services.analytics_service import AnalyticsService
from backend.app.models.analysis import AnalysisHistory

@pytest.fixture
def mock_fyers():
    with patch("backend.app.services.analytics_service.FyersService") as MockFyers:
        mock_instance = MockFyers.return_value
        # Mock current price
        mock_instance.fetch_ltp.return_value = 110.0
        
        # Mock historical candles
        candle_mock = MagicMock()
        candle_mock.close = 100.0
        candle_mock.timestamp = datetime.datetime.now() - datetime.timedelta(days=5)
        mock_instance.fetch_ohlcv.return_value = [candle_mock]
        
        yield mock_instance

@pytest.mark.asyncio
async def test_track_strategy_drift_alpha_calculation(mock_fyers):
    with patch("backend.app.services.analytics_service.SessionLocal") as mock_session_maker:
        mock_db = MagicMock()
        mock_session_maker.return_value.__enter__.return_value = mock_db
        
        # Mock DB records
        history_mock = MagicMock(spec=AnalysisHistory)
        history_mock.created_at = datetime.datetime.now() - datetime.timedelta(days=5)
        history_mock.recommendation = "BUY"
        history_mock.sentiment_score = 0.8
        history_mock.technical_score = 65.0
        
        # db.execute(stmt).all() returns list of (history, symbol) tuples
        mock_db.execute.return_value.all.return_value = [(history_mock, "RELIANCE.NS")]
        
        service = AnalyticsService()
        await service.track_strategy_drift()
        
        # Verify FYERS calls
        assert mock_fyers.fetch_ltp.called
        assert mock_fyers.fetch_ohlcv.called
        
        # Verify DB add log entry
        assert mock_db.add.called
        
        # Extract the saved log entry
        args, kwargs = mock_db.add.call_args
        log_entry = args[0]
        
        # (110 - 100) / 100 * 100 = 10.0% alpha
        assert log_entry.realized_return_5d == 10.0
        assert log_entry.symbol == "RELIANCE.NS"
        assert log_entry.dominant_agent == "News/Sentiment Catalyst"
