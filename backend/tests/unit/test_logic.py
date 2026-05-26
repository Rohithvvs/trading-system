import pytest
from app.services.token_service import _mask_token

def test_mask_token_empty():
    assert _mask_token(None) is None
    assert _mask_token("") is None

def test_mask_token_short():
    assert _mask_token("1234567") == "*******"
    assert _mask_token("12345678") == "********"

def test_mask_token_long():
    assert _mask_token("123456789") == "1234...6789"
    assert _mask_token("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ") == "eyJh...IyfQ"

def test_mask_token_type_handling():
    # Even if an int slips in, it should cast to str
    assert _mask_token(12345) == "*****"
