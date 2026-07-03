from __future__ import annotations
from sqlalchemy import select, update

from datetime import datetime, timedelta
import logging
from typing import Any, List
import os

from sqlalchemy.ext.asyncio import AsyncSession
from ..models import FyersToken, FyersTokenHistory

logger = logging.getLogger("app.token")

_CACHED_TOKEN: str | None = None
_TOKEN_EXPIRY: datetime | None = None
_TOKEN_SAVED_AT: datetime | None = None
_TOKEN_CACHE_TTL = timedelta(minutes=int(os.getenv("FYERS_TOKEN_CACHE_MINUTES", "60")))

import threading
_TOKEN_LOCK = threading.Lock()

# Internal flag to force a refresh attempt on the next get_current call
# (set by auth failure paths so that "retry the original request" can succeed transparently)
_FORCE_REFRESH_NEXT_GET = False

def _force_refresh_on_next_get() -> None:
    """Called when an auth error is detected during a live FYERS call.
    Makes the next get_current_* run the refresh logic even if DB still shows a (now bad) access token."""
    global _FORCE_REFRESH_NEXT_GET
    _FORCE_REFRESH_NEXT_GET = True

def _clear_token_cache() -> None:
    global _CACHED_TOKEN, _TOKEN_EXPIRY, _TOKEN_SAVED_AT
    _CACHED_TOKEN = None
    _TOKEN_EXPIRY = None
    _TOKEN_SAVED_AT = None
    logger.info("TOKEN_INVALIDATED | Local memory cache cleared")

def has_cached_token() -> bool:
    return bool(_CACHED_TOKEN and _TOKEN_EXPIRY and datetime.utcnow() < _TOKEN_EXPIRY)


def _set_token_cache(access_token: str, saved_at: datetime | None = None) -> None:
    global _CACHED_TOKEN, _TOKEN_EXPIRY, _TOKEN_SAVED_AT
    _CACHED_TOKEN = access_token
    _TOKEN_EXPIRY = datetime.utcnow() + _TOKEN_CACHE_TTL
    if saved_at:
        _TOKEN_SAVED_AT = saved_at

async def get_fyers_token_row(db: AsyncSession) -> FyersToken | None:
    return (await db.scalars(select(FyersToken).filter(FyersToken.is_active == True).order_by(FyersToken.created_at.desc()))).first()


def _mask_token(token: str | None) -> str | None:
    if not token:
        return None
    t = str(token)
    if len(t) <= 8:
        return "*" * len(t)
    return f"{t[:4]}...{t[-4:]}"


