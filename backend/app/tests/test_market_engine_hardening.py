import pytest
import asyncio
import os
import uuid
import tempfile
import logging
from datetime import datetime
from unittest.mock import patch, MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.paper_trading import PaperTradingAccount, PaperOrder, PaperPosition, ExecutionEvent
from app.services.market_engine_service import MarketEngineService
from app.utils.symbol import canonical_symbol, fyers_symbol

@pytest.fixture(scope="function")
def isolated_db():
    db_fd, db_path = tempfile.mkstemp(suffix=f"_{uuid.uuid4().hex[:8]}.db")
    os.close(db_fd)
    
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 15}
    )
    
    from app.db.session import init_db
    with patch("app.db.session.engine", engine):
        with patch("app.db.session.settings.database_url", f"sqlite:///{db_path}"):
            init_db()

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    with TestingSessionLocal() as db:
        account = PaperTradingAccount(
            starting_balance=100000.0,
            cash_balance=100000.0,
        )
        db.add(account)
        db.commit()
        db.refresh(account)

    yield TestingSessionLocal, engine
    
    engine.dispose()
    if os.path.exists(db_path):
        os.remove(db_path)

def test_1_symbol_canonicalization():
    assert canonical_symbol("NSE:DATAPATTNS-EQ") == "DATAPATTNS"
    assert canonical_symbol("DATAPATTNS-EQ") == "DATAPATTNS"
    assert canonical_symbol("DATAPATTNS") == "DATAPATTNS"
    assert canonical_symbol("nse:datapattns-eq") == "DATAPATTNS"
    assert canonical_symbol("NSE:NIFTY50-INDEX") == "NIFTY50-INDEX"
    
    assert fyers_symbol("DATAPATTNS") == "NSE:DATAPATTNS-EQ"
    assert fyers_symbol("NIFTY50-INDEX", is_index=True) == "NSE:NIFTY50-INDEX"

@pytest.mark.asyncio
async def test_2_3_4_5_websocket_tick_matches_position(isolated_db):
    TestingSessionLocal, engine = isolated_db
    
    with patch("app.services.market_engine_service.SessionLocal", TestingSessionLocal), \
         patch("app.services.market_engine_service.AsyncSessionLocal", TestingSessionLocal):
        engine_svc = MarketEngineService()
        
        with TestingSessionLocal() as db:
            account = db.query(PaperTradingAccount).first()
            # 3. Position stored exactly as DATAPATTNS
            pos1 = PaperPosition(
                account_id=account.id, symbol="DATAPATTNS", qty=10, avg_entry_price=4800.0, 
                target=4900.0, stop_loss=4700.0, status="OPEN", lifecycle_state="OPEN_POSITION", monitor_enabled=True
            )
            # 8. Mixed-format: stored as DATAPATTNS-EQ (simulating old data from before canonicalization)
            pos2 = PaperPosition(
                account_id=account.id, symbol="CUPID-EQ", qty=10, avg_entry_price=160.0, 
                target=170.0, stop_loss=150.0, status="OPEN", lifecycle_state="OPEN_POSITION", monitor_enabled=True
            )
            db.add_all([pos1, pos2])
            db.commit()

        # 2. Websocket tick: NSE:DATAPATTNS-EQ, crossing target
        # 4. Target hit execution
        await engine_svc._on_tick("NSE:DATAPATTNS-EQ", 4905.0)
        
        # 5. Stop-loss execution
        await engine_svc._on_tick("NSE:CUPID-EQ", 149.0)
        
        with TestingSessionLocal() as db:
            p1 = db.query(PaperPosition).filter_by(symbol="DATAPATTNS").first()
            assert p1 is None  # Exited!
            
            p2 = db.query(PaperPosition).filter_by(symbol="CUPID-EQ").first()
            assert p2 is None  # Exited!

@pytest.mark.asyncio
async def test_6_7_reconciliation_missed_websocket(isolated_db):
    TestingSessionLocal, engine = isolated_db
    
    with patch("app.services.market_engine_service.SessionLocal", TestingSessionLocal), \
         patch("app.services.market_engine_service.AsyncSessionLocal", TestingSessionLocal):
        engine_svc = MarketEngineService()
        
        with TestingSessionLocal() as db:
            account = db.query(PaperTradingAccount).first()
            pos = PaperPosition(
                account_id=account.id, symbol="RELIANCE", qty=10, avg_entry_price=2500.0, 
                target=2600.0, status="OPEN", lifecycle_state="OPEN_POSITION", monitor_enabled=True
            )
            db.add(pos)
            db.commit()

        # Engine starts up and reconciles
        with patch("app.services.market_engine_service.MarketEngineService.is_market_hours", return_value=True):
            with patch("app.services.fyers_service.FyersService.fetch_ltp", return_value=2605.0): # Target hit
                await engine_svc._poll_missing_prices({"RELIANCE"})
                
        with TestingSessionLocal() as db:
            p = db.query(PaperPosition).filter_by(symbol="RELIANCE").first()
            assert p is None # Exited!

@pytest.mark.asyncio
async def test_9_exception_logging(isolated_db, caplog):
    TestingSessionLocal, engine = isolated_db
    
    with patch("app.services.market_engine_service.SessionLocal", TestingSessionLocal), \
         patch("app.services.market_engine_service.AsyncSessionLocal", TestingSessionLocal):
        engine_svc = MarketEngineService()
        
        with TestingSessionLocal() as db:
            account = db.query(PaperTradingAccount).first()
            pos = PaperPosition(
                account_id=account.id, symbol="ERRORCO", qty=10, avg_entry_price=100.0, 
                target=110.0, status="OPEN", lifecycle_state="OPEN_POSITION", monitor_enabled=True
            )
            db.add(pos)
            db.commit()

        # Force auto_exit to raise an error
        with patch("app.services.paper_trading_service.PaperTradingService.auto_exit", side_effect=ValueError("DB locked")):
            with caplog.at_level(logging.ERROR):
                await engine_svc._on_tick("NSE:ERRORCO-EQ", 115.0)
                
        assert "AUTO_EXIT_FAILED" in caplog.text
        assert "DB locked" in caplog.text
