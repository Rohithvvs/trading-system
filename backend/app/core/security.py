"""Single-user security utilities.

User authentication is disabled. This module gates optional operator/diagnostics
endpoints via ``API_KEY`` and documents production fail-closed rules.

Broker token encryption lives in ``app.core.token_crypto`` (Fernet / cryptography).
"""
from __future__ import annotations

import logging
import os
import secrets

logger = logging.getLogger("app.security")


def _is_production() -> bool:
    return (os.getenv("APP_ENV") or "development").strip().lower() in {
        "production",
        "prod",
    }


def _configured_api_key() -> str:
    return (os.getenv("API_KEY") or "").strip()


class APIKeyAuth:
    """API key authentication dependency for diagnostics / operator APIs.

    Behaviour:
    - Development / non-production: open when ``API_KEY`` is unset (local DX).
    - Production: ``API_KEY`` is required; missing key → 503; wrong key → 401.
    """

    def __init__(self, api_key: str | None = None) -> None:
        if api_key is not None:
            self.api_key = api_key.strip()
        else:
            self.api_key = _configured_api_key()

    def __call__(self, authorization: str | None = None) -> bool:
        from fastapi import HTTPException

        if not self.api_key:
            if _is_production():
                logger.error(
                    "OPERATOR_API_KEY_MISSING | app_env=production | "
                    "diagnostics/operator endpoints refuse open access"
                )
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "API_KEY is required in production for operator endpoints. "
                        "Set API_KEY in the environment."
                    ),
                )
            return True

        provided = ""
        if authorization and authorization.startswith("Bearer "):
            provided = authorization[7:].strip()

        # Constant-time compare; pad-safe for empty provided token.
        if provided and secrets.compare_digest(provided, self.api_key):
            return True

        logger.warning(
            "OPERATOR_API_KEY_REJECTED | reason=invalid_or_missing_bearer | "
            "has_authorization=%s",
            bool(authorization),
        )
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )


def verify_api_key(authorization: str | None = None) -> bool:
    return APIKeyAuth()(authorization)


def require_api_key(authorization: str | None = None) -> bool:
    return verify_api_key(authorization)
