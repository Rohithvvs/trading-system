import pytest
import asyncio
import os
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.deps import SYSTEM_OWNER_ID
from app.models.paper_trading import Base, PaperTradingAccount, PaperOrder, PaperPosition
from app.services.paper_trading_service import PaperTradingService
from app.schemas.paper_trading import PaperOrderCreateRequest

# Use a real sqlite file to properly test locking/contention (WAL mode enabled via connect_args typically, but SQLite does default file locking here)
test_db_path = os.path.join(tempfile.gettempdir(), "test_trading_execution.db")

if os.path.exists(test_db_path):
    os.remove(test_db_path)

engine = create_engine(
    f"sqlite:///{test_db_path}", connect_args={"check_same_thread": False, "timeout": 15}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

from app.models.paper_trading import Base
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
SQLiteTypeCompiler.visit_JSONB = lambda self, type_, **kw: "JSON"  # type: ignore[method-assign]
SQLiteTypeCompiler.visit_UUID = lambda self, type_, **kw: "CHAR(36)"  # type: ignore[method-assign]
Base.metadata.create_all(bind=engine)


def _owner_service(db) -> PaperTradingService:
    """Paper routes always inject SYSTEM_OWNER_ID; tests must match single-owner mode."""
    return PaperTradingService(db, user_id=SYSTEM_OWNER_ID)


@pytest.fixture(autouse=True)
def setup_db():
    with TestingSessionLocal() as db:
        # Cleanup
        db.query(PaperOrder).delete()
        db.query(PaperPosition).delete()
        db.query(PaperTradingAccount).delete()
        db.commit()

        # Seed primary owner account (026 single-owner context)
        account = PaperTradingAccount(
            user_id=SYSTEM_OWNER_ID,
            name="Test Account",
            starting_balance=Decimal("1000000.00"),
            cash_balance=Decimal("1000000.00"),
            max_risk_per_trade=Decimal("0.02"),
        )
        db.add(account)
        db.commit()

        yield

        db.query(PaperOrder).delete()
        db.query(PaperPosition).delete()
        db.query(PaperTradingAccount).delete()
        db.commit()

@pytest.mark.concurrency
@pytest.mark.asyncio
async def test_concurrent_duplicate_order_prevention():
    """
    Spawns multiple threads trying to place the exact same order idempotency key.
    Validates exactly one succeeds, exactly one balance deduction occurs.
    """
    # Create barrier to ensure all tasks fire at the EXACT same time
    barrier = asyncio.Barrier(5)
    
    async def place_concurrent_order():
        await barrier.wait()
        
        # We need independent sessions per thread to simulate real requests
        with TestingSessionLocal() as db:
            service = _owner_service(db)
            # Mock price snapshot since we don't have FYERS configured
            with patch.object(service, "_price_snapshot") as mock_price:
                class DummyPrice:
                    symbol = "INFY-EQ"
                    current_price = 100.0
                    candles = []
                    ema_20 = None
                    supertrend = None
                    source = "FYERS_QUOTE"
                    fetched_at = datetime.now(timezone.utc)
                mock_price.return_value = DummyPrice()
                
                payload = PaperOrderCreateRequest(
                    symbol="INFY-EQ",
                    side="BUY",
                    type="MARKET",
                    qty=10, # Total cost = 1000.0
                    idempotency_key="UNIQUE_SIGNAL_12345"
                )
                try:
                    # Run the sync DB logic in a thread
                    return await asyncio.to_thread(service.place_order, payload)
                except Exception as e:
                    return e

    # Fire 5 tasks concurrently
    tasks = [asyncio.create_task(place_concurrent_order()) for _ in range(5)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for r in results:
        if isinstance(r, Exception):
            raise r
    
    # Assert DB state
    with TestingSessionLocal() as db:
        orders = db.query(PaperOrder).filter_by(idempotency_key="UNIQUE_SIGNAL_12345").all()
        # Due to idempotency key and DB locks, only 1 order should exist
        assert len(orders) == 1
        
        # Symbol may be normalized (e.g. INFY-EQ → INFY) depending on service rules.
        positions = db.query(PaperPosition).all()
        assert len(positions) == 1
        assert positions[0].qty == 10
        assert "INFY" in (positions[0].symbol or "").upper()
        
        account = db.query(PaperTradingAccount).first()
        # 1000000 - 1000 = 999000
        assert float(account.cash_balance) == 999000.0

@pytest.mark.asyncio
async def test_order_rollback_on_failure():
    """
    Injects a failure mid-transaction (e.g. during position creation).
    Asserts account balance is not deducted and order is rolled back.
    """
    with TestingSessionLocal() as db:
        service = _owner_service(db)
        
        payload = PaperOrderCreateRequest(
            symbol="TCS-EQ",
            side="BUY",
            type="MARKET",
            qty=5, 
            idempotency_key="FAIL_ME_1234567890"
        )
        
        # Mock price to work, but mock flush to raise an exception 
        # to simulate partial DB failure after order creation but before commit
        with patch.object(service, "_price_snapshot") as mock_price:
            class DummyPrice:
                symbol = "TCS-EQ"
                current_price = 100.0
                candles = []
                ema_20 = None
                supertrend = None
                source = "FYERS_QUOTE"
                fetched_at = datetime.now(timezone.utc)
            mock_price.return_value = DummyPrice()
            
            with patch.object(service.db, "commit", side_effect=Exception("Simulated DB Crash!")):
                with pytest.raises(Exception, match="Simulated DB Crash!"):
                    await asyncio.to_thread(service.place_order, payload)

    # Validate DB state remained entirely untouched
    with TestingSessionLocal() as db:
        account = db.query(PaperTradingAccount).first()
        assert float(account.cash_balance) == 1000000.0  # No money lost
        
        orders = db.query(PaperOrder).all()
        assert len(orders) == 0  # Order rolled back
        
        positions = db.query(PaperPosition).all()
        assert len(positions) == 0  # No position

@pytest.mark.asyncio
async def test_risk_management_limits():
    """
    Asserts orders that exceed cash limits are rejected, balance untouched, and logged.
    """
    with TestingSessionLocal() as db:
        service = _owner_service(db)
        
        payload = PaperOrderCreateRequest(
            symbol="RELIANCE-EQ",
            side="BUY",
            type="MARKET",
            qty=20000, # 20000 * 100 = 2,000,000 (exceeds 1,000,000 balance)
            idempotency_key="BIG_RISK_123456789"
        )
        
        with patch.object(service, "_price_snapshot") as mock_price:
            class DummyPrice:
                symbol = "RELIANCE-EQ"
                current_price = 100.0
                candles = []
                ema_20 = None
                supertrend = None
                source = "FYERS_QUOTE"
                fetched_at = datetime.now(timezone.utc)
            mock_price.return_value = DummyPrice()
            
            with patch("app.services.paper_trading_service.trading_logger") as mock_logger:
                result = await asyncio.to_thread(service.place_order, payload)
                
                assert result.order.status == "REJECTED"
                assert "insufficient available cash" in result.message.lower()
                
                # Verify observability was triggered
                mock_logger.warning.assert_called()
                call_args = mock_logger.warning.call_args[0]
                assert "ORDER_REJECTED" in call_args[0]
                assert "INSUFFICIENT_CASH" in call_args[0]

    # Verify no funds deducted and no position created
    with TestingSessionLocal() as db:
        account = db.query(PaperTradingAccount).first()
        assert float(account.cash_balance) == 1000000.0
        
        positions = db.query(PaperPosition).all()
        assert len(positions) == 0
