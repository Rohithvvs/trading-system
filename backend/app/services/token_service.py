from __future__ import annotations
from sqlalchemy import select, update
import base64
import json

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import logging
from typing import Any, List
import os

from sqlalchemy.ext.asyncio import AsyncSession
from ..config import settings
from ..models import FyersToken, FyersTokenHistory
from ..utils.datetime_utils import ensure_utc as _ensure_utc, utc_now

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
    expiry = _ensure_utc(_TOKEN_EXPIRY)
    return bool(
        _CACHED_TOKEN and expiry and utc_now() < expiry
    )


def _set_token_cache(access_token: str, saved_at: datetime | None = None) -> None:
    global _CACHED_TOKEN, _TOKEN_EXPIRY, _TOKEN_SAVED_AT
    _CACHED_TOKEN = access_token
    _TOKEN_EXPIRY = utc_now() + _TOKEN_CACHE_TTL
    if saved_at is not None:
        _TOKEN_SAVED_AT = _ensure_utc(saved_at)

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
    logger.info("Timestamp (UTC)  : %s", utc_now().isoformat())

    # Live broker validation — skip only in automated test env (APP_ENV=test)
    # so integration suites stay offline and deterministic.
    if (getattr(settings, "app_env", "") or "").lower() == "test":
        logger.info("TOKEN_VALIDATION_SKIPPED | reason=app_env_test")
    else:
        try:
            import asyncio
            from .fyers_service import FyersService
            from .fyers_service import (
                FyersAuthInvalidError,
                FyersAuthExpiredError,
                FyersAPIError,
            )

            logger.info("Validating token against FYERS API...")
            fyers_service = FyersService()
            await asyncio.wait_for(
                asyncio.to_thread(fyers_service.validate_token_sync, access_token),
                timeout=15.0,
            )
            logger.info(
                "TOKEN_AUTH_RECOVERED | Token validation successful. Auth recovered."
            )

        except asyncio.TimeoutError:
            logger.error(
                "TOKEN_VALIDATION_FAILURE | Token validation failed: FYERS API timeout"
            )
            return {
                "status": "error",
                "message": "Validation failed: FYERS API timeout",
            }
        except (FyersAuthInvalidError, FyersAuthExpiredError) as e:
            logger.error("TOKEN_VALIDATION_FAILURE | Token validation failed: %s", e)
            return {
                "status": "error",
                "message": "Invalid token. Please check and try again.",
            }
        except FyersAPIError as e:
            logger.error(
                "TOKEN_VALIDATION_FAILURE | Token validation failed due to API error: %s",
                e,
            )
            return {
                "status": "error",
                "message": "Token validation failed due to API error.",
            }
        except Exception as e:
            logger.error("Unexpected error validating token: %s", e, exc_info=True)
            return {"status": "error", "message": "Token validation failed."}

    try:
        async with db.begin():
            now = utc_now()
            
            # Step 1: Deactivate existing tokens
            logger.info("STEP 1: Deactivating existing tokens...")
            await db.execute(update(FyersToken).where(FyersToken.is_active == True).values(is_active=False, status="inactive"))
            logger.info("STEP 1 RESULT: Deactivated")

            # Parse JWT expiry
            expires_at = _decode_jwt_expiry(access_token)

            # Step 2: Upsert ID=1 row (dialect-safe: SQLite tests + Postgres prod)
            logger.info("STEP 2: Upserting ID=1 row...")
            stored = _encrypt_for_storage(access_token)
            row = (
                await db.scalars(select(FyersToken).filter(FyersToken.id == 1))
            ).first()
            if row is None:
                row = FyersToken(
                    id=1,
                    access_token=stored,
                    created_at=now,
                    is_active=True,
                    # Unified monitoring status (Sprint 4): Success | Failed | inactive
                    status="Success",
                    last_error=None,
                    access_token_saved_at=now,
                    validated_at=now,
                    expires_at=expires_at,
                )
                db.add(row)
            else:
                row.access_token = stored
                row.is_active = True
                row.status = "Success"
                row.last_error = None  # clear automation/job failure when UI save succeeds
                row.access_token_saved_at = now
                row.validated_at = now
                row.expires_at = expires_at
            await db.flush()

            # Step 3: Add history
            logger.info("STEP 3: Adding token history entry...")
            masked = _mask_token(access_token)
            history = FyersTokenHistory(
                access_token_masked=masked,
                saved_at=now,
                status="Success",
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
        IST = ZoneInfo("Asia/Kolkata")
        saved = _ensure_utc(row.access_token_saved_at)
        if saved is not None:
            local = saved.astimezone(IST)
            saved_date = local.strftime("%d %b %Y")
            saved_time = local.strftime("%I:%M:%S %p").lstrip("0")
        else:
            saved_date = None
            saved_time = None
        return {"status": "ok", "saved_at": str(row.access_token_saved_at), "saved_date": saved_date, "saved_time": saved_time}

    except Exception as e:
        logger.error("%s", "=" * 60)
        logger.error("SAVE ACCESS TOKEN FAILED")
        logger.error("Exception type   : %s", type(e).__name__)
        logger.error("Exception message: %s", e)
        logger.error("%s", "=" * 60, exc_info=True)
        try:
            rollback = getattr(db, "rollback", None)
            if rollback is not None:
                result = rollback()
                if hasattr(result, "__await__"):
                    await result
        except Exception:
            pass
        _clear_token_cache()
        return {"status": "error", "message": "Unable to save access token."}


def _has_usable_stored_token(row: FyersToken | None) -> bool:
    """True when ciphertext is present (empty first-run failure placeholder is not usable)."""
    if row is None:
        return False
    raw = row.access_token
    return bool(raw and str(raw).strip())


def _derive_connection_status(
    *,
    row_status: str | None,
    has_token: bool,
    expires_in_seconds: int | None,
) -> str:
    """Unify UI-save (active/inactive) and automation (Success/Failed) for consumers.

    - active / Success → Connected (or Expired)
    - Failed with prior token still stored → Connected (or Expired) so trading UI is not false-red
    - no token / inactive / missing → Disconnected
    """
    if not has_token:
        return "Disconnected"
    st = (row_status or "").strip().lower()
    if st in ("inactive", "no_token"):
        return "Disconnected"
    # active | success | failed-with-token | other non-empty with token
    if expires_in_seconds is not None and expires_in_seconds <= 0:
        return "Expired"
    if expires_in_seconds is not None and expires_in_seconds < 3600:
        return "Expiring Soon"
    if st in ("active", "success", "failed") or has_token:
        return "Connected"
    return "Disconnected"


async def get_token_status(db: AsyncSession) -> dict[str, Any]:
    """
    DB-only token status. Does NOT call FYERS.
    Cached in-process for 5 minutes to avoid repeated DB hits on every page navigation.

    Additive Sprint 4 fields (non-breaking):
      - connection_status: normalized Connected/Expired/Disconnected
      - automation_metrics: in-process job counters (success/failure totals)
    """
    from ..core.response_cache import cache_get, cache_set

    cache_key = "token_status"
    hit = cache_get(cache_key)
    if hit is not None:
        logger.info("TOKEN_STATUS_CACHE_HIT | source=memory")
        # Always refresh live automation counters (cheap, not from DB).
        hit = dict(hit)
        hit["automation_metrics"] = get_token_automation_metrics()
        return hit

    # Prefer active token; fall back to singleton id=1 so Failed/inactive monitoring is visible.
    row = await get_fyers_token_row(db)
    if row is None:
        row = (
            await db.scalars(select(FyersToken).where(FyersToken.id == 1))
        ).first()
    now = utc_now()
    expires_at = None
    expires_in_seconds = None
    token_masked = None
    has_token = _has_usable_stored_token(row)
    if row and has_token:
        plain = _decrypt_from_storage(row.access_token)
        # Treat decrypt failure as inactive for consumers
        if not plain or not str(plain).strip():
            has_token = False
        else:
            token_masked = _mask_token(plain)
            expires_at = row.expires_at
            if expires_at is None:
                expires_at = _decode_jwt_expiry(plain)
            if expires_at:
                try:
                    exp = _ensure_utc(expires_at)
                    remaining = (exp - now).total_seconds() if exp is not None else 0
                except Exception:
                    remaining = 0
                expires_in_seconds = max(0, int(remaining))
    elif row and row.access_token:
        # Non-empty garbage / undecryptable — still mask for UI without claiming active
        token_masked = _mask_token("stored")

    row_status = row.status if row else "no_token"
    connection_status = _derive_connection_status(
        row_status=row_status,
        has_token=has_token,
        expires_in_seconds=expires_in_seconds,
    )

    status = {
        "access_token_active": has_token,
        "access_token_saved_at": row.access_token_saved_at.isoformat() if row and row.access_token_saved_at else None,
        "validated_at": getattr(row, 'validated_at', None).isoformat() if row and getattr(row, 'validated_at', None) else None,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "expires_in_seconds": expires_in_seconds,
        "status": row_status,
        "connection_status": connection_status,
        "last_error": row.last_error if row else None,
        "token_masked": token_masked,
        "automation_metrics": get_token_automation_metrics(),
        # Never include full access_token
    }
    # Cache DB-derived fields without freezing metrics forever
    cache_payload = {k: v for k, v in status.items() if k != "automation_metrics"}
    cache_set(cache_key, cache_payload, ttl_seconds=300.0)
    logger.info(
        "TOKEN_STATUS_CACHE_MISS | source=database | status=%s | connection_status=%s",
        status.get("status"),
        connection_status,
    )
    return status


async def get_token_history(db: AsyncSession, limit: int = 50) -> List[dict[str, Any]]:
    IST = ZoneInfo("Asia/Kolkata")
    rows = (await db.scalars(select(FyersTokenHistory).order_by(FyersTokenHistory.saved_at.desc()).limit(limit))).all()
    result: List[dict[str, Any]] = []
    for r in rows:
        saved_at = _ensure_utc(r.saved_at)
        saved_date: str | None = None
        saved_time: str | None = None
        if saved_at is not None:
            local = saved_at.astimezone(IST)
            saved_date = local.strftime("%d %b %Y")
            saved_time = local.strftime("%I:%M:%S %p").lstrip("0")
        result.append({
            "id": r.id,
            "access_token_masked": r.access_token_masked,
            "saved_at": r.saved_at.isoformat() if r.saved_at else None,
            "saved_date": saved_date,
            "saved_time": saved_time,
            "status": r.status,
            "note": r.note,
        })
    return result


async def get_current_access_token(db: AsyncSession) -> str | None:
    now = utc_now()
    expiry = _ensure_utc(_TOKEN_EXPIRY)
    if _CACHED_TOKEN and expiry and now < expiry:
        logger.info(
            "TOKEN_CACHE_HIT | source=memory_cache | expiry=%s",
            expiry.isoformat() if expiry else "N/A",
        )
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

    saved_at = _ensure_utc(row.access_token_saved_at)
    known_saved = _ensure_utc(_TOKEN_SAVED_AT)
    if known_saved and saved_at and saved_at < known_saved:
        logger.warning(
            "TOKEN_GENERATION_MISMATCH | DB token is older than our last known token"
        )

    logger.info(
        "TOKEN_REFRESH_FROM_DB | Access token found in DB, status=%s, saved_at=%s",
        row.status,
        row.access_token_saved_at,
    )
    _set_token_cache(plain, row.access_token_saved_at)
    return plain


def get_current_access_token_sync() -> tuple[str | None, str]:
    now = utc_now()
    expiry = _ensure_utc(_TOKEN_EXPIRY)
    if _CACHED_TOKEN and expiry and now < expiry:
        logger.info(
            "TOKEN_CACHE_HIT | source=memory_cache | expiry=%s",
            expiry.isoformat() if expiry else "N/A",
        )
        return _CACHED_TOKEN, "cache"

    with _TOKEN_LOCK:
        now = utc_now()
        expiry = _ensure_utc(_TOKEN_EXPIRY)
        if _CACHED_TOKEN and expiry and now < expiry:
            logger.info("TOKEN_CACHE_HIT | source=memory_cache | reason=double_check")
            return _CACHED_TOKEN, "cache"

        logger.info("TOKEN_CACHE_MISS | source=database | reason=cache_miss_or_expired")
        from ..db.session import SessionLocal
        try:
            with SessionLocal() as db:
                row = (
                    db.query(FyersToken)
                    .filter(FyersToken.is_active == True)
                    .order_by(FyersToken.created_at.desc())
                    .first()
                )
                if row is None:
                    logger.warning("TOKEN_NOT_FOUND | No FyersToken row found in database")
                    _clear_token_cache()
                    return None, "database"
                if not row.access_token:
                    logger.warning(
                        "TOKEN_NOT_FOUND | FyersToken row exists but access_token is empty"
                    )
                    _clear_token_cache()
                    return None, "database"
                plain = _decrypt_from_storage(row.access_token)
                if not plain:
                    logger.warning(
                        "TOKEN_NOT_FOUND | Stored token could not be decrypted"
                    )
                    _clear_token_cache()
                    return None, "database"

                saved_at = _ensure_utc(getattr(row, "access_token_saved_at", None))
                known_saved = _ensure_utc(_TOKEN_SAVED_AT)
                if known_saved and saved_at and saved_at < known_saved:
                    logger.warning(
                        "TOKEN_GENERATION_MISMATCH | DB token is older than our last known token"
                    )

                logger.info(
                    "TOKEN_REFRESH_FROM_DB | Access token found in DB, status=%s, saved_at=%s",
                    row.status,
                    getattr(row, "access_token_saved_at", None),
                )
                _set_token_cache(plain, getattr(row, "access_token_saved_at", None))
                return plain, "database"
        except Exception as e:
            logger.error(
                "TOKEN_DB_UNAVAILABLE | Database unavailable during cache refresh: %s",
                str(e),
            )
            if _CACHED_TOKEN:
                logger.warning(
                    "TOKEN_DB_UNAVAILABLE | Falling back to expired cached token due to DB outage"
                )
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

    now = utc_now()
    try:
        # Dialect-safe upsert (SQLite tests + Postgres prod) — no Postgres-only ON CONFLICT.
        async with db.begin():
            await db.execute(
                update(FyersToken)
                .where(FyersToken.is_active == True)  # noqa: E712
                .values(is_active=False, status="inactive")
            )
            stored = _encrypt_for_storage(access_token)
            row = (
                await db.scalars(select(FyersToken).where(FyersToken.id == 1))
            ).first()
            if row is None:
                row = FyersToken(
                    id=1,
                    access_token=stored,
                    created_at=now,
                    is_active=True,
                    status="Success",
                    last_error=None,
                    access_token_saved_at=now,
                    validated_at=now,
                    expires_at=expires_at,
                )
                db.add(row)
            else:
                row.access_token = stored
                row.is_active = True
                row.status = "Success"
                row.last_error = None
                row.access_token_saved_at = now
                row.validated_at = now
                row.expires_at = expires_at
            await db.flush()
            masked = _mask_token(access_token)
            history = FyersTokenHistory(
                access_token_masked=masked,
                saved_at=now,
                status="Success",
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

    now = utc_now()
    if expires_at:
        expires_at = _ensure_utc(expires_at)
        remaining = (expires_at - now).total_seconds() if expires_at is not None else 0
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


# ---------------------------------------------------------------------------
# Sprint 4 automation hardening + ops improvements
# ---------------------------------------------------------------------------
# Bound external generation so the job cannot hang indefinitely (edge: network).
# Bound DB commits so pool stalls surface as timeouts rather than silent hangs.
_TOKEN_GEN_TIMEOUT_SEC = float(os.getenv("FYERS_TOKEN_JOB_TIMEOUT_SEC", "180") or "180")
_DB_WRITE_TIMEOUT_SEC = float(os.getenv("FYERS_TOKEN_DB_WRITE_TIMEOUT_SEC", "30") or "30")
_LAST_ERROR_MAX_LEN = 2000
# Non-nullable access_token: empty string is intentional so access_token_active stays False.
_NO_TOKEN_PLACEHOLDER = ""

# Lightweight in-process counters (process-local; not a distributed metrics backend).
_JOB_METRICS_LOCK = threading.Lock()
_JOB_METRICS: dict[str, Any] = {
    "success_total": 0,
    "failure_total": 0,
    "last_outcome": None,
    "last_elapsed_ms": None,
    "last_error_type": None,
    "last_at": None,
}


def get_token_automation_metrics() -> dict[str, Any]:
    """Snapshot of in-process automation job counters (for ops / status API)."""
    with _JOB_METRICS_LOCK:
        return dict(_JOB_METRICS)


def _record_job_metric(
    outcome: str,
    *,
    elapsed_ms: int | None = None,
    error_type: str | None = None,
) -> None:
    with _JOB_METRICS_LOCK:
        if outcome == "Success":
            _JOB_METRICS["success_total"] = int(_JOB_METRICS["success_total"]) + 1
        else:
            _JOB_METRICS["failure_total"] = int(_JOB_METRICS["failure_total"]) + 1
        _JOB_METRICS["last_outcome"] = outcome
        _JOB_METRICS["last_elapsed_ms"] = elapsed_ms
        _JOB_METRICS["last_error_type"] = error_type
        _JOB_METRICS["last_at"] = utc_now().isoformat()


def mask_access_token_preview(token: str | None) -> str | None:
    """Public helper for CLI/UI previews — never returns full secret material."""
    return _mask_token(token)


def _truncate_error_message(exc: BaseException) -> str:
    """Cap last_error size to protect the DB column and log sinks (no secrets expected)."""
    msg = str(exc).strip() if str(exc).strip() else exc.__class__.__name__
    if len(msg) > _LAST_ERROR_MAX_LEN:
        return msg[: _LAST_ERROR_MAX_LEN - 3] + "..."
    return msg


async def _invalidate_token_status_cache() -> None:
    try:
        from ..core.response_cache import cache_invalidate
        cache_invalidate("token_status")
    except Exception:
        pass


async def _rollback_quietly(db: AsyncSession) -> None:
    try:
        if db.in_transaction():
            await db.rollback()
    except Exception:
        pass


async def _commit_with_timeout(db: AsyncSession) -> None:
    """Commit with a hard timeout so DB unavailability does not hang the job."""
    import asyncio

    timeout = max(1.0, _DB_WRITE_TIMEOUT_SEC)
    await asyncio.wait_for(db.commit(), timeout=timeout)


async def _load_singleton_for_update(db: AsyncSession) -> FyersToken | None:
    """Load id=1 with row lock when the dialect supports it (Postgres)."""
    try:
        return (
            await db.scalars(
                select(FyersToken).where(FyersToken.id == 1).with_for_update()
            )
        ).first()
    except Exception:
        return (
            await db.scalars(select(FyersToken).where(FyersToken.id == 1))
        ).first()


async def _record_generation_failure(db: AsyncSession, exc: BaseException) -> None:
    """Update monitoring fields on failure without wiping a prior valid token.

    Uses plain commit (no nested ``begin()``) so caller-owned sessions work.
    On DB unavailability: logs ERROR and returns — original job exception still propagates.
    """
    now = utc_now()
    err_text = _truncate_error_message(exc)
    try:
        await _rollback_quietly(db)
        row = await _load_singleton_for_update(db)

        if row is None:
            # Placeholder only — no prior credential to preserve.
            # Empty access_token keeps get_current_access_token / access_token_active false.
            row = FyersToken(
                id=1,
                access_token=_NO_TOKEN_PLACEHOLDER,
                status="Failed",
                last_error=err_text,
                access_token_saved_at=now,
                is_active=False,
                created_at=now,
            )
            db.add(row)
        else:
            # Preserve access_token and is_active so trading can keep using last good token.
            row.status = "Failed"
            row.last_error = err_text
            row.access_token_saved_at = now
            # Never activate a missing/placeholder credential on failure.
            if not row.access_token:
                row.is_active = False

        await _commit_with_timeout(db)
        await _invalidate_token_status_cache()
        logger.warning(
            "TOKEN_PERSISTENCE_JOB | outcome=Failed | monitoring_persisted=true | error_type=%s | last_error=%s | metrics=%s",
            type(exc).__name__,
            err_text,
            get_token_automation_metrics(),
        )
    except Exception as db_err:
        logger.error(
            "TOKEN_PERSISTENCE_JOB | outcome=Failed | monitoring_persisted=false | "
            "error_type=%s | db_error_type=%s | db_error=%s | metrics=%s",
            type(exc).__name__,
            type(db_err).__name__,
            db_err,
            get_token_automation_metrics(),
            exc_info=True,
        )
        await _rollback_quietly(db)


async def generate_and_persist_fyers_token(db: AsyncSession) -> dict[str, Any]:
    """Generate a Fyers access token and persist it with monitoring fields.

    Success (single atomic commit — FR-007):
      - encrypts token via project crypto
      - upserts singleton ``fyers_tokens.id=1``
      - ``status="Success"``, ``last_error=NULL``, ``access_token_saved_at=now``
      - history note identifies automation (not UI)

    Failure:
      - records ``status="Failed"`` + ``last_error`` without wiping prior token
      - re-raises the original exception for CLI/orchestrator exit codes

    Does **not** re-validate against live FYERS (generation is authoritative).
    Does **not** use the UI manual-save path (avoids validation + wrong history note).
    """
    import asyncio
    import sys
    from pathlib import Path

    # fyers_token.py lives at repo root; ensure import works when cwd is backend/.
    _repo_root = Path(__file__).resolve().parents[3]
    if str(_repo_root) not in sys.path:
        sys.path.insert(0, str(_repo_root))

    from fyers_token import generate_fyers_access_token

    job_started = utc_now()
    logger.info(
        "TOKEN_PERSISTENCE_JOB | outcome=start | gen_timeout_sec=%s | db_write_timeout_sec=%s | started_at=%s",
        _TOKEN_GEN_TIMEOUT_SEC,
        _DB_WRITE_TIMEOUT_SEC,
        job_started.isoformat(),
    )
    try:
        # Sync generator off the event loop; retry policy lives inside the generator.
        # Hard timeout prevents indefinite hang if broker/network stalls beyond retry budget.
        gen_timeout = max(5.0, _TOKEN_GEN_TIMEOUT_SEC)
        try:
            token = await asyncio.wait_for(
                asyncio.to_thread(generate_fyers_access_token),
                timeout=gen_timeout,
            )
        except asyncio.TimeoutError as te:
            raise TimeoutError(
                f"Token generation exceeded {gen_timeout:.0f}s job timeout"
            ) from te

        if not token or not str(token).strip():
            raise RuntimeError("Token generation returned an empty access token")

        now = utc_now()
        stored = _encrypt_for_storage(str(token))
        expires_at = _decode_jwt_expiry(str(token))
        masked = _mask_token(str(token))

        # Ensure a clean transaction boundary for the atomic write.
        await _rollback_quietly(db)

        # Single transaction: deactivate peers, upsert id=1 with Success, history.
        row = await _load_singleton_for_update(db)

        await db.execute(
            update(FyersToken)
            .where(FyersToken.is_active == True, FyersToken.id != 1)  # noqa: E712
            .values(is_active=False, status="inactive")
        )

        if row is None:
            row = FyersToken(
                id=1,
                access_token=stored,
                created_at=now,
                is_active=True,
                status="Success",
                last_error=None,
                access_token_saved_at=now,
                validated_at=now,
                expires_at=expires_at,
            )
            db.add(row)
        else:
            row.access_token = stored
            row.is_active = True
            row.status = "Success"
            row.last_error = None
            row.access_token_saved_at = now
            row.validated_at = now
            row.expires_at = expires_at

        db.add(
            FyersTokenHistory(
                access_token_masked=masked,
                saved_at=now,
                status="Success",
                note="Automated headless token generation",
            )
        )
        await _commit_with_timeout(db)

        # Cache only after durable commit (no cache write on failed persist).
        _set_token_cache(str(token), now)
        await _invalidate_token_status_cache()

        elapsed_ms = int((utc_now() - job_started).total_seconds() * 1000)
        _record_job_metric("Success", elapsed_ms=elapsed_ms)
        logger.info(
            "TOKEN_PERSISTENCE_JOB | outcome=Success | monitoring_persisted=true | "
            "elapsed_ms=%s | token_preview=%s | saved_at=%s | metrics=%s",
            elapsed_ms,
            masked,
            now.isoformat(),
            get_token_automation_metrics(),
        )
        return {
            "status": "Success",
            # ISO string keeps CLI/logs/JSON consumers safe (datetime is not JSON-native).
            "saved_at": now.isoformat(),
            "token_preview": masked,
        }

    except Exception as exc:
        elapsed_ms = int((utc_now() - job_started).total_seconds() * 1000)
        _record_job_metric(
            "Failed",
            elapsed_ms=elapsed_ms,
            error_type=type(exc).__name__,
        )
        # Expected job failures are WARNING; DB write issues log ERROR inside helper.
        logger.warning(
            "TOKEN_PERSISTENCE_JOB | outcome=Failed | error_type=%s | error=%s | elapsed_ms=%s",
            type(exc).__name__,
            _truncate_error_message(exc),
            elapsed_ms,
        )
        await _record_generation_failure(db, exc)
        raise


