from datetime import datetime, timedelta, timezone
import logging
import os
import uuid
from typing import Any, Dict, Optional, Tuple
import jwt
from passlib.context import CryptContext

from .roles import DEFAULT_ROLE, VALID_ROLES, normalize_role

logger = logging.getLogger("app.core.security")

# Secret keys
_INSECURE_JWT_DEFAULT = "yoursecretkey_must_be_changed_in_prod"
_INSECURE_REFRESH_DEFAULT = "yourrefreshsecretkey_must_be_changed_in_prod"
SECRET_KEY = os.getenv("JWT_SECRET", _INSECURE_JWT_DEFAULT)
REFRESH_SECRET_KEY = os.getenv("JWT_REFRESH_SECRET", _INSECURE_REFRESH_DEFAULT)
ALGORITHM = "HS256"

def _default_access_token_minutes() -> int:
    """Shorter default TTL in production/staging (M-2); 24h remains for local/dev."""
    env = os.getenv("APP_ENV", "development").strip().lower()
    if env in {"production", "prod", "staging"}:
        return int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))  # 1 hour
    return int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # 24 hours


# Expirations (env ACCESS_TOKEN_EXPIRE_MINUTES always wins when set)
ACCESS_TOKEN_EXPIRE_MINUTES = _default_access_token_minutes()
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# Crypt context for Argon2id
pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto",
)


def assert_jwt_secrets_safe_for_env(app_env: str | None = None) -> None:
    """Fail closed in production when JWT secrets are missing or still the insecure defaults."""
    env = (app_env or os.getenv("APP_ENV", "development")).strip().lower()
    if env not in {"production", "prod", "staging"}:
        if SECRET_KEY in {"", _INSECURE_JWT_DEFAULT}:
            logger.warning(
                "JWT_SECRET_INSECURE | Using default/empty JWT_SECRET outside production. "
                "Set JWT_SECRET before deploying."
            )
        return
    if not SECRET_KEY or SECRET_KEY == _INSECURE_JWT_DEFAULT:
        raise RuntimeError(
            "JWT_SECRET must be set to a strong non-default value in production/staging."
        )
    if not REFRESH_SECRET_KEY or REFRESH_SECRET_KEY == _INSECURE_REFRESH_DEFAULT:
        raise RuntimeError(
            "JWT_REFRESH_SECRET must be set to a strong non-default value in production/staging."
        )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> Tuple[str, str]:
    """Returns (token, jti). Role claim is clamped to VALID_ROLES (trader|admin)."""
    to_encode = data.copy()
    to_encode["role"] = normalize_role(to_encode.get("role"))
    jti = str(uuid.uuid4())
    to_encode.update({"jti": jti})
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt, jti

def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> Tuple[str, str]:
    """Returns (token, jti)"""
    to_encode = data.copy()
    jti = str(uuid.uuid4())
    to_encode.update({"jti": jti})
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, REFRESH_SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt, jti

def decode_access_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

def decode_refresh_token(token: str) -> dict:
    return jwt.decode(token, REFRESH_SECRET_KEY, algorithms=[ALGORITHM])


class APIKeyAuth:
    """API key authentication dependency for diagnostics APIs.

    Reuses the existing JWT security infrastructure. In Phase 0 the single
    admin role means all authenticated users have full access.

    When ``API_KEY`` is unset/empty, Phase 0 allows open access (local dev).
    When set, requires ``Authorization: Bearer <API_KEY>``.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("API_KEY", "")

    def __call__(self, authorization: str | None = None) -> bool:
        from fastapi import HTTPException

        if not self.api_key:
            return True
        if authorization and authorization.startswith("Bearer "):
            token = authorization[7:].strip()
            if token == self.api_key:
                return True
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )


def verify_api_key(authorization: str | None = None) -> bool:
    """FastAPI dependency for API key authentication.

    Injects the ``Authorization`` header when used as a FastAPI dependency.
    Raises HTTP 401 when ``API_KEY`` is configured and the bearer token is
    missing or invalid. When ``API_KEY`` is empty, allows all requests
    (Phase 0 local-dev convenience).
    """
    from fastapi import Header, HTTPException

    # Support both dependency-injected Header and direct calls.
    # When FastAPI resolves this, callers should use the wrapped dependency below.
    api_key = os.getenv("API_KEY", "")
    if not api_key:
        return True
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        if token == api_key:
            return True
    raise HTTPException(
        status_code=401,
        detail="Invalid or missing API key",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_api_key(authorization: str | None = None) -> bool:
    """FastAPI dependency that reads the Authorization header."""
    from fastapi import Header

    # Re-bind for FastAPI signature inspection via dependency wrapper in routes.
    return verify_api_key(authorization)
