from datetime import datetime, timedelta, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal

from backend.app.services.market_engine_service import MarketEngineService
from backend.app.models.paper_trading import PaperPosition

@pytest.fixture
def market_engine():
    engine = MarketEngineService()
    engine.fyers = MagicMock()
    engine.fyers.fetch_ohlcv = MagicMock()
    return engine

class MockCandle:
    def __init__(self, ts, h, l):
        self.timestamp = ts
        self.high = h
        self.low = l

@pytest.mark.asyncio
async def test_reconciliation_exit_recovery(market_engine):
    """
    TEST CATEGORY 1 — RECONCILIATION EXIT RECOVERY
    Verify exit logic (target/sl) is processed correctly during reconciliation.
    """
    t1 = datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc)
    
    pos = PaperPosition(
        id=1,
        symbol="TEST",
        status="OPEN",
        target=100,
        stop_loss=90,
        avg_entry_price=Decimal("95"),
        created_at=t1,
        last_evaluated_at=t1,
        last_reconciled_at=t1,
    )
    
    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=pos)
    mock_db.bind.dialect.name = "postgresql"
    
    with patch("app.services.market_engine_service.AsyncSessionLocal") as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_db
        
        # High hits target 100
        market_engine.fyers.fetch_ohlcv.return_value = [
            MockCandle(t1 + timedelta(minutes=1), 101, 95)
        ]
        
        with patch('app.services.market_engine_service.PaperTradingService') as mock_pts:
            mock_pts_instance = MagicMock()
            mock_pts.return_value = mock_pts_instance
            
            await market_engine._reconcile_ohlcv_sequence(1)
            
            # Verify exit triggered
            assert mock_db.run_sync.called
            args, kwargs = mock_db.run_sync.call_args
            assert args[1] == 1  # position_id
            assert args[2] == 101  # exit_price (high)
            assert args[3] == "TARGET_HIT"  # reason

@pytest.mark.asyncio
async def test_same_candle_conflict_resolution(market_engine):
    """
    TEST CATEGORY 2 — SAME CANDLE CONFLICT RESOLUTION
    If both target and SL hit on same candle, SL should win.
    """
    t1 = datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc)
    
    pos = PaperPosition(
        id=1,
        symbol="TEST",
        status="OPEN",
        target=100,
        stop_loss=90,
        avg_entry_price=Decimal("95"),
        created_at=t1,
        last_evaluated_at=t1,
        last_reconciled_at=t1,
    )
    
    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=pos)
    mock_db.bind.dialect.name = "postgresql"
    
    with patch("app.services.market_engine_service.AsyncSessionLocal") as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_db
        
        # High 101, Low 89 -> hits both!
        market_engine.fyers.fetch_ohlcv.return_value = [
            MockCandle(t1 + timedelta(minutes=1), 101, 89)
        ]
        
        with patch('app.services.market_engine_service.PaperTradingService') as mock_pts:
            mock_pts_instance = MagicMock()
            mock_pts.return_value = mock_pts_instance
            
            await market_engine._reconcile_ohlcv_sequence(1)
            
            assert mock_db.run_sync.called
            args, kwargs = mock_db.run_sync.call_args
            assert args[1] == 1
            assert args[2] == 89
            assert args[3] == "STOPLOSS_HIT"

@pytest.mark.asyncio
async def test_watermark_regression_protection(market_engine):
    """
    TEST CATEGORY 3 — WATERMARK REGRESSION PROTECTION
    Watermark must advance exactly to candle close time (timestamp + 1 min), not utcnow.
    """
    t1 = datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc)
    now = t1 + timedelta(minutes=10) # 10:10
    
    pos = PaperPosition(
        id=1,
        symbol="TEST",
        status="OPEN",
        created_at=t1,
        last_evaluated_at=t1,
        last_reconciled_at=t1,
    )
    
    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=pos)
    mock_db.bind.dialect.name = "postgresql"
    
    with patch("app.services.market_engine_service.AsyncSessionLocal") as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_db
        
        # FYERS returns up to 10:03
        c1 = t1 + timedelta(minutes=1) # 10:01
        c2 = t1 + timedelta(minutes=2) # 10:02
        c3 = t1 + timedelta(minutes=3) # 10:03
        market_engine.fyers.fetch_ohlcv.return_value = [
            MockCandle(c1, 100, 95),
            MockCandle(c2, 100, 95),
            MockCandle(c3, 100, 95)
        ]
        
        with patch('app.services.market_engine_service.datetime') as mock_dt:
            mock_dt.utcnow.return_value = now.replace(tzinfo=None)
            
            await market_engine._reconcile_ohlcv_sequence(1)
            
            assert pos.last_reconciled_at == c3 + timedelta(minutes=1)
            assert pos.last_reconciled_at != now

