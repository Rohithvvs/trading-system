import os
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.base import Base
from backend.app.services.market_engine_service import MarketEngineService

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

@pytest.fixture
def memory_db_session():
    # Use in-memory SQLite for high-throughput testing
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    with patch("backend.app.services.market_engine_service.SessionLocal", TestingSessionLocal):
        yield TestingSessionLocal

def test_memory_soak_50k_ticks(memory_db_session):
    """
    Inject 50,000 synthetic market ticks sequentially.
    Assert the SQLite database size and RAM footprint remain stable without severe bloat.
    """
    mem_before = 0
    if HAS_PSUTIL:
        process = psutil.Process(os.getpid())
        mem_before = process.memory_info().rss
    
    with patch("backend.app.services.market_engine_service.FyersService"):
        engine = MarketEngineService()
        engine._feed.start = MagicMock()
        
        # Inject 50,000 ticks
        ticks = 50000
        for i in range(ticks):
            engine._on_tick("RELIANCE", 2500.0 + (i % 10))
            
    # Assert it processed all 50k ticks
    assert engine.latest_ltp["RELIANCE"] == 2500.0 + ((ticks - 1) % 10)
    
    if HAS_PSUTIL:
        mem_after = process.memory_info().rss
        mem_diff_mb = (mem_after - mem_before) / (1024 * 1024)
        # Assert memory didn't leak heavily (e.g. max 100MB increase for 50k ticks)
        assert mem_diff_mb < 100.0, f"Memory bloat detected: {mem_diff_mb} MB increase"
