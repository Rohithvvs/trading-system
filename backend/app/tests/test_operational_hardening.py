import pytest
import pandas as pd
from datetime import datetime, timedelta
import pytz
from unittest.mock import patch, MagicMock
from backend.app.services.market_data_service import MarketDataService
from backend.app.services.candle_reconciliation_service import CandleReconciliationService
from backend.app.models.market_data import Base, HistoricalCandle
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import tempfile
import os

test_db_path = os.path.join(tempfile.gettempdir(), "test_operational.db")
if os.path.exists(test_db_path):
    os.remove(test_db_path)

engine = create_engine(
    f"sqlite:///{test_db_path}", connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

from alembic.config import Config
from alembic import command
from backend.app.config import settings
from backend.app.config.settings import ROOT_DIR
alembic_cfg = Config(str(ROOT_DIR / "backend" / "alembic.ini"))
alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{test_db_path}")
command.upgrade(alembic_cfg, "head")

@pytest.fixture(autouse=True)
def setup_db():
    with patch("app.services.market_data_service.SessionLocal", new=TestingSessionLocal):
        with patch("app.services.candle_reconciliation_service.SessionLocal", new=TestingSessionLocal):
            yield
            with TestingSessionLocal() as db:
                db.query(HistoricalCandle).delete()
                db.commit()

def test_sqlite_variable_explosion_prevention():
    """Test that a payload of 10,000 candles is safely chunked and inserted without OperationalError."""
    md_service = MarketDataService()
    
    # Generate 10k candles
    now = datetime.now(pytz.utc).replace(tzinfo=None)
    dates = [now - timedelta(minutes=i) for i in range(10000)]
    
    df = pd.DataFrame({
        "open": [100] * 10000,
        "high": [105] * 10000,
        "low": [95] * 10000,
        "close": [102] * 10000,
        "volume": [1000] * 10000
    }, index=dates)
    
    # Should not raise any OperationalError (too many variables)
    md_service.upsert_candles("RELIANCE", "1m", df)
    
    with TestingSessionLocal() as db:
        count = db.query(HistoricalCandle).filter_by(symbol="RELIANCE").count()
        assert count == 10000

@pytest.mark.asyncio
async def test_holiday_gap_suppression():
    service = CandleReconciliationService()
    
    # Mock Friday as latest
    friday = datetime(2023, 12, 1, 15, 30, 0) # Dec 1, 2023 was Friday
    monday = datetime(2023, 12, 4, 9, 15, 0) # Dec 4, 2023 was Monday
    
    gaps = [{
        "symbol": "TCS",
        "gap_start": friday,
        "gap_end": monday,
        "days_diff": 3
    }]
    
    with patch.object(service, "detect_gaps", return_value=gaps):
        with patch.object(service.md_service, "get_latest_candle_time", return_value=monday):
            with patch.object(service.fyers_service, "_request_history_with_retries") as mock_fetch:
                # Need to mock the lock so it can acquire
                with patch("app.services.lock_service.SessionLocal", new=TestingSessionLocal):
                    await service.reconciliation_job(["TCS"])
                
                # Should NOT have called fetch, because the gap is only Sat/Sun
                mock_fetch.assert_not_called()

@pytest.mark.asyncio
async def test_reconciliation_circuit_breaker():
    service = CandleReconciliationService()
    
    gaps = [{"symbol": "INFY", "gap_start": datetime(2023, 11, 1), "gap_end": datetime(2023, 11, 5), "days_diff": 4}]
    # 5 symbols, each has a gap
    symbols = ["S1", "S2", "S3", "S4", "S5", "S6"]
    
    with patch.object(service, "detect_gaps", return_value=gaps):
        with patch.object(service.md_service, "get_latest_candle_time", return_value=None):
            with patch.object(service.fyers_service, "_request_history_with_retries", side_effect=Exception("API Crash")):
                with patch("app.services.lock_service.SessionLocal", new=TestingSessionLocal):
                    # We expect the circuit breaker to trip at 5 failures
                    await service.reconciliation_job(symbols)
                
                # 5 failures max before break
                assert service.circuit_breaker_failures == 5
                assert service.circuit_breaker_tripped_until is not None
                
                # S6 should not have been attempted
                assert len(service.fyers_service._request_history_with_retries.mock_calls) == 5
