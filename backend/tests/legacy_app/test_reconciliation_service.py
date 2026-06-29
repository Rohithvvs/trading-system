import pytest
import asyncio
import os
from unittest.mock import patch, MagicMock
from backend.app.services.candle_reconciliation_service import CandleReconciliationService

@pytest.fixture
def recon_service():
    return CandleReconciliationService()

def test_verify_historical_migration_no_legacy_db(recon_service):
    """
    Test that if candle_cache.db does not exist, the migration is marked as successful.
    """
    with patch("os.path.exists", return_value=False):
        result = recon_service.verify_historical_migration()
        assert result is True

@patch("app.services.candle_reconciliation_service.sqlite3.connect")
@patch("app.services.candle_reconciliation_service.SessionLocal")
def test_verify_historical_migration_mismatch(mock_session, mock_connect, recon_service):
    """
    Test that if legacy DB has more rows than primary DB, migration fails.
    """
    # Mock legacy DB
    mock_conn = MagicMock()
    mock_cursor = [("TCS", 500), ("INFY", 600)]
    mock_conn.execute.return_value = mock_cursor
    mock_connect.return_value = mock_conn
    
    # Mock primary DB
    mock_db = MagicMock()
    # Primary DB is missing some INFY candles
    mock_db.execute.return_value = [("TCS", 500), ("INFY", 550)]
    mock_session.return_value.__enter__.return_value = mock_db

    with patch("os.path.exists", return_value=True):
        with patch("app.services.candle_reconciliation_service.logger") as mock_logger:
            result = recon_service.verify_historical_migration()
            assert result is False
            mock_logger.warning.assert_called_with(
                "historical_migration_mismatch",
                extra={'symbol': 'INFY', 'legacy_count': 600, 'primary_count': 550, 'deficit': 50}
            )

@pytest.mark.asyncio
async def test_reconciliation_job_duplicate_prevention(recon_service):
    """
    Test that the lock prevents concurrent/duplicate reconciliation jobs.
    """
    # Force the lock to fail acquiring
    with patch.object(recon_service, "_acquire_lock", return_value=False):
        with patch("app.services.candle_reconciliation_service.logger") as mock_logger:
            await recon_service.reconciliation_job(["RELIANCE"])
            mock_logger.warning.assert_called_with("Reconciliation job already running or locked. Skipping.")

@patch("app.services.candle_reconciliation_service.SessionLocal")
def test_detect_gaps(mock_session, recon_service):
    """
    Test gap detection correctly maps SQLite window function results.
    """
    mock_db = MagicMock()
    class RowMock:
        def __init__(self, symbol, prev, ts, diff):
            self.symbol = symbol
            self.prev_timestamp = prev
            self.timestamp = ts
            self.days_diff = diff
            
    mock_db.execute.return_value = [
        RowMock("WIPRO", "2023-01-01 00:00:00", "2023-01-05 00:00:00", 4)
    ]
    mock_session.return_value.__enter__.return_value = mock_db
    
    gaps = recon_service.detect_gaps("WIPRO")
    assert len(gaps) == 1
    assert gaps[0]['days_diff'] == 4
    assert gaps[0]['symbol'] == "WIPRO"
