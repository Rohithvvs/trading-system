from datetime import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import FyersToken
from ..schemas import FyersTokenCreate, FyersTokenResponse


router = APIRouter(prefix="/fyers", tags=["fyers"])
logger = logging.getLogger("app.fyers")


@router.post("/token")
def save_fyers_token(payload: FyersTokenCreate, db: Session = Depends(get_db)):
    """Save a new FYERS token. Deactivate any existing tokens first."""
    try:
        # Deactivate existing tokens
        try:
            db.query(FyersToken).filter(FyersToken.is_active == True).update({"is_active": False, "status": "inactive"})
            db.commit()
        except Exception:
            db.rollback()

        now = datetime.utcnow()
        # Keep compatibility with older code that expects a single row with id==1.
        existing = db.query(FyersToken).filter(FyersToken.id == 1).one_or_none()
        if existing:
            existing.access_token = payload.access_token
            existing.refresh_token = payload.refresh_token
            existing.created_at = now
            existing.expires_at = payload.expires_at
            existing.is_active = True
            existing.status = "active"
            existing.access_token_saved_at = now
            db.add(existing)
            db.commit()
            db.refresh(existing)
            row = existing
        else:
            row = FyersToken(
                id=1,
                access_token=payload.access_token,
                refresh_token=payload.refresh_token,
                created_at=now,
                expires_at=payload.expires_at,
                is_active=True,
                status="active",
                access_token_saved_at=now,
            )
            db.add(row)
            db.commit()
            db.refresh(row)

        resp = FyersTokenResponse(
            id=row.id,
            access_token=row.access_token,
            created_at=row.created_at,
            expires_at=row.expires_at,
            is_active=bool(row.is_active),
        )
        return JSONResponse(content=jsonable_encoder(resp))
    except Exception as exc:
        logger.exception("Failed to save FYERS token: %s", exc)
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/token/status")
def fyers_token_status(db: Session = Depends(get_db)):
    try:
        row = db.query(FyersToken).filter(FyersToken.is_active == True).order_by(FyersToken.created_at.desc()).first()
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
def clear_fyers_tokens(db: Session = Depends(get_db)):
    try:
        db.query(FyersToken).update({"is_active": False, "status": "inactive"})
        db.commit()
        return JSONResponse(content={"message": "Token cleared"})
    except Exception as exc:
        logger.exception("Failed to clear tokens: %s", exc)
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
