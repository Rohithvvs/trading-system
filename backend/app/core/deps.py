import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from ..db.session import get_db, get_sync_db
from ..models.auth import User
from ..core.security import decode_access_token
from ..core.roles import VALID_ROLES, DEFAULT_ROLE, UserRole, normalize_role
from sqlalchemy import select


def _extract_token_payload(request: Request) -> dict:
    """
    Decode and return JWT payload from Authorization header or HttpOnly cookie.
    Never trust a frontend-supplied user_id or role.
    """
    token = None
    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    try:
        payload = decode_access_token(token)
        if not payload.get("sub"):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return payload
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def _normalize_token_role(payload: dict) -> str:
    return normalize_role(payload.get("role"))


def _extract_user_id_from_request(request: Request) -> uuid.UUID:
    """
    Derive authenticated user id from Authorization header or HttpOnly session cookie.
    Never trust a frontend-supplied user_id.
    """
    payload = _extract_token_payload(request)
    # Expose verified JWT claims on request state for stateless authorization (FR-007 / NFR-001).
    request.state.user_id = str(payload.get("sub"))
    request.state.user_role = _normalize_token_role(payload)
    return uuid.UUID(str(payload.get("sub")))


class TokenPrincipal:
    """Stateless authenticated principal derived solely from a verified JWT (no DB read)."""

    __slots__ = ("user_id", "role", "jti", "raw")

    def __init__(self, user_id: str, role: str, jti: str | None = None, raw: dict | None = None):
        self.user_id = user_id
        self.role = role
        self.jti = jti
        self.raw = raw or {}

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN.value


def get_token_principal(request: Request) -> TokenPrincipal:
    """
    NFR-001: role authorization principal with zero database queries.
    Use for pure authorization checks; prefer get_current_user when full User row is required.
    """
    payload = _extract_token_payload(request)
    user_id = str(payload.get("sub"))
    role = _normalize_token_role(payload)
    request.state.user_id = user_id
    request.state.user_role = role
    return TokenPrincipal(
        user_id=user_id,
        role=role,
        jti=payload.get("jti"),
        raw=payload,
    )


def require_roles(*allowed: str):
    """Factory: FastAPI dependency that enforces JWT role claim without a DB lookup."""
    allowed_set = {normalize_role(r) for r in allowed}

    def _dependency(principal: Annotated[TokenPrincipal, Depends(get_token_principal)]) -> TokenPrincipal:
        if principal.role not in allowed_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role privileges",
            )
        return principal

    return _dependency


# Convenience dependencies for lightweight/stateless gates.
# WARNING (audit L-3): JWT role claim only — do NOT use as the sole gate for
# privilege-sensitive /admin/* user-management APIs. Prefer get_current_admin_user.
require_admin = require_roles(UserRole.ADMIN.value)
require_trader_or_admin = require_roles(UserRole.TRADER.value, UserRole.ADMIN.value)


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    user_id = _extract_user_id_from_request(request)
    try:
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return user
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Active, non-soft-deleted principal (audit L-4: soft-deleted cannot use protected APIs)."""
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")
    if current_user.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is unavailable",
        )
    return current_user


async def get_current_admin_user(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """
    Production admin gate for privilege-sensitive admin user-management APIs.

    Resolves the caller via Sprint 1 session identity (Bearer or cookie JWT), loads
    the live User row, and requires:
      - is_active == True and deleted_at is None (via get_current_active_user)
      - stored role == admin

    Token/session role claims alone MUST NOT authorize these routes (FR-001–FR-005).
    Prefer this dependency over JWT-only ``require_admin`` for /admin/* mutations and
    directory APIs. Stateless ``require_admin`` remains for low-risk/future gates only.
    """
    # Defense-in-depth if called without get_current_active_user composition.
    if current_user.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    if normalize_role(current_user.role) != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user


def get_current_user_id_sync(request: Request) -> uuid.UUID:
    """Sync dependency for paper-trading routes (uses cookie JWT only)."""
    return _extract_user_id_from_request(request)


def get_current_user_sync(
    request: Request,
    db: Session = Depends(get_sync_db),
) -> User:
    """Load User via sync session — for paper-trading FastAPI sync handlers."""
    user_id = _extract_user_id_from_request(request)
    user = db.get(User, user_id)
    if not user or not user.is_active or user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user
