from datetime import datetime, timedelta, timezone
import os
import uuid
from typing import Any, Dict, Optional, Tuple
import jwt
from passlib.context import CryptContext

# Secret keys
SECRET_KEY = os.getenv("JWT_SECRET", "yoursecretkey_must_be_changed_in_prod")
REFRESH_SECRET_KEY = os.getenv("JWT_REFRESH_SECRET", "yourrefreshsecretkey_must_be_changed_in_prod")
ALGORITHM = "HS256"

# Expirations
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440")) # 24 hours
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# Crypt context for Argon2id
pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto",
)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> Tuple[str, str]:
    """Returns (token, jti)"""
    to_encode = data.copy()
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
