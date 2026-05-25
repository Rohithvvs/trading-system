from datetime import datetime
from unittest.mock import patch

from backend.app.services.fyers_service import FyersRateLimitError, FyersAuthExpiredError
from backend.app.services.screener_service import ScreenerService
from backend.app.services.market_engine_service import MarketEngineService, MarketEngineSession
from backend.app.schemas.analysis import ScreenerConditionResult


import pytest

@pytest.mark.skip(reason="Legacy test: Backoff logic was moved to TokenBucketRateLimiter and FyersService network boundary")
def test_fyers_429_rate_limit_backoff():
    """
    Mock the FYERS API returning an HTTP 429 (Too Many Requests). Assert
    that the `_process_symbol_safe` applies an exponential backoff sleep
    (using mocked time) and retries successfully.
    """
    service = ScreenerService()
    
    with patch("backend.app.services.screener_service.time.sleep") as mock_sleep, \
         patch.object(service, "_process_single_symbol") as mock_process:
        
        # Make the first two attempts fail with 429, and the third succeed
        mock_process.side_effect = [
            FyersRateLimitError("Too Many Requests"),
            FyersRateLimitError("Too Many Requests"),
            ScreenerConditionResult(
                symbol="RELIANCE", close=2500.0, ema_20=2400.0, sma_30=2410.0,
                sma_50=2420.0, sma_100=2430.0, sma_200=2440.0, macd=10.0,
                macd_signal=5.0, supertrend=2400.0, volume=100000,
                previous_volume=90000, screener_score=80.0, technical_signal="buy",
                technical_score=80.0, conditions={"ema_cross": True}, matched=True
            )
        ]
        
        result = service._process_single_symbol("RELIANCE", 100, "technical")
        
        # Assert the success result was eventually returned
        assert result.symbol == "RELIANCE"
        assert result.close == 2500.0
        
        # Assert _process_single_symbol was called 3 times
        assert mock_process.call_count == 3
        
        # Assert time.sleep was called with exponential backoff
        # attempt 0 -> wait = 2.0 ** 0 = 1.0
        # attempt 1 -> wait = 2.0 ** 1 = 2.0
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1.0)
        mock_sleep.assert_any_call(2.0)


def test_token_expiry_graceful_pause(db_session):
    """
    Mock an HTTP 401 (Unauthorized/Expired Token) during a background scan loop.
    Assert that the engine marks the token status as 'inactive', logs a critical
    warning, and gracefully pauses the loop rather than firing an infinite loop
    of failed requests.
    """
    engine = MarketEngineService()
    
    # Create a dummy session
    engine_session = MarketEngineSession(
        trading_date=datetime.utcnow().date(),
        status="RUNNING",
        token_status="VALID"
    )
    db_session.add(engine_session)
    db_session.commit()
    
    with patch.object(engine, "_desired_symbols", return_value={"INFY"}), \
         patch.object(engine, "_poll_missing_prices", side_effect=FyersAuthExpiredError("Unauthorized")), \
         patch.object(engine, "_set_market_closed_waiting"), \
         patch.object(engine, "is_market_hours", return_value=True):
        
        # Trigger the reconcile which runs the _poll_missing_prices and should catch the auth error
        import asyncio
        asyncio.run(engine._reconcile_session(db_session, engine_session))
        
        # Assert the session was paused gracefully
        assert engine_session.status == "PAUSED_TOKEN_EXPIRED"
        assert engine_session.token_status == "EXPIRED"
        assert engine_session.paused_reason == "TOKEN_EXPIRED"
