import pytest
import threading
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from backend.app.models import FyersToken
from backend.app.services.fyers_service import FyersService, FyersAuthInvalidError, FyersAuthExpiredError, _check_fyers_response
from backend.app.services import token_service

@pytest.fixture(autouse=True)
def clear_token_cache():
    token_service._clear_token_cache()
    yield
    token_service._clear_token_cache()

@pytest.fixture
def fyers_service_mock():
    with patch("backend.app.services.fyers_service.FyersService.validate_token_sync") as mock_validate:
        yield mock_validate

@pytest.fixture
def mock_session_local():
    with patch("backend.app.db.session.SessionLocal") as mock_sl:
        mock_session = MagicMock()
        mock_sl.return_value.__enter__.return_value = mock_session
        yield mock_session

def test_startup_token_load_and_scanner_access(mock_session_local):
    token_service._clear_token_cache()
    
    row = FyersToken(id=1, access_token="startup_token", is_active=True, status="active", created_at=datetime.utcnow(), access_token_saved_at=datetime.utcnow())
    mock_session_local.query.return_value.filter.return_value.order_by.return_value.first.return_value = row
    
    service = FyersService()
    with patch("backend.app.services.fyers_service.fyersModel.FyersModel") as mock_model:
        client = service._client()
        assert mock_model.call_args[1]["token"] == "startup_token"
    assert token_service._CACHED_TOKEN == "startup_token"

def test_cache_miss_storm(mock_session_local):
    token_service._clear_token_cache()
    
    row = FyersToken(id=1, access_token="storm_token", is_active=True, status="active", created_at=datetime.utcnow(), access_token_saved_at=datetime.utcnow())
    mock_session_local.query.return_value.filter.return_value.order_by.return_value.first.return_value = row
    
    # Track how many times the DB was queried
    db_query_count = 0
    original_first = mock_session_local.query.return_value.filter.return_value.order_by.return_value.first
    def mock_first():
        nonlocal db_query_count
        db_query_count += 1
        return row
    mock_session_local.query.return_value.filter.return_value.order_by.return_value.first.side_effect = mock_first
    
    results = []
    with patch("backend.app.services.fyers_service.fyersModel.FyersModel") as mock_model:
        def worker():
            service = FyersService()
            try:
                client = service._client()
                # We can't safely extract call_args from a single mock called 100 times concurrently in a reliable way for index matching, 
                # but we can just append the token we passed to _set_token_cache or just check the cache!
                results.append(token_service._CACHED_TOKEN)
            except Exception as e:
                results.append(e)

        threads = [threading.Thread(target=worker) for _ in range(100)]
    for t in threads: t.start()
    for t in threads: t.join()
    
    assert len(results) == 100, f"Expected 100 results, got {len(results)}. Results: {results}"
    assert all(r == "storm_token" for r in results), f"Expected 'storm_token' for all, got {results}"
    assert db_query_count == 1, f"Expected 1 DB query, got {db_query_count}"

def test_auth_failure_invalidation(mock_session_local):
    token_service._set_token_cache("invalid_token")
    
    # Simulate API response failing
    response = {"s": "error", "code": -15, "message": "invalid token"}
    with pytest.raises(FyersAuthInvalidError):
        _check_fyers_response(response, "NSE:NIFTY50-INDEX")
        
    # The cache should be explicitly cleared!
    assert token_service._CACHED_TOKEN is None
    
    # The NEXT call should hit the DB!
    row = FyersToken(id=1, access_token="new_valid_token", is_active=True, status="active", created_at=datetime.utcnow(), access_token_saved_at=datetime.utcnow())
    mock_session_local.query.return_value.filter.return_value.order_by.return_value.first.return_value = row
    
    service = FyersService()
    with patch("backend.app.services.fyers_service.fyersModel.FyersModel") as mock_model:
        client = service._client()
        assert mock_model.call_args[1]["token"] == "new_valid_token"

def test_token_generation_mismatch(mock_session_local):
    now = datetime.utcnow()
    token_service._set_token_cache("old_token", saved_at=now)
    
    # Suppose a cache check occurs (e.g. cache expired)
    token_service._TOKEN_EXPIRY = now - timedelta(minutes=1)
    
    row = FyersToken(id=1, access_token="new_rotated_token", is_active=True, status="active", created_at=now, access_token_saved_at=now + timedelta(minutes=5))
    mock_session_local.query.return_value.filter.return_value.order_by.return_value.first.return_value = row
    
    service = FyersService()
    with patch("backend.app.services.fyers_service.fyersModel.FyersModel") as mock_model:
        client = service._client()
        assert mock_model.call_args[1]["token"] == "new_rotated_token"

