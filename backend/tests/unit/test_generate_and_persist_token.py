"""Unit tests for Sprint 4 token persistence helpers
(feature: 009-db-storage-monitoring).

These focus on pure/narrow units: encryption wrappers, status field contracts,
and CLI wiring invariants — without requiring a live database when possible.
"""

from __future__ import annotations

import inspect

import pytest

from backend.app.core.token_crypto import decrypt_secret, encrypt_secret, is_encrypted
from backend.app.services.token_service import (
    _decrypt_from_storage,
    _encrypt_for_storage,
    _mask_token,
    generate_and_persist_fyers_token,
    mask_access_token_preview,
)


@pytest.mark.unit
def test_encrypt_for_storage_uses_project_crypto():
    """FR-005: persistence helpers delegate to Fernet encrypt_secret.

    Fernet ciphertext is non-deterministic (random IV), so we assert format
    and round-trip rather than byte-equality across two encrypt calls.
    """
    plain = "unit-token-value-9999"
    cipher = _encrypt_for_storage(plain)
    assert is_encrypted(cipher)
    assert cipher.startswith("enc:v1:")
    assert is_encrypted(encrypt_secret(plain))
    assert _decrypt_from_storage(cipher) == plain
    assert decrypt_secret(cipher) == plain


@pytest.mark.unit
def test_encrypt_for_storage_never_returns_raw_jwt_fragment():
    """SC-003: ciphertext must not contain identifiable JWT payload segments."""
    plain = "eyJhbGciOiJIUzI1NiJ9.segment_payload_here.signature_tail"
    cipher = _encrypt_for_storage(plain)
    assert "segment_payload_here" not in cipher
    assert plain not in cipher


@pytest.mark.unit
def test_mask_token_safe_for_cli_stdout():
    """CLI must only surface a masked preview (contract api_contracts.md)."""
    token = "generated_access_token_WXYZ"
    masked = _mask_token(token)
    assert masked is not None
    assert token not in masked
    assert masked.endswith("WXYZ")
    assert "*" in masked


@pytest.mark.unit
def test_generate_and_persist_is_async_and_accepts_db_session():
    """Library contract: async function with AsyncSession parameter (FR-006)."""
    assert inspect.iscoroutinefunction(generate_and_persist_fyers_token)
    sig = inspect.signature(generate_and_persist_fyers_token)
    assert "db" in sig.parameters


@pytest.mark.unit
def test_monitoring_status_literals_documented():
    """Status values required by FR-003 are the Success/Failed literals."""
    # Guard against accidental rename drift in service source.
    source = inspect.getsource(generate_and_persist_fyers_token)
    assert '"Success"' in source or "'Success'" in source
    assert "last_error" in source
    # Must not *call* UI save path (docstring may mention it as avoided)
    assert "await save_access_token" not in source
    assert "save_access_token(" not in source


@pytest.mark.unit
def test_mask_access_token_preview_public_api():
    assert mask_access_token_preview("abcdefghijklmnop1234").endswith("1234")
    assert mask_access_token_preview(None) is None
