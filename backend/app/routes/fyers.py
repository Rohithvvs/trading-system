from sqlalchemy import select, update
from datetime import datetime
import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import FyersToken
from ..schemas import FyersTokenCreate, FyersTokenResponse
from ..config import settings


router = APIRouter(prefix="/fyers", tags=["fyers"])
logger = logging.getLogger("app.fyers")


@router.post("/token")
async def save_fyers_token(payload: FyersTokenCreate, db: AsyncSession = Depends(get_db)):
    """Save a new FYERS token. Deactivate any existing tokens first."""
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
    """Exchange an OAuth authorization code for an access token and persist it."""
    auth_code = payload.get("auth_code", "").strip()
    if not auth_code:
        raise HTTPException(status_code=400, detail="Missing auth_code.")

    from ..services.token_service import exchange_auth_code
    result = await exchange_auth_code(auth_code, db)

    if result.get("status") != "ok":
        raise HTTPException(status_code=502, detail=result.get("message", "FYERS authentication failed."))

    return JSONResponse(content=result)