def test_db_unavailable_fallback(mock_session_local):
    token_service._set_token_cache("fallback_token")
    token_service._TOKEN_EXPIRY = datetime.utcnow() - timedelta(minutes=1) # force refresh
    
    mock_session_local.query.side_effect = Exception("DB Connection Lost")
    
    service = FyersService()
    with patch("backend.app.services.fyers_service.fyersModel.FyersModel") as mock_model:
        client = service._client()
        assert mock_model.call_args[1]["token"] == "fallback_token"

def test_db_unavailable_no_fallback(mock_session_local):
    token_service._clear_token_cache()
    mock_session_local.query.side_effect = Exception("DB Connection Lost")
    
    service = FyersService()
    with pytest.raises(FyersAuthInvalidError):
        service._client()

def test_scenario_token_rotation_without_restart(mock_session_local):
    """
    User saves Token A.
    Scanner uses Token A.
    Token A expires.
    User saves Token B.
    Scanner successfully switches to Token B without restart.
    """
    token_service._clear_token_cache()
    
    # 1. User saves Token A
    token_a_row = FyersToken(id=1, access_token="Token_A", is_active=True, status="active", created_at=datetime.utcnow())
    mock_session_local.query.return_value.filter.return_value.order_by.return_value.first.return_value = token_a_row
    
    # 2. Scanner uses Token A
    service = FyersService()
    with patch("backend.app.services.fyers_service.fyersModel.FyersModel") as mock_model:
        service._client()
        assert mock_model.call_args[1]["token"] == "Token_A"
        
    assert token_service._CACHED_TOKEN == "Token_A"
    
    # 3. Token A expires / invalid
    response = {"s": "error", "code": -15, "message": "invalid token"}
    with pytest.raises(FyersAuthInvalidError):
        _check_fyers_response(response, "NSE:NIFTY50-INDEX")
    assert token_service._CACHED_TOKEN is None
    
    # 4. User saves Token B
    token_b_row = FyersToken(id=2, access_token="Token_B", is_active=True, status="active", created_at=datetime.utcnow())
    mock_session_local.query.return_value.filter.return_value.order_by.return_value.first.return_value = token_b_row
    
    # 5. Scanner successfully switches to Token B without restart
    with patch("backend.app.services.fyers_service.fyersModel.FyersModel") as mock_model:
        service._client()
        assert mock_model.call_args[1]["token"] == "Token_B"
        
def test_scenario_cache_invalidated_storm_one_db_query(mock_session_local):
    """
    100 scanner threads.
    Invalid token.
    Cache invalidated.
    Only one DB reload occurs.
    """
    token_service._set_token_cache("invalid_token")
    
    # Invalidate cache
    response = {"s": "error", "code": -15, "message": "invalid token"}
    with pytest.raises(FyersAuthInvalidError):
        _check_fyers_response(response, "NSE:NIFTY50-INDEX")
    assert token_service._CACHED_TOKEN is None
    
    # Set DB to return new token
    db_query_count = 0
    row = FyersToken(id=1, access_token="new_valid_token", is_active=True, status="active", created_at=datetime.utcnow())
    def mock_first():
        nonlocal db_query_count
        db_query_count += 1
        return row
    mock_session_local.query.return_value.filter.return_value.order_by.return_value.first.side_effect = mock_first
    
    # 100 scanner threads
    results = []
    with patch("backend.app.services.fyers_service.fyersModel.FyersModel"):
        def worker():
            service = FyersService()
            try:
                service._client()
                results.append(token_service._CACHED_TOKEN)
            except Exception as e:
                results.append(e)

        threads = [threading.Thread(target=worker) for _ in range(100)]
        for t in threads: t.start()
        for t in threads: t.join()
        
    assert len(results) == 100
    assert all(r == "new_valid_token" for r in results)
    assert db_query_count == 1

def test_scenario_db_unavailable_invalid_cache_fails_fast(mock_session_local):
    """
    DB unavailable.
    Invalid cached token.
    Scanner fails fast.
    No retry storm.
    """
    # Invalid token
    token_service._set_token_cache("invalid_token")
    response = {"s": "error", "code": -15, "message": "invalid token"}
    with pytest.raises(FyersAuthInvalidError):
        _check_fyers_response(response, "NSE:NIFTY50-INDEX")
    
    assert token_service._CACHED_TOKEN is None
    
    # DB unavailable
    mock_session_local.query.side_effect = Exception("DB Connection Lost")
    
    service = FyersService()
    
    # Scanner fails fast (will raise FyersAuthInvalidError because DB failed and no cached token)
    with pytest.raises(FyersAuthInvalidError, match="No FYERS access token configured"):
        service._client()

