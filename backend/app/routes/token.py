from sqlalchemy import select, update
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from ..db import get_db
from ..schemas import FyersTokenCreate
from ..services import token_service


router = APIRouter(prefix="/api/token", tags=["token"])
logger = logging.getLogger("app.token")


@router.post("/save-access-token")
async def save_access_token_route(payload: FyersTokenCreate, db: AsyncSession = Depends(get_db)):
    logger.info("=" * 50)
    logger.info("POST /api/token HIT")
    logger.info("=" * 50)

    token = payload.access_token
    if not token or not token.strip():
        logger.error("Rejecting token payload: empty access_token field")
        raise HTTPException(status_code=400, detail="access_token cannot be empty")

    logger.info("Token accepted. Calling token_service.save_access_token...")
    result = await token_service.save_access_token(token, db)
    logger.info("Service result   : %s", result.get("status"))

    if result.get("status") == "error":
        logger.error("Save failed: %s", result.get("message"))
        raise HTTPException(status_code=500, detail=result.get("message"))

    logger.info("HTTP 200 OK returning success")
    return result


@router.get("/status")
async def token_status(db: AsyncSession = Depends(get_db)):
    try:
        status = await token_service.get_token_status(db)
    except Exception as exc:
        logger.exception("Failed to load token status: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    return JSONResponse(content=status)


@router.get("/history")
async def token_history(limit: int = Query(50, ge=1, le=500), db: AsyncSession = Depends(get_db)):
    try:
        history = await token_service.get_token_history(db, limit=limit)
    except Exception as exc:
        logger.exception("Failed to load token history: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    return JSONResponse(content={"history": history})


@router.get("/diagnostic")
async def token_diagnostic(db: AsyncSession = Depends(get_db)):
    
    from ..models import FyersToken
    from ..db.session import engine

    row = (await db.scalars(select(FyersToken).filter(FyersToken.is_active == True).order_by(FyersToken.created_at.desc()))).first()
    return {
        "db_url": str(engine.url),
        "token_row_exists": row is not None,
        "token_is_set": bool(row and row.access_token),
        "token_preview": ("..." + row.access_token[-8:]) if (row and row.access_token and len(row.access_token) >= 8) else None,
        "token_status": row.status if row else "no_row",
        "token_saved_at": str(row.access_token_saved_at) if (row and row.access_token_saved_at) else None,
    }
