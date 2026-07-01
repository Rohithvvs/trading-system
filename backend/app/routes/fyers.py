from sqlalchemy import select, update
from datetime import datetime
import logging
import traceback

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import FyersToken
from ..schemas import FyersTokenCreate, FyersTokenResponse


router = APIRouter(prefix="/fyers", tags=["fyers"])
logger = logging.getLogger("app.fyers")


@router.post("/token")
async def save_fyers_token(payload: FyersTokenCreate, db: AsyncSession = Depends(get_db)):
    """Save a new FYERS token. Deactivate any existing tokens first."""
    print("[TOKEN ROUTE] Request received")
    print(f"[TOKEN ROUTE] access_token present: {bool(payload.access_token)}")
    print(f"[TOKEN ROUTE] refresh_token present: {bool(payload.refresh_token)}")
    from ..services.fyers_service import FyersService
    
    try:
        fyers_service = FyersService()
        result = await fyers_service.save_tokens(payload.access_token, payload.refresh_token, db)
        if result.get("status") != "ok":
            raise HTTPException(status_code=400, detail=result.get("message", "Failed to save token"))
        return {"status": "success", "message": "Token saved successfully", "token_id": result.get("token_id")}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[FYERS SERVICE ERROR] {e}")
        traceback.print_exc()
        logger.error("Failed to save fyers token: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/token/status")
async def fyers_token_status(db: AsyncSession = Depends(get_db)):
    from ..services.fyers_service import FyersService
    try:
        fyers_service = FyersService()
        status = await fyers_service.get_token_status_with_refresh_info(db)
        return JSONResponse(content=status)
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
