import pytest
import asyncio
import pandas as pd
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch, MagicMock
from sqlalchemy.exc import OperationalError
from app.services.market_data_service import MarketDataService
from app.models.market_data import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import tempfile
import os

# Create a temporary file database for testing so threads share the same tables
test_db_path = os.path.join(tempfile.gettempdir(), "test_concurrent.db")
if os.path.exists(test_db_path):
    os.remove(test_db_path)

engine = create_engine(
    f"sqlite:///{test_db_path}", connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

@pytest.fixture
def md_service():
    return MarketDataService()

@pytest.fixture
def sample_candles_df():
    now = datetime.now(timezone.utc)
    dates = [now - timedelta(days=i) for i in range(5)]
    df = pd.DataFrame({
        "open": [100, 101, 102, 103, 104],
        "high": [105, 106, 107, 108, 109],
        "low": [95, 96, 97, 98, 99],
        "close": [102, 103, 104, 105, 106],
        "volume": [1000, 1100, 1200, 1300, 1400]
    }, index=dates)
    return df

@pytest.mark.asyncio
@patch("app.services.market_data_service.SessionLocal", new=TestingSessionLocal)
@patch("app.services.market_data_service.engine", new=engine)
async def test_concurrent_upserts(md_service, sample_candles_df):
    """
    Test that concurrent upserts for the same symbol do not result in
    fatal database locked errors due to the retry mechanism.
    """
    async def upsert_task(i):
        # Slightly alter volume to simulate updates
        df = sample_candles_df.copy()
        df['volume'] += i
        # Run in thread as the method is synchronous
        await asyncio.to_thread(md_service.upsert_candles, "RELIANCE", "1D", df)
        return True

    # Spawn 10 concurrent upserts
    tasks = [upsert_task(i) for i in range(10)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for r in results:
        assert r is True, f"A concurrent insert failed: {r}"

def test_stale_data_detection(md_service):
    """
    Test that check_stale_candles correctly identifies stale data.
    """
    with patch("app.services.market_data_service.logger") as mock_logger:
        # 1D threshold is > 2 days
        stale_date = datetime.now(timezone.utc) - timedelta(days=3)
        md_service.check_stale_candles("TCS", "1D", stale_date)
        
        mock_logger.warning.assert_called_with(
            "stale_candle_detected",
            extra=unittest.mock.ANY
        )

@patch("app.services.market_data_service.time.sleep", return_value=None)
@patch("app.services.market_data_service.SessionLocal")
def test_retry_exhaustion(mock_session, mock_sleep, md_service, sample_candles_df):
    """
    Test that if OperationalError occurs 5 times, it is correctly raised
    and the exhaustion is logged.
    """
    # Setup mock to raise OperationalError with 'database is locked'
    mock_db = MagicMock()
    mock_db.execute.side_effect = OperationalError("database is locked", None, None)
    mock_session.return_value.__enter__.return_value = mock_db

    with patch("app.services.market_data_service.logger") as mock_logger:
        with pytest.raises(OperationalError):
            md_service.upsert_candles("INFY", "1D", sample_candles_df)
        
        # Verify it retried 4 times and logged lock_retry, then failed on the 5th
        assert mock_logger.warning.call_count >= 4
        mock_logger.error.assert_called_with("candle_upsert_failed", extra=unittest.mock.ANY)
