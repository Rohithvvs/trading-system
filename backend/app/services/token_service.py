from __future__ import annotations
from sqlalchemy import select, update
import base64
import json

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, List
import os

from sqlalchemy.ext.asyncio import AsyncSession
from ..config import settings
from ..models import FyersToken, FyersTokenHistory

logger = logging.getLogger("app.token")

_CACHED_TOKEN: str | None = None
_TOKEN_EXPIRY: datetime | None = None
_TOKEN_SAVED_AT: datetime | None = None
_TOKEN_CACHE_TTL = timedelta(minutes=int(os.getenv("FYERS_TOKEN_CACHE_MINUTES", "60")))

import threading
_TOKEN_LOCK = threading.Lock()


def _decode_jwt_expiry(token: str) -> datetime | None:
    """Extract the ``exp`` claim from a FYERS JWT without signature verification."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload_b64 = parts[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        decoded = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(decoded)
        exp_ts = payload.get("exp") or payload.get("expires_in")
        if exp_ts is None:
            return None
        return datetime.fromtimestamp(int(exp_ts), tz=timezone.utc)
    except Exception:
        return None

def _clear_token_cache() -> None:
    global _CACHED_TOKEN, _TOKEN_EXPIRY, _TOKEN_SAVED_AT
    _CACHED_TOKEN = None
    _TOKEN_EXPIRY = None
    _TOKEN_SAVED_AT = None
    try:
        from ..core.response_cache import cache_invalidate
        cache_invalidate("token_status")
    except Exception:
        pass
    logger.info("TOKEN_INVALIDATED | Local memory cache cleared")

def has_cached_token() -> bool:
    return bool(_CACHED_TOKEN and _TOKEN_EXPIRY and datetime.now(timezone.utc) < _TOKEN_EXPIRY)


def _set_token_cache(access_token: str, saved_at: datetime | None = None) -> None:
    global _CACHED_TOKEN, _TOKEN_EXPIRY, _TOKEN_SAVED_AT
    _CACHED_TOKEN = access_token
    _TOKEN_EXPIRY = datetime.now(timezone.utc) + _TOKEN_CACHE_TTL
    if saved_at:
        _TOKEN_SAVED_AT = saved_at

async def get_fyers_token_row(db: AsyncSession) -> FyersToken | None:
    return (await db.scalars(select(FyersToken).filter(FyersToken.is_active == True).order_by(FyersToken.created_at.desc()))).first()


def _mask_token(token: str | None) -> str | None:
    if not token:
        return None
    # Delegate to shared masker (asterisks + last 4) — never log full token
    from ..core.token_crypto import mask_secret
    return mask_secret(token)


def _encrypt_for_storage(access_token: str) -> str:
    from ..core.token_crypto import encrypt_secret
    return encrypt_secret(access_token) or access_token


def _decrypt_from_storage(value: str | None) -> str | None:
    if not value:
        return None
    from ..core.token_crypto import decrypt_secret
    try:
        return decrypt_secret(value)
    except Exception:
        logger.error("TOKEN_DECRYPT_FAILED | stored token unreadable")
        return None


async def save_access_token(access_token: str, db: AsyncSession) -> dict:
    logger.info("%s", "=" * 60)
    logger.info("SAVE ACCESS TOKEN STARTED")
    logger.info("%s", "=" * 60)
    logger.info("Token length     : %s", len(access_token) if access_token else 0)
    logger.info(
        "Token preview    : %s",
        _mask_token(access_token) if access_token else "empty",
    )
    logger.info("Timestamp (UTC)  : %s", datetime.now(timezone.utc).isoformat())

    try:
        import asyncio
        from .fyers_service import FyersService
        from .fyers_service import FyersAuthInvalidError, FyersAuthExpiredError, FyersAPIError
        
        logger.info("Validating token against FYERS API...")
        fyers_service = FyersService()
        await asyncio.wait_for(
            asyncio.to_thread(fyers_service.validate_token_sync, access_token),
            timeout=15.0
        )
        logger.info("TOKEN_AUTH_RECOVERED | Token validation successful. Auth recovered.")
        
    except asyncio.TimeoutError:
        logger.error("TOKEN_VALIDATION_FAILURE | Token validation failed: FYERS API timeout")
        return {"status": "error", "message": "Validation failed: FYERS API timeout"}
    except (FyersAuthInvalidError, FyersAuthExpiredError) as e:
        logger.error("TOKEN_VALIDATION_FAILURE | Token validation failed: %s", e)
        return {"status": "error", "message": "Invalid token. Please check and try again."}
    except FyersAPIError as e:
        logger.error("TOKEN_VALIDATION_FAILURE | Token validation failed due to API error: %s", e)
        return {"status": "error", "message": "Token validation failed due to API error."}
    except Exception as e:
        logger.error("Unexpected error validating token: %s", e, exc_info=True)
        return {"status": "error", "message": "Token validation failed."}

    try:
        async with db.begin():
            now = datetime.now(timezone.utc)
            
            # Step 1: Deactivate existing tokens
            logger.info("STEP 1: Deactivating existing tokens...")
            await db.execute(update(FyersToken).where(FyersToken.is_active == True).values(is_active=False, status="inactive"))
            logger.info("STEP 1 RESULT: Deactivated")

            # Parse JWT expiry
            expires_at = _decode_jwt_expiry(access_token)

            # Step 2: Upsert ID=1 row (INSERT ... ON CONFLICT avoids race between concurrent saves)
            logger.info("STEP 2: Upserting ID=1 row...")
            stored = _encrypt_for_storage(access_token)
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            stmt = pg_insert(FyersToken).values(
                id=1,
                access_token=stored,
                created_at=now,
                is_active=True,
                status="active",
                access_token_saved_at=now,
                validated_at=now,
                expires_at=expires_at,
            ).on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "access_token": stored,
                    "is_active": True,
                    "status": "active",
                    "access_token_saved_at": now,
                    "validated_at": now,
                    "expires_at": expires_at,
                },
            )
            await db.execute(stmt)
            row = (await db.scalars(select(FyersToken).filter(FyersToken.id == 1))).one()

            # Step 3: Add history
            logger.info("STEP 3: Adding token history entry...")
            masked = _mask_token(access_token)
            history = FyersTokenHistory(
                access_token_masked=masked,
                saved_at=now,
                status="active",
                note="Manual save via UI",
            )
            db.add(history)
            logger.info("STEP 3 RESULT: History entry added")

            logger.info("STEP 4: Committing DB transaction...")
            # PRE-COMMIT diagnostic
            logger.info("PRE-COMMIT: token_length=%s", len(access_token) if access_token else 0)

        # Cache plaintext in-memory only (never log it)
        _set_token_cache(access_token, row.access_token_saved_at)
        try:
            from ..core.response_cache import cache_invalidate
            cache_invalidate("token_status")
        except Exception:
            pass
        logger.info("STEP 4 RESULT: Commit successful. Final status=%s saved_at=%s", row.status, getattr(row, 'access_token_saved_at', None))

        # POST-COMMIT diagnostics
        logger.info("POST-COMMIT: row_id=%s access_token_saved_at=%s", getattr(row, 'id', None), getattr(row, 'access_token_saved_at', None))

        # Verification read
        try:
            verify_row = await get_fyers_token_row(db)
            logger.info(
                "VERIFY: token_in_db=%s, status=%s",
                bool(verify_row and verify_row.access_token),
                verify_row.status if verify_row else "missing",
            )
        except Exception:
            logger.exception("VERIFY: failed to re-read token row from DB")

        logger.info("%s", "=" * 60)
        logger.info("TOKEN_SAVE_SUCCESS | SAVE ACCESS TOKEN COMPLETED SUCCESSFULLY")
        logger.info("%s", "=" * 60)
        return {"status": "ok", "saved_at": str(row.access_token_saved_at)}

    except Exception as e:
        logger.error("%s", "=" * 60)
        logger.error("SAVE ACCESS TOKEN FAILED")
        logger.error("Exception type   : %s", type(e).__name__)
        logger.error("Exception message: %s", e)
        logger.error("%s", "=" * 60, exc_info=True)
        await db.rollback()
        _clear_token_cache()
        return {"status": "error", "message": "Unable to save access token."}


async def get_token_status(db: AsyncSession) -> dict[str, Any]:
    """
    DB-only token status. Does NOT call FYERS.
    Cached in-process for 5 minutes to avoid repeated DB hits on every page navigation.
    """
    from ..core.response_cache import cache_get, cache_set

    cache_key = "token_status"
    hit = cache_get(cache_key)
    if hit is not None:
        logger.info("TOKEN_STATUS_CACHE_HIT | source=memory")
        return hit

    row = await get_fyers_token_row(db)
    now = datetime.now(timezone.utc)
    expires_at = None
    expires_in_seconds = None
    token_masked = None
    if row:
        plain = _decrypt_from_storage(row.access_token)
        token_masked = _mask_token(plain) if plain else _mask_token("stored")
        expires_at = row.expires_at
        if expires_at is None and plain:
            expires_at = _decode_jwt_expiry(plain)
        if expires_at:
            try:
                exp = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
                remaining = (exp - now).total_seconds()
            except Exception:
                remaining = 0
            expires_in_seconds = max(0, int(remaining))

    status = {
        "access_token_active": bool(row and row.access_token),
        "access_token_saved_at": row.access_token_saved_at.isoformat() if row and row.access_token_saved_at else None,
        "validated_at": getattr(row, 'validated_at', None).isoformat() if row and getattr(row, 'validated_at', None) else None,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "expires_in_seconds": expires_in_seconds,
        "status": row.status if row else "no_token",
        "last_error": row.last_error if row else None,
        "token_masked": token_masked,
        # Never include full access_token
    }
    cache_set(cache_key, status, ttl_seconds=300.0)
    logger.info("TOKEN_STATUS_CACHE_MISS | source=database | status=%s", status.get("status"))
    return status


async def get_token_history(db: AsyncSession, limit: int = 50) -> List[dict[str, Any]]:
    rows = (await db.scalars(select(FyersTokenHistory).order_by(FyersTokenHistory.saved_at.desc()).limit(limit))).all()
    return [
        {
            "id": r.id,
            "access_token_masked": r.access_token_masked,
            "saved_at": r.saved_at.isoformat(),
            "status": r.status,
            "note": r.note,
        }
        for r in rows
    ]


async def get_current_access_token(db: AsyncSession) -> str | None:
    if _CACHED_TOKEN and _TOKEN_EXPIRY and datetime.now(timezone.utc) < _TOKEN_EXPIRY:
        logger.info("TOKEN_CACHE_HIT | source=memory_cache | expiry=%s", _TOKEN_EXPIRY.isoformat() if _TOKEN_EXPIRY else "N/A")
        return _CACHED_TOKEN

    logger.info("TOKEN_CACHE_MISS | source=database | reason=cache_miss_or_expired")
    row = await get_fyers_token_row(db)
    if row is None:
        logger.warning("TOKEN_NOT_FOUND | No FyersToken row found in database")
        _clear_token_cache()
        return None
    if not row.access_token:
        logger.warning("TOKEN_NOT_FOUND | FyersToken row exists but access_token is empty")
        _clear_token_cache()
        return None

    plain = _decrypt_from_storage(row.access_token)
    if not plain:
        logger.warning("TOKEN_NOT_FOUND | Stored token could not be decrypted")
        _clear_token_cache()
        return None
        
    if _TOKEN_SAVED_AT and row.access_token_saved_at and row.access_token_saved_at < _TOKEN_SAVED_AT:
        logger.warning("TOKEN_GENERATION_MISMATCH | DB token is older than our last known token")

    logger.info("TOKEN_REFRESH_FROM_DB | Access token found in DB, status=%s, saved_at=%s", row.status, row.access_token_saved_at)
    _set_token_cache(plain, row.access_token_saved_at)
    return plain


def get_current_access_token_sync() -> tuple[str | None, str]:
    now = datetime.now(timezone.utc)
    if _CACHED_TOKEN and _TOKEN_EXPIRY and now < _TOKEN_EXPIRY:
        logger.info("TOKEN_CACHE_HIT | source=memory_cache | expiry=%s", _TOKEN_EXPIRY.isoformat() if _TOKEN_EXPIRY else "N/A")
        return _CACHED_TOKEN, "cache"

    with _TOKEN_LOCK:
        now = datetime.now(timezone.utc)
        if _CACHED_TOKEN and _TOKEN_EXPIRY and now < _TOKEN_EXPIRY:
            logger.info("TOKEN_CACHE_HIT | source=memory_cache | reason=double_check")
            return _CACHED_TOKEN, "cache"

        logger.info("TOKEN_CACHE_MISS | source=database | reason=cache_miss_or_expired")
        from ..db.session import SessionLocal
        try:
            with SessionLocal() as db:
                row = db.query(FyersToken).filter(FyersToken.is_active == True).order_by(FyersToken.created_at.desc()).first()
                if row is None:
                    logger.warning("TOKEN_NOT_FOUND | No FyersToken row found in database")
                    _clear_token_cache()
                    return None, "database"
                if not row.access_token:
                    logger.warning("TOKEN_NOT_FOUND | FyersToken row exists but access_token is empty")
                    _clear_token_cache()
                    return None, "database"
                plain = _decrypt_from_storage(row.access_token)
                if not plain:
                    logger.warning("TOKEN_NOT_FOUND | Stored token could not be decrypted")
                    _clear_token_cache()
                    return None, "database"
                
                if _TOKEN_SAVED_AT and row.access_token_saved_at and row.access_token_saved_at < _TOKEN_SAVED_AT:
                    logger.warning("TOKEN_GENERATION_MISMATCH | DB token is older than our last known token")
                    
                logger.info("TOKEN_REFRESH_FROM_DB | Access token found in DB, status=%s, saved_at=%s", row.status, getattr(row, 'access_token_saved_at', None))
                _set_token_cache(plain, getattr(row, 'access_token_saved_at', None))
                return plain, "database"
        except Exception as e:
            logger.error("TOKEN_DB_UNAVAILABLE | Database unavailable during cache refresh: %s", str(e))
            if _CACHED_TOKEN:
                logger.warning("TOKEN_DB_UNAVAILABLE | Falling back to expired cached token due to DB outage")
                return _CACHED_TOKEN, "cache_fallback"
            return None, "error"


async def exchange_auth_code(auth_code: str, db: AsyncSession) -> dict:
    """Exchange a FYERS OAuth authorization code for an access token and persist it."""
    import httpx

    app_id = (settings.fyers_app_id or "").strip().strip('"').strip("'")
    secret_id = (settings.fyers_secret_id or "").strip().strip('"').strip("'")

    if not app_id or not secret_id:
        logger.error("OAUTH_EXCHANGE_FAILED | fyers_app_id or fyers_secret_id not configured")
        return {"status": "error", "message": "FYERS app credentials not configured."}

    token_url = "https://api-t1.fyers.in/api/v2/validate-auth/token"
    payload = {
        "grant_type": "authorization_code",
        "appId": app_id,
        "secretId": secret_id,
        "auth_code": auth_code,
    }

    logger.info("OAUTH_EXCHANGE | Exchanging auth_code for access_token")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(token_url, json=payload)
            body = resp.json()
    except httpx.TimeoutException:
        logger.error("OAUTH_EXCHANGE_FAILED | FYERS token exchange timed out")
        return {"status": "error", "message": "FYERS authentication timed out. Please try again."}
    except Exception as exc:
        logger.error("OAUTH_EXCHANGE_FAILED | Network error: %s", exc)
        return {"status": "error", "message": "Could not reach FYERS authentication server."}

    if body.get("s") != "ok":
        msg = body.get("message", "FYERS rejected the authorization code.")
        logger.error("OAUTH_EXCHANGE_FAILED | FYERS returned error: %s", msg)
        return {"status": "error", "message": msg}

    access_token = body.get("access_token")
    if not access_token:
        logger.error("OAUTH_EXCHANGE_FAILED | No access_token in FYERS response")
        return {"status": "error", "message": "FYERS did not return an access token."}

    expires_at = _decode_jwt_expiry(access_token)
    refresh_token = body.get("refresh_token")

    logger.info(
        "OAUTH_EXCHANGE_SUCCESS | token_length=%s | expires_at=%s | has_refresh=%s",
        len(access_token), expires_at.isoformat() if expires_at else "unknown", bool(refresh_token),
    )

    now = datetime.now(timezone.utc)
    try:
        async with db.begin():
            await db.execute(
                update(FyersToken).where(FyersToken.is_active == True).values(is_active=False, status="inactive")
            )
            # Upsert ID=1 row (avoids race between concurrent OAuth exchanges)
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            stmt = pg_insert(FyersToken).values(
                id=1,
                access_token=access_token,
                created_at=now,
                is_active=True,
                status="active",
                access_token_saved_at=now,
                validated_at=now,
                expires_at=expires_at,
            ).on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "access_token": access_token,
                    "is_active": True,
                    "status": "active",
                    "access_token_saved_at": now,
                    "validated_at": now,
                    "expires_at": expires_at,
                },
            )
            await db.execute(stmt)
            row = (await db.scalars(select(FyersToken).filter(FyersToken.id == 1))).one()
            masked = _mask_token(access_token)
            history = FyersTokenHistory(
                access_token_masked=masked,
                saved_at=now,
                status="active",
                note="Auto-generated via FYERS OAuth",
            )
            db.add(history)

        _set_token_cache(access_token, now)
        try:
            from ..core.response_cache import cache_invalidate
            cache_invalidate("token_status")
        except Exception:
            pass

        logger.info("OAUTH_EXCHANGE_COMPLETE | Token saved successfully")
        return {
            "status": "ok",
            "message": "FYERS authentication successful.",
            "expires_at": expires_at.isoformat() if expires_at else None,
        }
    except Exception as e:
        logger.exception("OAUTH_EXCHANGE_DB_FAILED | %s", e)
        await db.rollback()
        _clear_token_cache()
        return {"status": "error", "message": "Failed to save token to database."}


async def get_token_expiry_info(db: AsyncSession) -> dict:
    """Return token expiry information with time remaining."""
    row = await get_fyers_token_row(db)
    if not row or not row.access_token:
        return {
            "has_token": False,
            "expires_at": None,
            "expires_in_seconds": None,
            "is_expired": True,
        }

    expires_at = row.expires_at
    if expires_at is None:
        expires_at = _decode_jwt_expiry(row.access_token)
        if expires_at and expires_at != row.expires_at:
            try:
                row.expires_at = expires_at
                await db.commit()
            except Exception:
                await db.rollback()

    now = datetime.now(timezone.utc)
    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        remaining = (expires_at - now).total_seconds()
        is_expired = remaining <= 0
    else:
        remaining = None
        is_expired = False

    return {
        "has_token": True,
        "status": row.status,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "expires_in_seconds": max(0, int(remaining)) if remaining is not None else None,
        "is_expired": is_expired,
        "validated_at": row.validated_at.isoformat() if row.validated_at else None,
    }


def get_fyers_auth_url() -> str:
    """Generate the FYERS OAuth authorization URL."""
    app_id = (settings.fyers_app_id or "").strip().strip('"').strip("'")
    redirect_uri = (settings.fyers_redirect_uri or "").strip().strip('"').strip("'")

    if not app_id:
        logger.error("OAUTH_URL_FAILED | fyers_app_id not configured")
        return ""

    import urllib.parse
    params = urllib.parse.urlencode({
        "client_id": app_id,
        "redirect_uri": redirect_uri or settings.frontend_url + "/fyers/callback",
        "response_type": "code",
        "state": "fyers_auth",
    })
    return f"https://api.fyers.in/api/v2/validate-auth?{params}"

