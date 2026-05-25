import pytest
import sqlite3
from unittest.mock import patch, MagicMock
from sqlalchemy.exc import OperationalError
from backend.app.services.market_engine_service import MarketEngineService

@pytest.fixture
def test_engine():
    with patch("backend.app.services.market_engine_service.FyersService"):
        engine = MarketEngineService()
        engine._feed.start = MagicMock()
        yield engine

def test_sqlite_operational_error_graceful_handling(test_engine, caplog):
    """
    Simulate an active trading sequence. Mid-trade, inject an artificial sqlite3.OperationalError (exclusive file lock).
    Assert the backend catches exceptions safely, logs it, and doesn't crash.
    """
    with patch("backend.app.services.market_engine_service.SessionLocal") as mock_session_local:
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        # Inject OperationalError on commit
        mock_db.commit.side_effect = OperationalError("statement", "params", sqlite3.OperationalError("database is locked"))

        # Trigger tick
        test_engine._on_tick("RELIANCE", 2500.0)

        # Assert no crash and log contains error
        assert any("Tick processing error for RELIANCE" in record.message for record in caplog.records)
        assert test_engine.latest_ltp["RELIANCE"] == 2500.0

@pytest.mark.asyncio
async def test_websocket_connection_reset_retry(test_engine, caplog):
    """
    Force a dirty WebSocket drop (ConnectionResetError). 
    Assert it logs it and triggers automated connection retry logic instead of crashing.
    """
    test_engine.is_market_hours = MagicMock(return_value=True)
    test_engine._desired_symbols = MagicMock(return_value={"RELIANCE"})
    test_engine._feed.sync_symbols = MagicMock()
    
    # Manually trigger a ConnectionResetError in the on_feed_error callback
    with patch("backend.app.services.market_engine_service.SessionLocal") as mock_session_local:
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_session = MagicMock()
        test_engine._get_or_create_session = MagicMock(return_value=mock_session)
        
        test_engine._on_feed_error(ConnectionResetError("Connection reset by peer"))
        
        # Verify the status flag reflects websocket drop
        assert not test_engine._feed.connected
        
        # Run one loop iteration to simulate the recovery
        # Call reconcile session which is the retry logic
        await test_engine._reconcile_session(mock_db, mock_session)
        
        # Assert feed is restarted
        test_engine._feed.start.assert_called_once()
        assert mock_session.status == "RUNNING"
