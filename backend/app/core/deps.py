import uuid

from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from ..db.session import get_db, get_sync_db
from ..models.auth import User
from ..core.security import decode_access_token
from sqlalchemy import select


def _extract_user_id_from_request(request: Request) -> uuid.UUID:
    """
    Derive authenticated user id from the HttpOnly session cookie.
    Never trust a frontend-supplied user_id.
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return uuid.UUID(str(user_id))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


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
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")
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
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user
