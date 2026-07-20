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

    assert masked_1 is not None
    assert masked_2 is not None
    # Middle of the injection payload must never appear in the redacted form.
    assert "DROP TABLE" not in masked_1
    assert "OR 1=1" not in masked_2
    # Production masker caps output size (O(1), max 100 chars).
    assert len(masked_1) <= 100
    assert masked_1.startswith("*")
    assert masked_2.startswith("*")


def test_security_massive_string_masking():
    """
    Security Test: Ensure that a massive buffer overflow string disguised as a token
    is efficiently masked without proportional growth (O(1) size/cost).
    """
    # A 1-million character token
    massive_token = "A" * 1_000_000

    masked = _mask_token(massive_token)

    assert masked is not None
    assert masked.endswith("AAAA")
    assert "*" in masked
    assert len(masked) <= 100
    # Default max_stars=24 + last 4 chars
    assert masked == ("*" * 24) + "AAAA"
