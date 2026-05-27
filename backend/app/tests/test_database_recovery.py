import pytest
import os
import uuid
import tempfile
from datetime import datetime, timezone
import pandas as pd
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError

from app.models.market_data import HistoricalCandle
from app.services.market_data_service import MarketDataService

@pytest.fixture(scope="function")
def isolated_db():
    db_fd, db_path = tempfile.mkstemp(suffix=f"_{uuid.uuid4().hex[:8]}.db")
    os.close(db_fd)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False, "timeout": 15})
    
    from app.db.session import init_db
    with patch("app.db.session.engine", engine):
        with patch("app.db.session.settings.database_url", f"sqlite:///{db_path}"):
            init_db()

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    yield TestingSessionLocal, engine
    
    engine.dispose()
    try:
        os.remove(db_path)
    except OSError:
        pass


@pytest.mark.recovery
def test_interrupted_chunked_upsert_rollback(isolated_db):
    TestingSessionLocal, engine = isolated_db
    
    with patch("app.services.market_data_service.SessionLocal", TestingSessionLocal):
        with patch("app.services.market_data_service.engine", engine):
            svc = MarketDataService()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        
        # 1. Provide a batch of 2000 candles (which spans 3 chunks of 900)
        dates = pd.date_range(end=now, periods=2000, freq="1min")
        df = pd.DataFrame({
            "open": [100.0] * 2000,
            "high": [105.0] * 2000,
            "low": [95.0] * 2000,
            "close": [102.0] * 2000,
            "volume": [100] * 2000,
        }, index=dates)

        # 2. Mock db.execute to crash specifically on the 2nd chunk
        # This simulates a mid-batch WAL failure
        original_execute = engine.execute if hasattr(engine, 'execute') else None
        
        # Actually, the service uses `db.execute(stmt)`. So we can patch TestingSessionLocal().execute
        chunk_counter = 0
        
        def crashing_execute(*args, **kwargs):
            nonlocal chunk_counter
            chunk_counter += 1
            if chunk_counter == 2:
                # First chunk succeeds, second chunk crashes
                raise OperationalError("database is locked", params=None, orig=None)
            
            # Since we can't easily proxy Session.execute, we will mock at the service level _upsert_chunk
            return None

        # Alternative approach: patch _upsert_chunk to fail on the second call
        original_upsert = svc._upsert_chunk
        def crashing_upsert_chunk(symbol, timeframe, chunk):
            nonlocal chunk_counter
            chunk_counter += 1
            if chunk_counter == 2:
                # We raise a generic Exception or OperationalError to trigger the rollback logic
                raise OperationalError("simulated mid-batch crash", params=None, orig=None)
            original_upsert(symbol, timeframe, chunk)

        with patch.object(svc, "_upsert_chunk", side_effect=crashing_upsert_chunk):
            with pytest.raises(OperationalError):
                svc.upsert_candles("TCS", "1m", df)
                
        # 3. Assert DB state
        # The first chunk committed (900 rows)
        # The second chunk crashed
        # The third chunk never ran
        
        # Let's verify DB contains exactly 900 rows from chunk 1!
        # Because we chunk out of the transaction scope to keep transactions short!
        with TestingSessionLocal() as db:
            candles = db.query(HistoricalCandle).filter_by(symbol="TCS").all()
            assert len(candles) == 900
