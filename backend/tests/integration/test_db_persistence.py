import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.db.base import Base
from backend.app.models.analysis import StrategyPerformanceLog, AnalysisHistory
from backend.app.models.stock import WatchedStock
import datetime

@pytest.fixture
def test_db():
    # Use SQLite in-memory for testing the CRUD operations deterministically
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

def test_strategy_performance_log_crud(test_db):
    # Create Stock
    stock = WatchedStock(symbol="INFY.NS", display_name="Infosys")
    test_db.add(stock)
    test_db.commit()
    
    # Create History
    history = AnalysisHistory(
        stock_id=stock.id,
        mode="swing",
        technical_score=75.0,
        sentiment_score=0.9,
        backtest_score=15.0,
        recommendation="BUY",
        confidence=0.82,
        reasoning="Strong technical breakout.",
        created_at=datetime.datetime.now() - datetime.timedelta(days=10)
    )
    test_db.add(history)
    test_db.commit()
    
    # Create Performance Log
    log_entry = StrategyPerformanceLog(
        symbol="INFY.NS",
        screened_date=history.created_at,
        initial_score=history.technical_score,
        dominant_agent="Technical Analysis",
        realized_return_5d=3.2,
        realized_return_10d=8.4
    )
    test_db.add(log_entry)
    test_db.commit()
    
    # Read & Validate Persistence
    fetched_log = test_db.query(StrategyPerformanceLog).filter(StrategyPerformanceLog.symbol == "INFY.NS").first()
    assert fetched_log is not None
    assert fetched_log.realized_return_5d == 3.2
    assert fetched_log.realized_return_10d == 8.4
    assert fetched_log.initial_score == 75.0

def test_database_isolation_rollback(test_db):
    # Ensure this test starts with an empty DB, verifying transaction isolation
    logs = test_db.query(StrategyPerformanceLog).all()
    assert len(logs) == 0