@pytest.mark.asyncio
async def test_partial_response_retry_safety(market_engine):
    """
    TEST CATEGORY 4 — PARTIAL RESPONSE RETRY SAFETY
    Ensure resuming after partial response continues perfectly.
    """
    t1 = datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc)
    
    pos = PaperPosition(
        id=1,
        symbol="TEST",
        status="OPEN",
        created_at=t1,
        last_evaluated_at=t1,
        last_reconciled_at=t1,
    )
    
    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=pos)
    mock_db.bind.dialect.name = "postgresql"
    
    with patch("app.services.market_engine_service.AsyncSessionLocal") as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_db
        
        c3 = t1 + timedelta(minutes=3)
        market_engine.fyers.fetch_ohlcv.return_value = [MockCandle(c3, 100, 95)]
        await market_engine._reconcile_ohlcv_sequence(1)
        
        assert pos.last_reconciled_at == c3 + timedelta(minutes=1)
        
        # Second sweep
        c6 = t1 + timedelta(minutes=6)
        market_engine.fyers.fetch_ohlcv.return_value = [MockCandle(c6, 100, 95)]
        await market_engine._reconcile_ohlcv_sequence(1)
        
        assert pos.last_reconciled_at == c6 + timedelta(minutes=1)

@pytest.mark.asyncio
async def test_empty_response_safety(market_engine):
    """
    TEST CATEGORY 5 — EMPTY RESPONSE SAFETY
    Ensure empty array from FYERS doesn't crash or blindly advance watermark.
    """
    t1 = datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc)
    
    pos = PaperPosition(
        id=1,
        symbol="TEST",
        status="OPEN",
        created_at=t1,
        last_evaluated_at=t1,
        last_reconciled_at=t1,
    )
    
    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=pos)
    mock_db.bind.dialect.name = "postgresql"
    
    with patch("app.services.market_engine_service.AsyncSessionLocal") as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_db
        
        market_engine.fyers.fetch_ohlcv.return_value = []
        await market_engine._reconcile_ohlcv_sequence(1)
        
        assert pos.last_reconciled_at == t1

@pytest.mark.asyncio
async def test_live_vs_reconciliation_race(market_engine):
    """
    TEST CATEGORY 6 — LIVE VS RECONCILIATION RACE
    Simulate live event and historical target hit at the same time.
    Relies on dedupe DB logic via ExecutionEvent which is implemented inside PaperTradingService.
    Here we test that the historical engine handles exceptions (like IntegrityError) gracefully.
    """
    t1 = datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc)
    pos = PaperPosition(
        id=1, symbol="TEST", status="OPEN", target=100, avg_entry_price=Decimal("95"),
        created_at=t1, last_evaluated_at=t1, last_reconciled_at=t1
    )
    
    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=pos)
    mock_db.bind.dialect.name = "postgresql"
    
    with patch("app.services.market_engine_service.AsyncSessionLocal") as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_db
        market_engine.fyers.fetch_ohlcv.return_value = [MockCandle(t1 + timedelta(minutes=1), 101, 95)]
        
        # We patch PaperTradingService run_sync to raise an Exception representing the race duplicate key
        import sqlalchemy.exc
        mock_db.run_sync.side_effect = sqlalchemy.exc.IntegrityError("duplicate key", params={}, orig=Exception())
        
        # It should catch it and continue without crashing the sequence
        await market_engine._reconcile_ohlcv_sequence(1)
        assert mock_db.run_sync.called
        assert pos.last_reconciled_at is not None

@pytest.mark.asyncio
async def test_long_outage_recovery(market_engine):
    """
    TEST CATEGORY 7 — LONG OUTAGE RECOVERY
    """
    t1 = datetime(2023, 1, 1, 9, 15, tzinfo=timezone.utc)
    pos = PaperPosition(
        id=1,
        symbol="TEST",
        status="OPEN",
        created_at=t1,
        last_evaluated_at=t1,
        last_reconciled_at=t1,
    )
    
    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=pos)
    mock_db.bind.dialect.name = "postgresql"
    
    # 100 days outage
    c1 = t1 + timedelta(days=100)
    
    with patch("app.services.market_engine_service.AsyncSessionLocal") as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_db
        market_engine.fyers.fetch_ohlcv.return_value = [MockCandle(c1, 100, 95)]
        
        await market_engine._reconcile_ohlcv_sequence(1)
        assert pos.last_reconciled_at == c1 + timedelta(minutes=1)
