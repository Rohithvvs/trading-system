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
