import pytest
from backend.app.services.token_service import _mask_token


def test_mask_token_empty():
    assert _mask_token(None) is None
    assert _mask_token("") is None


def test_mask_token_short():
    # Short secrets (<= 8 chars) are fully redacted with asterisks.
    assert _mask_token("1234567") == "*******"
    assert _mask_token("12345678") == "********"


def test_mask_token_long():
    # Production masker: capped asterisks + last 4 chars (never exposes prefix/middle).
    masked = _mask_token("123456789")
    assert masked is not None
    assert masked.endswith("6789")
    assert masked.startswith("*")
    assert "1234" not in masked  # prefix must not leak

    jwt = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ"
    )
    masked_jwt = _mask_token(jwt)
    assert masked_jwt is not None
    assert masked_jwt.endswith(jwt[-4:])
    assert "eyJh" not in masked_jwt
    assert len(masked_jwt) <= 100


def test_mask_token_type_handling():
    # Even if an int slips in, it should cast to str
    assert _mask_token(12345) == "*****"
