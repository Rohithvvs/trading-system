import pytest
from backend.app.services.token_service import _mask_token

def test_security_sql_injection_masking():
    """
    Security Test: Ensure that SQL injection payloads disguised as tokens
    do not bypass the masking algorithm (i.e. length and structure remain obfuscated).
    """
    payload_1 = "'; DROP TABLE fyers_tokens; --"
    payload_2 = "OR 1=1;--"
    
    masked_1 = _mask_token(payload_1)
    masked_2 = _mask_token(payload_2)
    
    # 1. Masking shouldn't expose the sensitive injection string entirely
    # The default masking is f"{t[:4]}...{t[-4:]}"
    assert "DROP TABLE" not in masked_1
    assert len(masked_1) <= 15  # Max length of a masked string is 11 or length dependent

def test_security_massive_string_masking():
    """
    Security Test: Ensure that a massive buffer overflow string disguised as a token
    is efficiently masked without regex backtracking issues (ReDoS) or memory exhaustion.
    """
    # A 1-million character token
    massive_token = "A" * 1_000_000
    
    # Masking should be near-instant and O(1)
    masked = _mask_token(massive_token)
    
    assert masked == "AAAA...AAAA"
    assert len(masked) == 11