async def save_access_token(access_token: str, db: AsyncSession) -> dict:
    logger.info("%s", "=" * 60)
    logger.info("SAVE ACCESS TOKEN STARTED")
    logger.info("%s", "=" * 60)
    logger.info("Token length     : %s", len(access_token) if access_token else 0)
    logger.info(
        "Token preview    : ...%s",
        access_token[-8:] if access_token and len(access_token) >= 8 else "too_short",
    )
    logger.info("Timestamp (UTC)  : %s", datetime.utcnow().isoformat())

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
        logger.error("TOKEN_VALIDATION_FAILURE | Token validation failed: %s", str(e))
        return {"status": "error", "message": f"Invalid token: {str(e)}"}
    except FyersAPIError as e:
        logger.error("TOKEN_VALIDATION_FAILURE | Token validation failed due to API error: %s", str(e))
        return {"status": "error", "message": f"Validation failed: {str(e)}"}
    except Exception as e:
        logger.error("Unexpected error validating token: %s", str(e))
        return {"status": "error", "message": f"Validation error: {str(e)}"}

    try:
        async with db.begin():
            now = datetime.utcnow()
            
            # Step 1: Deactivate existing tokens
            logger.info("STEP 1: Deactivating existing tokens...")
            await db.execute(update(FyersToken).where(FyersToken.is_active == True).values(is_active=False, status="inactive"))
            logger.info("STEP 1 RESULT: Deactivated")

            # Step 2: Ensure ID=1 row exists
            logger.info("STEP 2: Checking for existing ID=1 row...")
            row = (await db.scalars(select(FyersToken).filter(FyersToken.id == 1))).one_or_none()
            
            if row:
                logger.info("STEP 2 RESULT: Found existing row. Updating...")
                row.access_token = access_token
                row.is_active = True
                row.status = "active"
                row.access_token_saved_at = now
                row.validated_at = now
                db.add(row)
            else:
                logger.info("STEP 2 RESULT: No row found. Creating new...")
                row = FyersToken(
                    id=1,
                    access_token=access_token,
                    created_at=now,
                    is_active=True,
                    status="active",
                    access_token_saved_at=now,
                    validated_at=now,
                )
                db.add(row)

            # Step 3: Add history (use only fields that exist in FyersTokenHistory model)
            logger.info("STEP 3: Adding token history entry...")
            history = FyersTokenHistory(
                access_token_masked=_mask_token(access_token),
                status="active",
                note="Manual save via UI",
            )
            db.add(history)
            logger.info("STEP 3 RESULT: History entry added")

            logger.info("STEP 4: Committing DB transaction...")
            # PRE-COMMIT diagnostic
            logger.info("PRE-COMMIT: token_length=%s", len(access_token) if access_token else 0)

            try:
                db_url = str(engine.url)
                logger.info("DB ENGINE URL: %s", db_url)
            except Exception:
                pass

        # We must refresh outside the transaction block if expire_on_commit was true,
        # but since expire_on_commit=False, row retains state!
        # await db.refresh(row) is not strictly needed inside, but if needed, we can do it inside.
        _set_token_cache(access_token, row.access_token_saved_at)
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
        logger.error("Exception message: %s", str(e))
        logger.error("%s", "=" * 60, exc_info=True)
        await db.rollback()
        _clear_token_cache()
        logger.info("DB transaction rolled back")
        return {"status": "error", "message": str(e)}


async def save_initial_refresh_token(refresh_token: str, db: AsyncSession) -> dict:
    logger.info("%s", "=" * 60)
    logger.info("SAVE INITIAL REFRESH TOKEN STARTED")
    logger.info("%s", "=" * 60)
    
    try:
        from .fyers_service import FyersService
        fyers_service = FyersService()
        encrypted_refresh_token = fyers_service.encrypt_token(refresh_token)
        
        now = datetime.utcnow()
        
        # Step 1: Deactivate existing tokens
        await db.execute(update(FyersToken).where(FyersToken.is_active == True).values(is_active=False, status="inactive"))

        # Step 2: Ensure ID=1 row exists
        row = (await db.scalars(select(FyersToken).filter(FyersToken.id == 1))).one_or_none()
        
        if row:
            row.access_token = ""
            row.refresh_token = encrypted_refresh_token
            row.refresh_token_expires_at = now + timedelta(days=15)
            row.is_active = True
            row.status = "active"
            row.access_token_saved_at = None
            row.validated_at = None
            db.add(row)
        else:
            row = FyersToken(
                id=1,
                access_token="",
                refresh_token=encrypted_refresh_token,
                refresh_token_expires_at=now + timedelta(days=15),
                created_at=now,
                is_active=True,
                status="active",
            )
            db.add(row)

        # Step 3: Add history (use only fields that exist in FyersTokenHistory model)
        history = FyersTokenHistory(
            access_token_masked="refresh-initiated",
            status="active",
            note="Saved initial refresh token via UI (access token auto-generated)",
        )
        db.add(history)

        await db.commit()
        _clear_token_cache()
        logger.info("SAVE INITIAL REFRESH TOKEN COMPLETED. Generating access token now...")

        refresh_res = await fyers_service.auto_refresh_access_token(db)
        if refresh_res.get("status") == "error":
            error_detail = refresh_res.get("message", "Unknown error")
            logger.error("ACCESS TOKEN GENERATION FAILED after refresh token save: %s", error_detail)
            return {
                "status": "partial",
                "refresh_token_saved": True,
                "access_token_generated": False,
                "message": "Refresh Token saved, but Access Token generation failed.",
                "error": error_detail,
            }

        return {
            "status": "ok",
            "refresh_token_saved": True,
            "access_token_generated": True,
            "message": "Refresh Token saved and Access Token generated successfully.",
        }

    except Exception as e:
        logger.error("SAVE INITIAL REFRESH TOKEN FAILED: %s", str(e), exc_info=True)
        await db.rollback()
        return {
            "status": "error",
            "refresh_token_saved": False,
            "access_token_generated": False,
            "message": "Failed to save Refresh Token.",
            "error": str(e),
        }


