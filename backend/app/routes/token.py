from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import logging

from ..db import get_db
from ..services import token_service


router = APIRouter(prefix="/api/token", tags=["token"])
logger = logging.getLogger("app.token")


@router.post("/save-access-token")
def save_access_token_route(payload: dict, db: Session = Depends(get_db)):
    logger.info("%s", "=" * 60)
    logger.info("HTTP POST /api/token/save-access-token RECEIVED")
    logger.info("Payload keys     : %s", list(payload.keys()))
    token = payload.get("access_token", "")
    logger.info("Token length     : %s", len(token) if token else 0)

    if not token or len(token) < 10:
        logger.warning("REJECTED: Token empty or too short (len=%s)", len(token) if token else 0)
        raise HTTPException(status_code=400, detail="Access token is empty or too short")

    logger.info("Token accepted. Calling token_service.save_access_token...")
    result = token_service.save_access_token(token, db)
    logger.info("Service result   : %s", result.get("status"))

    if result.get("status") == "error":
        logger.error("Save failed: %s", result.get("message"))
        raise HTTPException(status_code=500, detail=result.get("message"))

    logger.info("HTTP 200 OK returning success")
    return result


@router.get("/status")
def token_status(db: Session = Depends(get_db)):
    try:
        status = token_service.get_token_status(db)
    except Exception as exc:
        logger.exception("Failed to load token status: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    return JSONResponse(content=status)


@router.get("/history")
def token_history(limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    try:
        history = token_service.get_token_history(db, limit=limit)
    except Exception as exc:
        logger.exception("Failed to load token history: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    return JSONResponse(content={"history": history})


@router.get("/diagnostic")
def token_diagnostic(db: Session = Depends(get_db)):
    from ..db.session import engine
    import os
    from ..models import FyersToken

    db_path = str(engine.url).replace("sqlite:///", "")
    row = db.query(FyersToken).filter(FyersToken.id == 1).one_or_none()
    return {
        "db_file_path": db_path,
        "db_file_exists": os.path.exists(db_path),
        "token_row_exists": row is not None,
        "token_is_set": bool(row and row.access_token),
        "token_preview": ("..." + row.access_token[-8:]) if (row and row.access_token and len(row.access_token) >= 8) else None,
        "token_status": row.status if row else "no_row",
        "token_saved_at": str(row.access_token_saved_at) if (row and row.access_token_saved_at) else None,
    }
