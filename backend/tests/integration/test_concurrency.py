import asyncio
import tempfile
import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.db.base import Base
from backend.app.agents.orchestrator_agent import OrchestratorAgent
from backend.app.models.stock import WatchedStock
from backend.app.models.analysis import AnalysisHistory, BacktestHistory

@pytest.fixture
def file_db_session():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False, "timeout": 15}
    )
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
    
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        try:
            os.remove(path)
        except OSError:
            pass

@pytest.mark.asyncio
async def test_orchestrator_db_concurrency(file_db_session):
    agent = OrchestratorAgent(file_db_session)
    
    # Simulate 50 threads trying to create/get the SAME stock and persist analysis concurrently.
    
    def simulate_concurrent_analysis(i):
        # Trigger the DB operations that were raising "Session is already flushing"
        stock = agent._get_or_create_stock(f"TEST-EQ-{i%5}") # 5 unique symbols so there is contention
        
        class DummyBacktest:
            strategy_name = "test"
            total_return = 1.0
            cagr = 1.0
            max_drawdown = 1.0
            win_rate = 1.0
            profit_factor = 1.0
            trade_count = 1
            verdict = "Pass"
            
        class DummyRec:
            action = "BUY"
            confidence = 0.9
            summary = "Good"
            
        agent._persist_analysis(
            stock_id=stock,
            mode="swing",
            technical_score=80.0,
            sentiment_score=0.5,
            backtest=DummyBacktest(),
            recommendation=DummyRec()
        )
        return True

    tasks = [asyncio.to_thread(simulate_concurrent_analysis, i) for i in range(50)]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for r in results:
        # If the lock is working, there should be NO sqlalchemy exceptions
        assert not isinstance(r, Exception), f"Concurrency failed with exception: {r}"
        assert r is True
        
    # Verify the database state
    stocks = file_db_session.query(WatchedStock).all()
    assert len(stocks) == 5
