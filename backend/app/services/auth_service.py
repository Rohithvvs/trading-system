import re
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.auth import User
from app.schemas.auth import UserCreate
from app.core.security import get_password_hash, verify_password
from app.services.audit_service import AuditService
from sqlalchemy.exc import IntegrityError

from app.config.settings import settings
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

def validate_password(password: str) -> bool:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one digit")
    if not re.search(r"[@$!%*?&]", password):
        raise ValueError("Password must contain at least one special character")
    return True

async def create_user(db: AsyncSession, user_in: UserCreate, ip_address: str = None, user_agent: str = None) -> User:
    try:
        validate_password(user_in.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    
    # Check if user exists
    stmt = select(User).where(User.email == user_in.email)
    result = await db.execute(stmt)
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The user with this email already exists in the system.",
        )
    
    db_user = User(
        id=uuid.uuid4(),
        email=user_in.email,
        full_name=user_in.full_name,
        role=user_in.role,
        password_hash=get_password_hash(user_in.password),
        is_active=True,
    )
    db.add(db_user)
    
    try:
        await db.commit()
        await db.refresh(db_user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Error occurred while creating user. Email might already exist.",
        )
    
    # Log the registration event
    await AuditService.log_event(
        db=db,
        user_id=str(db_user.id),
        event_type="user_registration",
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"email": db_user.email}
    )
    
    return db_user


from app.schemas.auth import LoginRequest
from app.models.auth import UserSession
from app.core.security import create_access_token, create_refresh_token, get_password_hash

_DUMMY_HASH = get_password_hash("dummy_timing_attack_protection")

async def authenticate_user(db: AsyncSession, email: str, password: str, ip_address: str = None, user_agent: str = None) -> User:
    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        # Avoid user enumeration
        verify_password(password, _DUMMY_HASH)
        await AuditService.log_event(db, None, "login_failed", ip_address, user_agent, {"email": email, "reason": "user_not_found"})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        
    if not verify_password(password, user.password_hash):
        await AuditService.log_event(db, str(user.id), "login_failed", ip_address, user_agent, {"reason": "invalid_password"})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
        
    await AuditService.log_event(db, str(user.id), "login_success", ip_address, user_agent)
    return user

async def create_user_session(db: AsyncSession, user_id: str, ip_address: str = None, user_agent: str = None, remember_me: bool = False) -> Tuple[str, str]:
    # Generate tokens
    access_token, access_jti = create_access_token({"sub": user_id})
    
    if remember_me:
        refresh_token, refresh_jti = create_refresh_token({"sub": user_id}, expires_delta=timedelta(days=30))
        expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    else:
        refresh_token, refresh_jti = create_refresh_token({"sub": user_id})
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        
    # Store session
    session = UserSession(
        id=uuid.uuid4(),
        user_id=uuid.UUID(user_id),
        refresh_token_hash=get_password_hash(refresh_token),
        ip_address=ip_address,
        user_agent=user_agent,
        is_active=True,
        expires_at=expires_at
    )
    
    db.add(session)
    await db.commit()
    
    return access_token, refresh_token


async def get_active_sessions(db: AsyncSession, user_id: str):
    stmt = select(UserSession).where(
        UserSession.user_id == user_id,
        UserSession.is_active == True,
        UserSession.expires_at > datetime.now(timezone.utc)
    ).order_by(UserSession.last_active_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()

async def revoke_session(db: AsyncSession, user_id: str, session_id: str):
    stmt = select(UserSession).where(
        UserSession.id == session_id,
        UserSession.user_id == user_id
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        
    session.is_active = False
    await db.commit()
    await AuditService.log_event(db, user_id, "session_revoked", None, None, {"session_id": session_id})


async def google_auth(db: AsyncSession, id_token_str: str, ip_address: str = None, user_agent: str = None) -> User:
    try:
        info = await asyncio.to_thread(
            id_token.verify_oauth2_token,
            id_token_str,
            google_requests.Request(),
            settings.google_client_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid Google token: {str(e)}")

    if info.get("iss") not in ["accounts.google.com", "https://accounts.google.com"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid issuer")

    google_id = info.get("sub")
    email = info.get("email")
    name = info.get("name", "")
    picture = info.get("picture")

    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google account has no email")

    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user:
        if user.google_id and user.google_id != google_id:
            await AuditService.log_event(db, str(user.id), "login_failed", ip_address, user_agent, {"reason": "google_id_mismatch", "email": email})
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This email is already linked to a different Google account")
        user.google_id = google_id
        user.provider = "google"
        if picture:
            user.profile_picture = picture
        if name and not user.full_name:
            user.full_name = name
        await db.commit()
        await db.refresh(user)
        await AuditService.log_event(db, str(user.id), "login_success", ip_address, user_agent, {"provider": "google"})
        return user

    user = User(
        id=uuid.uuid4(),
        email=email,
        full_name=name,
        google_id=google_id,
        provider="google",
        profile_picture=picture,
        is_active=True,
        is_email_verified=True,
        password_hash=get_password_hash(uuid.uuid4().hex),
    )
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="An account with this email already exists")

    await AuditService.log_event(db, str(user.id), "user_registration", ip_address, user_agent, {"provider": "google", "email": email})
    await AuditService.log_event(db, str(user.id), "login_success", ip_address, user_agent, {"provider": "google"})
    return user