async def get_token_status(db: AsyncSession) -> dict[str, Any]:
    row = await get_fyers_token_row(db)
    return {
        "access_token_active": bool(row and row.access_token),
        "access_token_saved_at": row.access_token_saved_at.isoformat() if row and row.access_token_saved_at else None,
        "validated_at": getattr(row, 'validated_at', None).isoformat() if row and getattr(row, 'validated_at', None) else None,
        "status": row.status if row else "no_token",
        "last_error": row.last_error if row else None,
    }


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
    global _FORCE_REFRESH_NEXT_GET

    if _CACHED_TOKEN and _TOKEN_EXPIRY and datetime.utcnow() < _TOKEN_EXPIRY and not _FORCE_REFRESH_NEXT_GET:
        logger.info("TOKEN_CACHE_HIT | source=memory_cache | expiry=%s", _TOKEN_EXPIRY.isoformat() if _TOKEN_EXPIRY else "N/A")
        return _CACHED_TOKEN

    if _FORCE_REFRESH_NEXT_GET:
        logger.info("TOKEN_FORCE_REFRESH | auth failure detected earlier - will attempt refresh via stored refresh token")
        _FORCE_REFRESH_NEXT_GET = False

    logger.info("TOKEN_CACHE_MISS | source=database | reason=cache_miss_or_expired")
    row = await get_fyers_token_row(db)
    if row is None:
        logger.warning("TOKEN_NOT_FOUND | No FyersToken row found in database")
        _clear_token_cache()
        return None

    # Proactive refresh: if no/inactive access OR we have a refresh token and the access is stale (>6h), attempt auto renew
    is_stale = False
    if row.access_token_saved_at:
        saved = row.access_token_saved_at
        if saved.tzinfo is not None:
            saved = saved.replace(tzinfo=None)
        age = (datetime.utcnow() - saved).total_seconds()
        is_stale = age > (6 * 3600)
    if (not row.access_token or row.status != "active" or (row.refresh_token and is_stale)):
        if row.refresh_token:
            logger.info("TOKEN_EXPIRED_OR_STALE | Access token missing/inactive/stale, auto-refreshing via refresh token...")
            from .fyers_service import FyersService
            res = await FyersService().auto_refresh_access_token(db)
            if res.get("status") == "ok":
                row = await get_fyers_token_row(db)
                if row and row.access_token:
                    _set_token_cache(row.access_token, row.access_token_saved_at)
                    return row.access_token
        
        if not row.access_token or row.status != "active":
            logger.warning("TOKEN_NOT_FOUND | FyersToken row exists but access_token is empty and refresh failed")
            _clear_token_cache()
            return None
        
    if _TOKEN_SAVED_AT and row.access_token_saved_at and row.access_token_saved_at < _TOKEN_SAVED_AT:
        logger.warning("TOKEN_GENERATION_MISMATCH | DB token is older than our last known token")

    logger.info("TOKEN_REFRESH_FROM_DB | Access token found in DB, status=%s, saved_at=%s", row.status, row.access_token_saved_at)
    _set_token_cache(row.access_token, row.access_token_saved_at)
    return row.access_token


