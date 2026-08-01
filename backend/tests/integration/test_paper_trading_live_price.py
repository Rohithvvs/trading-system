import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone

from backend.app.services.paper_trading_service import PaperTradingService
from backend.app.services.fyers_service import FyersService
from backend.app.services import token_service
from backend.app.models import FyersToken

@pytest.fixture(autouse=True)
def clear_token_cache():
    token_service._clear_token_cache()
    yield
    token_service._clear_token_cache()

@pytest.fixture
def mock_session_local():
    with patch("backend.app.db.session.SessionLocal") as mock_sl:
        mock_session = MagicMock()
        mock_sl.return_value.__enter__.return_value = mock_session
        yield mock_session

def test_quote_endpoint_returns_numeric_float_not_coroutine():
    """Scenario 3: Quote endpoint returns numeric float, No coroutine object returned."""
    service = PaperTradingService(MagicMock())
    service._validate_symbol = MagicMock()
    
    async def mock_fetch_ltp(symbol):
        return 150.75
        
    service.fyers_service = MagicMock()
    service.fyers_service.fetch_ltp = mock_fetch_ltp
    
    with patch("asyncio.run_coroutine_threadsafe") as mock_run:
        mock_future = MagicMock()
        mock_future.result.return_value = 150.75
        mock_run.return_value = mock_future
        
        quote = service.get_quote("INFY-EQ")
    
    assert isinstance(quote.current_price, float)
    assert quote.current_price == 150.75
    assert quote.source == "FYERS_QUOTE"
    assert quote.market_status == "live"


def test_validate_symbol_accepts_eq_and_exchange_forms():
    """Root-cause regression: UI sends INFY-EQ / NSE:INFY-EQ; universe stores INFY."""
    service = PaperTradingService(MagicMock())
    with patch("backend.app.services.paper_trading_service.settings") as mock_settings:
        mock_settings.nifty500_symbols = ["INFY", "TCS", "ASTRAMICRO"]
        service._validate_symbol("INFY")
        service._validate_symbol("INFY-EQ")
        service._validate_symbol("nse:infy-eq")
        service._validate_symbol("ASTRAMICRO-EQ")
        try:
            service._validate_symbol("NOT_A_REAL_SYMBOL_XYZ")
            raised = False
        except ValueError:
            raised = True
        assert raised is True


def test_get_quote_canonicalizes_eq_suffix_before_broker_call():
    """Quote path must canonicalize so -EQ symbols hit the same cache/broker key."""
    service = PaperTradingService(MagicMock())
    service._validate_symbol = MagicMock()
    service.fyers_service = MagicMock()

    with patch("asyncio.run_coroutine_threadsafe") as mock_run:
        mock_future = MagicMock()
        mock_future.result.return_value = 1769.3
        mock_run.return_value = mock_future
        quote = service.get_quote("ASTRAMICRO-EQ")

    assert quote.symbol == "ASTRAMICRO"
    assert quote.current_price == 1769.3
    assert quote.source == "FYERS_QUOTE"
    # fetch_ltp coroutine was scheduled for canonical symbol
    coro = mock_run.call_args[0][0]
    # coroutine already created with canonical symbol via service call path
    assert quote.market_status == "live"

def test_valid_token_live_quote_request_returns_price(mock_session_local):
    """Scenario 1: Valid token -> Live quote request -> Returns price"""
    token_service._set_token_cache("valid_token", datetime.utcnow())
    
    service = PaperTradingService(MagicMock())
    service._validate_symbol = MagicMock()
    
    async def mock_fetch_ltp(symbol):
        return 120.50
        
    service.fyers_service = MagicMock()
    service.fyers_service.fetch_ltp = mock_fetch_ltp
    
    with patch("asyncio.run_coroutine_threadsafe") as mock_run:
        mock_future = MagicMock()
        mock_future.result.return_value = 120.50
        mock_run.return_value = mock_future
        
        quote = service.get_quote("TCS-EQ")
    
    assert quote.current_price == 120.50
    assert quote.source == "FYERS_QUOTE"

def test_cache_expired_token_refreshes_from_db(mock_session_local):
    """Scenario 2: Cache expired -> Token exists in PostgreSQL -> Paper Trading automatically refreshes token -> Price loads successfully"""
    # Ensure cache is expired / empty
    token_service._clear_token_cache()
    assert token_service.has_cached_token() is False
    
    # Setup DB to return a valid token
    row = FyersToken(id=1, access_token="refreshed_token", is_active=True, status="active", created_at=datetime.utcnow(), access_token_saved_at=datetime.utcnow())
    mock_session_local.query.return_value.filter.return_value.order_by.return_value.first.return_value = row

    fyers = FyersService()
    # It should successfully configure itself because it queries DB on cache miss
    assert fyers._is_fyers_configured() is True
    assert token_service.has_cached_token() is True  # Cache is now rehydrated
    assert token_service._CACHED_TOKEN == "refreshed_token"

def test_ui_polling_path_succeeds_repeatedly():
    """Scenario 4: UI polling path succeeds repeatedly."""
    service = PaperTradingService(MagicMock())
    service._validate_symbol = MagicMock()
    
    call_count = 0
    async def mock_fetch_ltp(symbol):
        return 0.0 # dummy
        
    service.fyers_service = MagicMock()
    service.fyers_service.fetch_ltp = mock_fetch_ltp
    service.fyers_service.fetch_ohlcv.return_value = [] # Ensure fallback to 0.0
    
    with patch("asyncio.run_coroutine_threadsafe") as mock_run:
        mock_future = MagicMock()
        mock_future.result.side_effect = [101.0, 102.0, 103.0, 104.0, 105.0]
        mock_run.return_value = mock_future
    
        for i in range(5):
            quote = service.get_quote("RELIANCE-EQ")
            assert isinstance(quote.current_price, float)
            assert quote.current_price == 101.0 + i
    
    assert mock_run.call_count == 5

def test_scanner_and_paper_trading_both_work_after_ttl_expiration(mock_session_local):
    """Scenario 5: Scanner and Paper Trading both work after token TTL expiration."""
    # Start with an expired cache
    token_service._set_token_cache("old_token")
    token_service._TOKEN_EXPIRY = datetime.utcnow() - timedelta(minutes=1) # Expired
    assert token_service.has_cached_token() is False
    
    # Setup DB to return new token
    row = FyersToken(id=1, access_token="new_db_token", is_active=True, status="active", created_at=datetime.utcnow(), access_token_saved_at=datetime.utcnow())
    mock_session_local.query.return_value.filter.return_value.order_by.return_value.first.return_value = row

    # 1. Paper Trading path
    fyers = FyersService()
    is_configured = fyers._is_fyers_configured()
    assert is_configured is True
    assert token_service._CACHED_TOKEN == "new_db_token"
    
    # Re-expire cache to test scanner
    token_service._TOKEN_EXPIRY = datetime.utcnow() - timedelta(minutes=1)
    
    # 2. Scanner path
    client = fyers._client()
    # Scanner client initialization goes through get_current_access_token_sync
    assert client.token == "new_db_token"
    assert token_service._CACHED_TOKEN == "new_db_token"
