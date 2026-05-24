import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.db.base import Base
from backend.app.models.analysis import StrategyPerformanceLog, AnalysisHistory
from backend.app.models.stock import WatchedStock
import datetime

@pytest.fixture
def test_db():
    # Use SQLite in-memory for fast integration testing, but configured to test WAL behavior locally
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False}
    )
    # Enable WAL mode if it were a file, but for memory it ignores it. 
    # To truly test WAL concurrency, use a temporary file database.
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

def test_strategy_performance_log_schema(test_db):
    # Insert WatchedStock
    stock = WatchedStock(symbol="TCS.NS", company_name="TCS", active=True)
    test_db.add(stock)
    test_db.commit()
    
    # Insert AnalysisHistory
    history = AnalysisHistory(
        stock_id=stock.id,
        mode="swing",
        technical_score=80.0,
        sentiment_score=0.9,
        backtest_score=20.0,
        recommendation="BUY",
        confidence=0.85,
        reasoning="Bullish momentum",
        created_at=datetime.datetime.now() - datetime.timedelta(days=5)
    )
    test_db.add(history)
    test_db.commit()
    
    # Insert StrategyPerformanceLog
    log_entry = StrategyPerformanceLog(
        symbol="TCS.NS",
        screened_date=history.created_at,
        initial_score=history.technical_score,
        dominant_agent="News/Sentiment Catalyst",
        realized_return_5d=5.5
    )
    test_db.add(log_entry)
    test_db.commit()
    
    # Validate Schema Query
    fetched_log = test_db.query(StrategyPerformanceLog).filter(StrategyPerformanceLog.symbol == "TCS.NS").first()
    assert fetched_log is not None
    assert fetched_log.realized_return_5d == 5.5
    assert fetched_log.dominant_agent == "News/Sentiment Catalyst"
    assert fetched_log.initial_score == 80.0
