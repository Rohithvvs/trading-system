"""Unit tests for broker token encryption helpers."""
from __future__ import annotations

from backend.app.core.token_crypto import (
    decrypt_secret,
    encrypt_secret,
    is_encrypted,
    mask_secret,
)


def test_encrypt_decrypt_roundtrip():
    plain = "client_id:eyJhbGciOiJIUzI1NiJ9.payload.signature"
    cipher = encrypt_secret(plain)
    assert cipher is not None
    assert is_encrypted(cipher)
    assert plain not in cipher
    assert decrypt_secret(cipher) == plain


def test_legacy_plaintext_passthrough():
    plain = "legacy-plaintext-token-value"
    assert decrypt_secret(plain) == plain
    assert not is_encrypted(plain)


def test_mask_never_exposes_middle():
    token = "abcdefghijklmnop1234"
    masked = mask_secret(token)
    assert masked is not None
    assert "efghijklmnop" not in masked
    assert masked.endswith("1234")
    assert "*" in masked
    assert "a" not in masked  # leading plaintext never shown


def test_double_encrypt_idempotent():
    plain = "another-token-value-xyz"
    once = encrypt_secret(plain)
    twice = encrypt_secret(once)
    assert once == twice
