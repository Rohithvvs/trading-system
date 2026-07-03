from sqlalchemy import select, update
from datetime import datetime
import logging

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
    from ..services.fyers_service import FyersService
    from ..services.token_service import save_initial_refresh_token
    
    try:
        fyers_service = FyersService()
        
        # New Flow: Only Refresh Token provided
        if not payload.access_token and payload.refresh_token:
            # 1. Save Refresh Token securely
            init_result = await save_initial_refresh_token(payload.refresh_token, db)
            if init_result.get("status") != "ok":
                raise HTTPException(status_code=400, detail=init_result.get("message", "Failed to save initial refresh token"))
                
            # 2. Immediately generate Access Token
            refresh_result = await fyers_service.auto_refresh_access_token(db)
            if refresh_result.get("status") != "ok":
                raise HTTPException(status_code=400, detail=refresh_result.get("message", "Failed to generate access token from refresh token"))
                
            return {"status": "success", "message": "Refresh Token saved and Access Token automatically generated"}

        # Old Flow (Backward compatibility): Access Token provided
        if payload.access_token:
            result = await fyers_service.save_tokens(payload.access_token, payload.refresh_token, db)
            if result.get("status") != "ok":
                raise HTTPException(status_code=400, detail=result.get("message", "Failed to save token"))
            return {"status": "success", "message": "Token saved successfully", "token_id": result.get("token_id")}
            
        raise HTTPException(status_code=400, detail="Must provide either access_token or refresh_token")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to save fyers token: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


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
