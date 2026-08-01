import re
import uuid
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models.auth import User
from ..schemas.auth import UserCreate
from ..core.security import get_password_hash, verify_password
from ..services.audit_service import AuditService
from sqlalchemy.exc import IntegrityError

from ..config.settings import settings
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
    
    from ..core.roles import UserRole

    db_user = User(
        id=uuid.uuid4(),
        email=user_in.email,
        full_name=user_in.full_name,
        role=UserRole.TRADER.value,
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

    # Auto-provision isolated paper trading account (₹10,00,000) — never recreate if exists
    try:
        from ..db.session import SessionLocal
        from ..services.paper_trading_service import PaperTradingService
        def _provision():
            with SessionLocal() as sync_db:
                PaperTradingService.ensure_paper_account_for_user(sync_db, db_user.id)
        await asyncio.to_thread(_provision)
    except Exception:
        # Registration must not fail if paper provisioning hiccups; account is created on first paper API call
        pass
    
    return db_user


from ..schemas.auth import LoginRequest
from ..models.auth import UserSession
from ..core.security import create_access_token, create_refresh_token, get_password_hash

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

    # Audit M-B / L-4 hardening: soft-deleted accounts must not receive new sessions.
    if user.deleted_at is not None:
        await AuditService.log_event(
            db, str(user.id), "login_failed", ip_address, user_agent, {"reason": "account_soft_deleted"}
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is unavailable")
        
    await AuditService.log_event(db, str(user.id), "login_success", ip_address, user_agent)
    return user

async def create_user_session(db: AsyncSession, user_id: str, role: str = "trader", ip_address: str = None, user_agent: str = None, remember_me: bool = False) -> Tuple[str, str]:
    from ..core.roles import normalize_role

    # Generate tokens (role clamped at issuance).
    access_token, access_jti = create_access_token({"sub": user_id, "role": normalize_role(role)})
    
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
    logger = logging.getLogger("app.auth.google")

    if not (settings.google_client_id or "").strip():
        logger.error("GOOGLE_AUTH_FAILED | GOOGLE_CLIENT_ID is not configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured on the server",
        )

    if not id_token_str or not str(id_token_str).strip():
        logger.warning("GOOGLE_AUTH_FAILED | empty id_token | ip=%s", ip_address)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Google id_token")

    logger.info(
        "GOOGLE_AUTH_ATTEMPT | token_len=%s | ip=%s | audience_configured=%s",
        len(id_token_str),
        ip_address,
        bool(settings.google_client_id),
    )

    try:
        info = await asyncio.to_thread(
            id_token.verify_oauth2_token,
            id_token_str,
            google_requests.Request(),
            settings.google_client_id,
        )
    except ValueError as e:
        logger.warning("GOOGLE_AUTH_FAILED | invalid_token | ip=%s | err=%s", ip_address, e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid Google token: {str(e)}")

    if info.get("iss") not in ["accounts.google.com", "https://accounts.google.com"]:
        logger.warning("GOOGLE_AUTH_FAILED | invalid_issuer | iss=%s", info.get("iss"))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid issuer")

    google_id = info.get("sub")
    email = info.get("email")
    name = info.get("name", "")
    picture = info.get("picture")

    if not email:
        logger.warning("GOOGLE_AUTH_FAILED | no_email | sub=%s", google_id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google account has no email")

    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user:
        if user.google_id and user.google_id != google_id:
            await AuditService.log_event(db, str(user.id), "login_failed", ip_address, user_agent, {"reason": "google_id_mismatch", "email": email})
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This email is already linked to a different Google account")
        if not user.is_active:
            await AuditService.log_event(db, str(user.id), "login_failed", ip_address, user_agent, {"reason": "account_disabled", "provider": "google"})
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
        if user.deleted_at is not None:
            await AuditService.log_event(
                db, str(user.id), "login_failed", ip_address, user_agent, {"reason": "account_soft_deleted", "provider": "google"}
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is unavailable")
        user.google_id = google_id
        user.provider = "google"
        if picture:
            user.profile_picture = picture
        if name and not user.full_name:
            user.full_name = name
        await db.commit()
        await db.refresh(user)
        await AuditService.log_event(db, str(user.id), "login_success", ip_address, user_agent, {"provider": "google"})
        logger.info("GOOGLE_AUTH_SUCCESS | existing_user | user_id=%s | email=%s", user.id, email)
        return user

    from ..core.roles import UserRole as _UserRole

    user = User(
        id=uuid.uuid4(),
        email=email,
        full_name=name,
        google_id=google_id,
        provider="google",
        profile_picture=picture,
        is_active=True,
        is_email_verified=True,
        role=_UserRole.TRADER.value,
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
    logger.info("GOOGLE_AUTH_SUCCESS | new_user | user_id=%s | email=%s", user.id, email)

    try:
        from ..db.session import SessionLocal
        from ..services.paper_trading_service import PaperTradingService
        def _provision_google():
            with SessionLocal() as sync_db:
                PaperTradingService.ensure_paper_account_for_user(sync_db, user.id)
        await asyncio.to_thread(_provision_google)
    except Exception:
        pass

    return user


import secrets
import hashlib
from ..services.email_service import send_password_reset_email

RESET_TOKEN_EXPIRE_MINUTES = 15
RESET_RATE_LIMIT_MINUTES = 60
RESET_RATE_LIMIT_MAX = 5

_forgot_rate_cache: dict[str, list[datetime]] = {}

def _rate_limit_exceeded(key: str) -> bool:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=RESET_RATE_LIMIT_MINUTES)
    entries = _forgot_rate_cache.get(key, [])
    entries = [t for t in entries if t > window_start]
    _forgot_rate_cache[key] = entries
    return len(entries) >= RESET_RATE_LIMIT_MAX

def _record_rate_limit(key: str) -> None:
    now = datetime.now(timezone.utc)
    _forgot_rate_cache.setdefault(key, []).append(now)

async def request_password_reset(db: AsyncSession, email: str, ip_address: str | None = None) -> dict:
    ip_key = f"ip:{ip_address}" if ip_address else None
    email_key = f"email:{email}"
    if ip_key and _rate_limit_exceeded(ip_key):
        return {"message": "If an account exists, a password reset link has been sent."}
    if _rate_limit_exceeded(email_key):
        return {"message": "If an account exists, a password reset link has been sent."}

    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user:
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        user.reset_password_token = token_hash
        user.reset_password_expires_at = datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)
        await db.commit()

        frontend_url = (settings.frontend_url or "http://localhost:5173").rstrip("/")
        reset_url = f"{frontend_url}/auth/reset-password?token={token}"
        # SMTP is blocking I/O — do not hold the event loop during Gmail handshake.
        sent = await asyncio.to_thread(send_password_reset_email, email, reset_url)
        if not sent:
            logging.getLogger("app.auth").warning(
                "PASSWORD_RESET_EMAIL_NOT_SENT | email=%s | url_host=%s",
                email,
                frontend_url,
            )

        await AuditService.log_event(
            db, str(user.id), "password_reset_requested", ip_address,
            metadata={"email": email, "email_sent": sent}
        )

    if ip_key:
        _record_rate_limit(ip_key)
    _record_rate_limit(email_key)
    return {"message": "If an account exists, a password reset link has been sent."}


async def confirm_password_reset(db: AsyncSession, token: str, new_password: str) -> dict:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = datetime.now(timezone.utc)

    stmt = select(User).where(
        User.reset_password_token == token_hash,
        User.reset_password_expires_at.isnot(None),
        User.reset_password_expires_at > now,
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token.")

    validate_password(new_password)
    user.password_hash = get_password_hash(new_password)
    user.reset_password_token = None
    user.reset_password_expires_at = None

    # Invalidate all active sessions for this user
    session_stmt = select(UserSession).where(
        UserSession.user_id == user.id,
        UserSession.is_active == True,
    )
    sessions = (await db.execute(session_stmt)).scalars().all()
    for s in sessions:
        s.is_active = False

    await db.commit()

    await AuditService.log_event(
        db, str(user.id), "password_reset_completed",
        metadata={"email": user.email}
    )

    return {"message": "Password updated successfully."}

