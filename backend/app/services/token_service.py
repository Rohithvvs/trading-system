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
_TOKEN_CACHE_TTL = timedelta(minutes=int(os.getenv("FYERS_TOKEN_CACHE_MINUTES", "60")))


def _clear_token_cache() -> None:
    global _CACHED_TOKEN, _TOKEN_EXPIRY
    _CACHED_TOKEN = None
    _TOKEN_EXPIRY = None

def has_cached_token() -> bool:
    return bool(_CACHED_TOKEN and _TOKEN_EXPIRY and datetime.utcnow() < _TOKEN_EXPIRY)


def _set_token_cache(access_token: str) -> None:
    global _CACHED_TOKEN, _TOKEN_EXPIRY
    _CACHED_TOKEN = access_token
    _TOKEN_EXPIRY = datetime.utcnow() + _TOKEN_CACHE_TTL

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
        logger.info("Token validation successful.")
        
    except asyncio.TimeoutError:
        logger.error("Token validation failed: FYERS API timeout")
        return {"status": "error", "message": "Validation failed: FYERS API timeout"}
    except (FyersAuthInvalidError, FyersAuthExpiredError) as e:
        logger.error("Token validation failed: %s", str(e))
        return {"status": "error", "message": f"Invalid token: {str(e)}"}
    except FyersAPIError as e:
        logger.error("Token validation failed due to API error: %s", str(e))
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

            # Step 3: Add history
            logger.info("STEP 3: Adding token history entry...")
            history = FyersTokenHistory(
                token_id=1,
                action="save_manual",
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
        _set_token_cache(access_token)
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
        logger.info("SAVE ACCESS TOKEN COMPLETED SUCCESSFULLY")
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
    if _CACHED_TOKEN and _TOKEN_EXPIRY and datetime.utcnow() < _TOKEN_EXPIRY:
        return _CACHED_TOKEN

    logger.info("Reading access token from database")
    row = await get_fyers_token_row(db)
    if row is None:
        logger.warning("No FyersToken row found in database")
        _clear_token_cache()
        return None
    if not row.access_token:
        logger.warning("FyersToken row exists but access_token is empty")
        _clear_token_cache()
        return None
    logger.info("Access token found in DB, status=%s, saved_at=%s", row.status, row.access_token_saved_at)
    _set_token_cache(row.access_token)
    return row.access_token