def get_current_access_token_sync() -> tuple[str | None, str]:
    global _FORCE_REFRESH_NEXT_GET

    if _CACHED_TOKEN and _TOKEN_EXPIRY and datetime.utcnow() < _TOKEN_EXPIRY and not _FORCE_REFRESH_NEXT_GET:
        logger.info("TOKEN_CACHE_HIT | source=memory_cache | expiry=%s", _TOKEN_EXPIRY.isoformat() if _TOKEN_EXPIRY else "N/A")
        return _CACHED_TOKEN, "cache"

    with _TOKEN_LOCK:
        # Double checked locking
        if _CACHED_TOKEN and _TOKEN_EXPIRY and datetime.utcnow() < _TOKEN_EXPIRY and not _FORCE_REFRESH_NEXT_GET:
            logger.info("TOKEN_CACHE_HIT | source=memory_cache | reason=double_check")
            return _CACHED_TOKEN, "cache"

        if _FORCE_REFRESH_NEXT_GET:
            logger.info("TOKEN_FORCE_REFRESH | sync path - auth failure detected, will refresh using refresh token if present")
            _FORCE_REFRESH_NEXT_GET = False

        logger.info("TOKEN_CACHE_MISS | source=database | reason=cache_miss_or_expired")
        from ..db.session import SessionLocal
        try:
            with SessionLocal() as db:
                row = db.query(FyersToken).filter(FyersToken.is_active == True).order_by(FyersToken.created_at.desc()).first()
                if row is None:
                    logger.warning("TOKEN_NOT_FOUND | No FyersToken row found in database")
                    _clear_token_cache()
                    return None, "database"
                
                # Proactive refresh in sync path too (for _client, ltp, candles, etc.)
                is_stale = False
                if row.access_token_saved_at:
                    saved = row.access_token_saved_at
                    if saved.tzinfo is not None:
                        saved = saved.replace(tzinfo=None)
                    age = (datetime.utcnow() - saved).total_seconds()
                    is_stale = age > (6 * 3600)
                if not row.access_token or row.status != "active" or (row.refresh_token and is_stale):
                    if row.refresh_token:
                        logger.info("TOKEN_EXPIRED_OR_STALE | Sync context, auto-refreshing via refresh token...")
                        from .fyers_service import FyersService
                        from ..db.session import AsyncSessionLocal
                        import asyncio
                        
                        async def _do_refresh():
                            async with AsyncSessionLocal() as async_db:
                                return await FyersService().auto_refresh_access_token(async_db)

                        try:
                            # Safely run the async refresh function
                            loop = asyncio.get_running_loop()
                            future = asyncio.run_coroutine_threadsafe(_do_refresh(), loop)
                            res = future.result(timeout=15.0)
                        except RuntimeError:
                            res = asyncio.run(_do_refresh())
                        
                        if res.get("status") == "ok":
                            db.expire_all() # Ensure fresh data
                            row = db.query(FyersToken).filter(FyersToken.is_active == True).order_by(FyersToken.created_at.desc()).first()
                            if row and row.access_token:
                                _set_token_cache(row.access_token, getattr(row, 'access_token_saved_at', None))
                                return row.access_token, "database"
                                
                    if not row.access_token or row.status != "active":
                        logger.warning("TOKEN_NOT_FOUND | FyersToken row exists but access_token is empty and refresh failed")
                        _clear_token_cache()
                        return None, "database"
                
                if _TOKEN_SAVED_AT and row.access_token_saved_at and row.access_token_saved_at < _TOKEN_SAVED_AT:
                    logger.warning("TOKEN_GENERATION_MISMATCH | DB token is older than our last known token")
                    
                logger.info("TOKEN_REFRESH_FROM_DB | Access token found in DB, status=%s, saved_at=%s", row.status, getattr(row, 'access_token_saved_at', None))
                _set_token_cache(row.access_token, getattr(row, 'access_token_saved_at', None))
                return row.access_token, "database"
        except Exception as e:
            logger.error("TOKEN_DB_UNAVAILABLE | Database unavailable during cache refresh: %s", str(e))
            if _CACHED_TOKEN:
                logger.warning("TOKEN_DB_UNAVAILABLE | Falling back to expired cached token due to DB outage")
                return _CACHED_TOKEN, "cache_fallback"
            return None, "error"

