import pytest
from backend.app.services.fyers_service import (
    _check_fyers_response,
    FyersAuthExpiredError,
    FyersAuthInvalidError,
    FyersRateLimitError,
    FyersAPIError
)

def test_fyers_contract_auth_expired():
    """Test FYERS strict contract for token expiration (-16)"""
    payload_code = {"s": "error", "code": -16, "message": "token expired"}
    payload_msg = {"s": "error", "code": 500, "message": "Auth token has Expired."}
    
    with pytest.raises(FyersAuthExpiredError):
        _check_fyers_response(payload_code)
        
    with pytest.raises(FyersAuthExpiredError):
        _check_fyers_response(payload_msg)

def test_fyers_contract_auth_invalid():
    """Test FYERS strict contract for invalid token (-15)"""
    payload = {"s": "error", "code": -15, "message": "invalid token provided"}
    
    with pytest.raises(FyersAuthInvalidError):
        _check_fyers_response(payload)

def test_fyers_contract_rate_limit():
    """Test FYERS strict contract for rate limits (429)"""
    payload = {"s": "error", "code": 429, "message": "Too many requests. Limit exceeded."}
    
    with pytest.raises(FyersRateLimitError):
        _check_fyers_response(payload)

def test_fyers_contract_generic_error():
    """Test generic API errors"""
    payload = {"s": "error", "code": -99, "message": "System failure"}
    
    with pytest.raises(FyersAPIError) as exc:
        _check_fyers_response(payload, symbol="NSE:RELIANCE-EQ")
        
    assert "code=-99" in str(exc.value)

def test_fyers_contract_success():
    """Test FYERS successful contract"""
    payload = {"s": "ok", "code": 200, "message": "Success"}
    
    # Should not raise any exception
    _check_fyers_response(payload)
