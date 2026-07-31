"""Encrypt / decrypt broker access tokens at rest.

Uses Fernet (AES-128-CBC + HMAC) with a key derived from TOKEN_ENCRYPTION_KEY.
Ciphertext is stored as ``enc:v1:<base64>`` so legacy plaintext rows can still
be read until re-saved.

Production fail-closed:
  - ``TOKEN_ENCRYPTION_KEY`` MUST be set when APP_ENV is production/prod.
  - ``JWT_SECRET`` is not accepted as the encryption key in production.
  - Weak hardcoded defaults are refused in production.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os

logger = logging.getLogger("app.token_crypto")

_PREFIX = "enc:v1:"
_fernet = None
_DEV_FALLBACK_SECRET = "yoursecretkey_must_be_changed_in_prod"


def _is_production() -> bool:
    return (os.getenv("APP_ENV") or "development").strip().lower() in {
        "production",
        "prod",
    }


def _resolve_secret() -> str:
    secret = (os.getenv("TOKEN_ENCRYPTION_KEY") or "").strip()
    if secret:
        return secret

    # Legacy alias — only accepted outside production.
    legacy = (os.getenv("JWT_SECRET") or "").strip()
    if legacy:
        if _is_production():
            raise RuntimeError(
                "TOKEN_ENCRYPTION_KEY is required in production. "
                "JWT_SECRET is no longer accepted as a broker encryption key."
            )
        logger.warning(
            "TOKEN_ENCRYPTION_KEY unset; falling back to JWT_SECRET (non-production only)"
        )
        return legacy

    if _is_production():
        raise RuntimeError(
            "TOKEN_ENCRYPTION_KEY is required in production for broker token encryption. "
            "Generate a long random secret and set it in the environment."
        )

    logger.warning(
        "TOKEN_ENCRYPTION_KEY unset; using insecure development fallback secret"
    )
    return _DEV_FALLBACK_SECRET


def _get_fernet():
    global _fernet
    if _fernet is not None:
        return _fernet
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("cryptography package is required for token encryption") from exc

    secret = _resolve_secret()
    # Fernet needs 32 url-safe base64-encoded bytes
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    _fernet = Fernet(key)
    return _fernet


def reset_fernet_cache() -> None:
    """Test helper: clear cached Fernet instance after env changes."""
    global _fernet
    _fernet = None


def encrypt_secret(plaintext: str | None) -> str | None:
    if plaintext is None:
        return None
    text = str(plaintext)
    if not text:
        return text
    if text.startswith(_PREFIX):
        return text  # already encrypted
    try:
        token = _get_fernet().encrypt(text.encode("utf-8"))
        return f"{_PREFIX}{token.decode('utf-8')}"
    except Exception:
        logger.error("TOKEN_ENCRYPT_FAILED | encryption failed", exc_info=True)
        raise


def decrypt_secret(value: str | None) -> str | None:
    """Decrypt if prefixed; otherwise return as plaintext (legacy rows)."""
    if value is None:
        return None
    text = str(value)
    if not text.startswith(_PREFIX):
        return text
    blob = text[len(_PREFIX) :]
    try:
        return _get_fernet().decrypt(blob.encode("utf-8")).decode("utf-8")
    except Exception:
        logger.error("TOKEN_DECRYPT_FAILED | ciphertext could not be decrypted")
        raise


def mask_secret(token: str | None, keep: int = 4, max_stars: int = 24) -> str | None:
    """Mask a secret for UI/DB display, e.g. ************************ABCD.

    Always returns a **short** fixed-size string (max 100 chars) so:
    - it fits ``token_masked VARCHAR(512)`` with large headroom
    - masking cost/size is O(1) even for multi-KB JWTs
    - middle/prefix of the secret is never exposed
    - never stores hundreds of '*' proportional to JWT length
    """
    if not token:
        return None
    t = str(token)
    if len(t) <= keep * 2:
        return ("*" * len(t))[:100]
    # Cap stars — never grow with secret length (Fyers JWTs are 500–900+ chars)
    stars = max(8, min(int(max_stars), 48))
    masked = f"{'*' * stars}{t[-keep:]}"
    return masked[:100]


def is_encrypted(value: str | None) -> bool:
    return bool(value and str(value).startswith(_PREFIX))
