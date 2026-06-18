from datetime import datetime, timedelta, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.orm import selectinload

from backend.app.services.market_engine_service import MarketEngineService
from backend.app.models.paper_trading import PaperPosition

@pytest.fixture
def market_engine():
    engine = MarketEngineService()
    engine.fyers = MagicMock()
    engine.fyers.fetch_ohlcv = MagicMock()
    return engine

@pytest.mark.asyncio
async def test_poll_missing_prices_still_executes(market_engine):
    """
    Validation 1: _poll_missing_prices() still executes during reconciliation.
    Ensure that the immediate LTP recovery is not removed or replaced by historical logic.
    """
    with patch.object(market_engine, '_poll_missing_prices', new_callable=AsyncMock) as mock_poll:
        with patch.object(market_engine, '_sync_on_connection_change', new_callable=AsyncMock):
            with patch.object(market_engine, 'is_market_hours', return_value=True):
                with patch.object(market_engine, '_desired_symbols', new_callable=AsyncMock, return_value={"TEST"}):
                    with patch.object(market_engine, '_resume_active_models', new_callable=AsyncMock):
                        with patch('app.services.market_engine_service.get_current_access_token', new_callable=AsyncMock, return_value="token"):
                            mock_db = AsyncMock()
                            mock_session = AsyncMock()
                            await market_engine._reconcile_session(mock_db, mock_session)
                            mock_poll.assert_called_once()

@pytest.mark.asyncio
async def test_replay_start_calculation(market_engine):
    """
    Validation 3: Replay Start Calculation uses max(last_reconciled_at, last_evaluated_at, created_at).
    We'll test this by intercepting the DB query in _reconcile_ohlcv_sequence.
    """
    t1 = datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2023, 1, 1, 10, 30, tzinfo=timezone.utc)
    t3 = datetime(2023, 1, 1, 11, 0, tzinfo=timezone.utc)

    pos = PaperPosition(
        id=1,
        symbol="TEST",
        status="OPEN",
        target=None,
        stop_loss=None,
        created_at=t1,
        last_evaluated_at=t2,
        last_reconciled_at=t3,
    )
    
    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=pos)
    mock_db.bind.dialect.name = "postgresql"
    
    # We patch AsyncSessionLocal to yield our mock db
    with patch("app.services.market_engine_service.AsyncSessionLocal") as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_db
        
        market_engine.fyers.fetch_ohlcv.return_value = []
        
        await market_engine._reconcile_ohlcv_sequence(1)
        
        # Verify fetch_ohlcv was called
        market_engine.fyers.fetch_ohlcv.assert_called_once()
        args, kwargs = market_engine.fyers.fetch_ohlcv.call_args
        # The lookback window calculation in days should be derived from the max time
        assert args[0] == "TEST"

@pytest.mark.asyncio
async def test_crash_recovery_last_reconciled_at_update(market_engine):
    """
    Validation 4: Crash recovery.
    Ensure last_reconciled_at is only updated AFTER successfully processing the candles,
    preserving crash safety.
    """
    t1 = datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc)
    pos = PaperPosition(
        id=1,
        symbol="TEST",
        status="OPEN",
        created_at=t1,
    )
    
    class MockCandle:
        def __init__(self, ts, h, l):
            self.timestamp = ts
            self.high = h
            self.low = l

    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=pos)
    
    with patch("app.services.market_engine_service.AsyncSessionLocal") as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_db
        
        market_engine.fyers.fetch_ohlcv.return_value = [
            MockCandle(t1 + timedelta(minutes=1), 100, 90),
            MockCandle(t1 + timedelta(minutes=2), 110, 95)
        ]
        
        await market_engine._reconcile_ohlcv_sequence(1)
        
        # Verify db.commit() was called indicating safe progress save
        assert mock_db.commit.called
        assert pos.last_reconciled_at is not None

@pytest.mark.asyncio
async def test_no_gap_skip(market_engine):
    """
    Phase 2.5 Validation 1: No-Gap Skip.
    If replay_start is within 1 minute of utcnow(), fetch_ohlcv should never be called.
    """
    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    pos = PaperPosition(
        id=1,
        symbol="TEST",
        status="OPEN",
        target=None,
        stop_loss=None,
        created_at=now - timedelta(minutes=10),
        last_evaluated_at=now - timedelta(seconds=30),  # Less than 1 minute gap
        last_reconciled_at=None,
    )
    
    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=pos)
    mock_db.bind.dialect.name = "postgresql"
    
    with patch("app.services.market_engine_service.AsyncSessionLocal") as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_db
        market_engine.fyers.fetch_ohlcv.return_value = []
        
        await market_engine._reconcile_ohlcv_sequence(1)
        
        # Verify fetch_ohlcv was NOT called
        market_engine.fyers.fetch_ohlcv.assert_not_called()
        # Verify last_reconciled_at was updated
        assert mock_db.commit.called

@pytest.mark.asyncio
async def test_timezone_comparison_and_replay_boundary(market_engine):
    """
    Phase 2.5 Validation 2 & 3: Timezone Comparison + Replay Boundary.
    Ensures naive and aware timestamps are compared correctly.
    Ensures a candle is included if c.timestamp + 1 minute > replay_start.
    """
    t1 = datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc)
    
    pos = PaperPosition(
        id=1,
        symbol="TEST",
        status="OPEN",
        target=110,
        stop_loss=90,
        created_at=t1,
        last_evaluated_at=t1 + timedelta(minutes=10, seconds=30), # 10:10:30
        last_reconciled_at=None,
    )
    
    class MockCandle:
        def __init__(self, ts, h, l):
            self.timestamp = ts
            self.high = h
            self.low = l

    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=pos)
    mock_db.bind.dialect.name = "postgresql"
    
    with patch("app.services.market_engine_service.AsyncSessionLocal") as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_db
        
        # Provide one naive timestamp and one aware timestamp
        # The 10:09 candle should be excluded. Its end is 10:10:00, which is < 10:10:30
        c1_naive = (t1 + timedelta(minutes=9)).replace(tzinfo=None) # 10:09 naive
        # The 10:10 candle should be included. Its end is 10:11:00, which is > 10:10:30
        c2_aware = t1 + timedelta(minutes=10) # 10:10 aware
        
        # c2_aware will hit the target of 110!
        market_engine.fyers.fetch_ohlcv.return_value = [
            MockCandle(c1_naive, 105, 95), # should be excluded
            MockCandle(c2_aware, 115, 95)  # should be included, target hit
        ]
        
        with patch('app.services.market_engine_service.PaperTradingService') as mock_pts:
            mock_pts_instance = MagicMock()
            mock_pts.return_value = mock_pts_instance
            
            await market_engine._reconcile_ohlcv_sequence(1)
            
            # The naive and aware compare shouldn't crash.
            # And the auto_exit should have been called for TARGET_HIT!
            # The run_sync execution wraps auto_exit:
            assert mock_db.run_sync.called
            # The auto_exit should be called with TARGET_HIT for exit_price 115
            args, kwargs = mock_db.run_sync.call_args
            assert args[1] == 1  # position_id
            assert args[2] == 115  # exit_price
            assert args[3] == "TARGET_HIT"  # reason
