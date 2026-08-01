from sqlalchemy import select, update
from datetime import datetime
import logging
import os
import secrets
import time
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import FyersToken
from ..schemas import FyersTokenCreate, FyersTokenResponse
from ..config import settings


router = APIRouter(prefix="/fyers", tags=["fyers"])
logger = logging.getLogger("app.fyers")


def _require_scheduler_secret(
    request: Request,
    x_scheduler_secret: Optional[str],
) -> None:
    """Same secret gate as POST /scheduler/daily-scan (for server cron jobs)."""
    source_ip = request.client.host if request.client else "unknown"
    timestamp = time.time()
    expected_secret = os.environ.get("SCHEDULER_SECRET")

    if x_scheduler_secret is None:
        logger.warning(
            "FYERS_TOKEN_GENERATE_AUTH_FAILURE | reason=missing_header | source_ip=%s | timestamp=%s",
            source_ip,
            timestamp,
        )
        raise HTTPException(status_code=401, detail="Unauthorized")

    if expected_secret is None or not secrets.compare_digest(
        x_scheduler_secret, expected_secret
    ):
        logger.warning(
            "FYERS_TOKEN_GENERATE_AUTH_FAILURE | reason=invalid_secret_or_unconfigured | source_ip=%s | timestamp=%s",
            source_ip,
            timestamp,
        )
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/token/generate")
async def generate_fyers_token(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_scheduler_secret: Optional[str] = Header(
        default=None, alias="X-Scheduler-Secret"
    ),
):
    """Fully automated Fyers access-token generation for cron jobs.

    Runs OTP → TOTP → PIN → auth_code → access_token and stores the encrypted
    token in DB. Requires header ``X-Scheduler-Secret`` == env ``SCHEDULER_SECRET``.

    Does **not** return the raw access token (masked preview only).

    For manual OAuth (browser login), use:
      1) GET  /fyers/auth/url
      2) POST /fyers/auth/exchange  with {\"auth_code\": \"...\"}
    """
    _require_scheduler_secret(request, x_scheduler_secret)
    source_ip = request.client.host if request.client else "unknown"
    logger.info(
        "FYERS_TOKEN_GENERATE_ACCEPTED | trigger_source=cron | endpoint=/fyers/token/generate | source_ip=%s",
        source_ip,
    )

    from ..services import token_service

    try:
        result = await token_service.generate_and_persist_fyers_token(db)
    except Exception as exc:
        from fyers_token import FyersAuthError, FyersConfigError, FyersConnectionError

        err_type = type(exc).__name__
        err_msg = str(exc)
        if len(err_msg) > 240:
            err_msg = err_msg[:240] + "..."
        logger.warning(
            "FYERS_TOKEN_GENERATE_FAILED | error_type=%s | error=%s",
            err_type,
            err_msg,
        )
        if isinstance(exc, FyersConfigError):
            raise HTTPException(
                status_code=400,
                detail={"status": "Failed", "error_type": err_type, "message": err_msg},
            ) from exc
        if isinstance(exc, FyersAuthError):
            raise HTTPException(
                status_code=502,
                detail={"status": "Failed", "error_type": err_type, "message": err_msg},
            ) from exc
        if isinstance(exc, (FyersConnectionError, TimeoutError)):
            raise HTTPException(
                status_code=504,
                detail={"status": "Failed", "error_type": err_type, "message": err_msg},
            ) from exc
        raise HTTPException(
            status_code=500,
            detail={
                "status": "Failed",
                "error_type": err_type,
                "message": err_msg or "Token generation failed",
            },
        ) from exc

    try:
        status = await token_service.get_token_status(db)
    except Exception:
        status = {}

    body = {
        "status": result.get("status") or "Success",
        "saved_at": result.get("saved_at"),
        "token_preview": result.get("token_preview"),
        "connection_status": status.get("connection_status"),
        "access_token_active": status.get("access_token_active"),
        "expires_at": status.get("expires_at"),
        "message": "Fyers access token generated and stored",
    }
    logger.info(
        "FYERS_TOKEN_GENERATE_SUCCESS | status=%s | preview=%s | connection=%s",
        body.get("status"),
        body.get("token_preview"),
        body.get("connection_status"),
    )
    return JSONResponse(content=body, status_code=200)


@router.post("/token")
async def save_fyers_token(payload: FyersTokenCreate, db: AsyncSession = Depends(get_db)):
    """Save a pre-existing FYERS access token (does NOT generate one)."""
    from ..services import token_service
    
    try:
        result = await token_service.save_access_token(payload.access_token, db)
        return {"status": "success", "message": "Token saved successfully", "token_id": result.get("token_id")}
    except Exception as e:
        logger.error("Failed to save fyers token: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/token/status")
async def fyers_token_status(db: AsyncSession = Depends(get_db)):
    try:
        row = (await db.scalars(select(FyersToken).filter(FyersToken.is_active == True).order_by(FyersToken.created_at.desc()))).first()
        if not row:
            return JSONResponse(content={"has_token": False, "created_at": None, "expires_at": None, "is_active": False})
        return JSONResponse(
            content={
                "has_token": True,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "expires_at": row.expires_at.isoformat() if row.expires_at else None,
                "is_active": bool(row.is_active),
            }
        )
    except Exception as exc:
        logger.exception("Failed to read token status: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/token")
async def clear_fyers_tokens(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(update(FyersToken).values(is_active=False, status="inactive"))
        await db.commit()
        return JSONResponse(content={"message": "Token cleared"})
    except Exception as exc:
        logger.exception("Failed to clear tokens: %s", exc)
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/auth/url")
async def fyers_auth_url():
    """Return the FYERS OAuth authorization URL for frontend redirect."""
    app_id = (settings.fyers_app_id or "").strip().strip('"').strip("'")
    secret_id = (settings.fyers_secret_id or "").strip().strip('"').strip("'")
    redirect_uri = (settings.fyers_redirect_uri or "").strip().strip('"').strip("'")

    oauth_configured = bool(app_id and secret_id)
    if not oauth_configured:
        return JSONResponse(content={
            "oauth_available": False,
            "auth_url": None,
            "callback_url": None,
            "message": "FYERS OAuth credentials not configured. Please set FYERS_APP_ID and FYERS_SECRET_ID in your environment.",
        })

    callback_url = redirect_uri or f"{settings.frontend_url}/fyers/callback"
    params = urlencode({
        "client_id": app_id,
        "redirect_uri": callback_url,
        "response_type": "code",
        "state": "fyers_auth",
    })
    auth_url = f"https://api.fyers.in/api/v2/validate-auth?{params}"
    return JSONResponse(content={
        "oauth_available": True,
        "auth_url": auth_url,
        "callback_url": callback_url,
    })


@router.post("/auth/exchange")
async def fyers_auth_exchange(payload: dict, db: AsyncSession = Depends(get_db)):
    """Exchange a browser OAuth ``auth_code`` for an access token and persist it.

    This is **not** full auto-generation. You must already have ``auth_code``
    from a browser login (or GET /fyers/auth/url flow).

    For cron / fully automated generation, use:
      POST /fyers/token/generate
    with header ``X-Scheduler-Secret``.
    """
    auth_code = payload.get("auth_code", "").strip()
    if not auth_code:
        raise HTTPException(status_code=400, detail="Missing auth_code.")

    from ..services.token_service import exchange_auth_code
    result = await exchange_auth_code(auth_code, db)

    if result.get("status") != "ok":
        raise HTTPException(status_code=502, detail=result.get("message", "FYERS authentication failed."))

    return JSONResponse(content=result)
