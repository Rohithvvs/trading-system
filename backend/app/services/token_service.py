from __future__ import annotations

from datetime import datetime
import hashlib
import logging
from typing import Any, List
import os

from sqlalchemy.orm import Session

from ..models import FyersToken, FyersTokenHistory


logger = logging.getLogger("app.token")


def get_fyers_token_row(db: Session) -> FyersToken | None:
    return db.query(FyersToken).filter(FyersToken.id == 1).one_or_none()


def _mask_token(token: str | None) -> str | None:
    if not token:
        return None
    t = str(token)
    if len(t) <= 8:
        return "*" * len(t)
    return f"{t[:4]}...{t[-4:]}"


def save_access_token(access_token: str, db: Session) -> dict:
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
        logger.info("STEP 1: Querying existing FyersToken row from DB...")
        row = db.query(FyersToken).filter(FyersToken.id == 1).one_or_none()
        logger.info("STEP 1 RESULT: row_found=%s", row is not None)

        if row is None:
            logger.info("STEP 2: No existing row. Creating new FyersToken row...")
            row = FyersToken(
                id=1,
                access_token=access_token,
                status="active",
                access_token_saved_at=datetime.utcnow(),
                last_error=None,
            )
            db.add(row)
            logger.info("STEP 2 RESULT: New row created and added to session")
        else:
            logger.info("STEP 2: Updating existing row id=%s, old_status=%s", row.id, row.status)
            row.access_token = access_token
            row.status = "active"
            row.access_token_saved_at = datetime.utcnow()
            row.last_error = None
            logger.info("STEP 2 RESULT: Row updated in session")

        logger.info("STEP 3: Saving FyersTokenHistory entry...")
        masked = "..." + access_token[-8:] if access_token and len(access_token) >= 8 else "too_short"
        history = FyersTokenHistory(
            access_token_masked=masked,
            saved_at=datetime.utcnow(),
            status="active",
            note="Manual save via UI",
        )
        db.add(history)
        logger.info("STEP 3 RESULT: History entry added")

        logger.info("STEP 4: Committing DB transaction...")
        # PRE-COMMIT diagnostic
        logger.info("PRE-COMMIT: token_length=%s", len(access_token) if access_token else 0)

        # Log DB engine/url and file path when using SQLite
        try:
            from ..db.session import engine
            db_url = str(engine.url)
            logger.info("DB ENGINE URL: %s", db_url)
            if db_url.startswith("sqlite:///"):
                db_path = db_url.replace("sqlite:///", "")
                logger.info("DB FILE PATH: %s | exists=%s", db_path, os.path.exists(db_path))
        except Exception:
            pass

        db.commit()
        db.refresh(row)
        logger.info("STEP 4 RESULT: Commit successful. Final status=%s saved_at=%s", row.status, row.access_token_saved_at)

        # POST-COMMIT diagnostics
        logger.info("POST-COMMIT: row_id=%s access_token_saved_at=%s", getattr(row, 'id', None), getattr(row, 'access_token_saved_at', None))

        # Verification read
        try:
            verify_row = db.query(FyersToken).filter(FyersToken.id == 1).one_or_none()
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
        db.rollback()
        logger.info("DB transaction rolled back")
        return {"status": "error", "message": str(e)}


def get_token_status(db: Session) -> dict[str, Any]:
    row = get_fyers_token_row(db)
    return {
        "access_token_active": bool(row and row.access_token),
        "access_token_saved_at": row.access_token_saved_at.isoformat() if row and row.access_token_saved_at else None,
        "status": row.status if row else "no_token",
        "last_error": row.last_error if row else None,
    }


def get_token_history(db: Session, limit: int = 50) -> List[dict[str, Any]]:
    rows = db.query(FyersTokenHistory).order_by(FyersTokenHistory.saved_at.desc()).limit(limit).all()
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


def get_current_access_token(db: Session) -> str | None:
    logger.info("Reading access token from database...")
    row = db.query(FyersToken).filter(FyersToken.id == 1).one_or_none()
    if row is None:
        logger.warning("No FyersToken row found in database")
        return None
    if not row.access_token:
        logger.warning("FyersToken row exists but access_token is empty")
        return None
    logger.info("Access token found in DB, status=%s, saved_at=%s", row.status, row.access_token_saved_at)
    return row.access_token
