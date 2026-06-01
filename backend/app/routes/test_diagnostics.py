from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db.base import Base
from ..db import get_db


router = APIRouter(prefix="/test-diagnostics", tags=["test-diagnostics"])


def require_test_mode() -> None:
    if settings.app_env != "test":
        raise HTTPException(status_code=404, detail="Not found")


def mask_secret(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


@router.post("/reset", dependencies=[Depends(require_test_mode)])
async def reset_test_state(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    for table in reversed(Base.metadata.sorted_tables):
        await db.execute(table.delete())
    await db.execute(text("TRUNCATE TABLE market_data.scan_results"))
    await db.commit()
    return {"status": "ok"}


@router.get("/source-of-truth", dependencies=[Depends(require_test_mode)])
def source_of_truth() -> dict[str, Any]:
    return {
        "database": {
            "kind": "postgresql",
            "url": settings.database_url,
            "survives_backend_restart": True,
            "survives_browser_refresh": True,
            "survives_pc_restart": True,
        },
        "browser_storage": {
            "localStorage_keys": ["scanHistory"],
            "sessionStorage_keys": [],
            "survives_backend_restart": True,
            "survives_browser_refresh": True,
            "survives_pc_restart": "Yes, until browser data is cleared",
        },
        "memory_only": {
            "frontend_react_state": [
                "mainView",
                "theme",
                "scanner filters",
                "current screenerResult",
                "selectedSymbol",
                "paper trading ticket draft",
                "status/error messages",
            ],
            "backend_app_state": ["last_gap_replay"],
            "survives_backend_restart": False,
            "survives_browser_refresh": False,
            "survives_pc_restart": False,
        },
    }


@router.get("/db/tables", dependencies=[Depends(require_test_mode)])
async def db_tables(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    rows = (await db.execute(
        text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' OR table_schema='market_data' ORDER BY table_name")
    )).all()
    table_names = [row[0] for row in rows]
    counts: dict[str, int] = {}
    for name in table_names:
        # Avoid row counts for huge tables in diagnostic routes, but we can try
        try:
            counts[name] = int((await db.execute(text(f'SELECT COUNT(*) FROM "{name}"'))).scalar() or 0)
        except Exception:
            counts[name] = -1
    return {"tables": table_names, "row_counts": counts}


@router.get("/token", dependencies=[Depends(require_test_mode)])
async def token_storage(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    row = (await db.execute(text("SELECT * FROM fyers_tokens ORDER BY id DESC LIMIT 1"))).mappings().first()
    history_count = int((await db.execute(text("SELECT COUNT(*) FROM fyers_token_history"))).scalar() or 0)
    if not row:
        return {"stored_in_db": False, "history_count": history_count, "token_masked": None}
    token = row.get("access_token")
    return {
        "stored_in_db": bool(token),
        "table": "fyers_tokens",
        "history_table": "fyers_token_history",
        "history_count": history_count,
        "status": row.get("status"),
        "token_masked": mask_secret(token),
        "access_token_saved_at": str(row.get("access_token_saved_at")) if row.get("access_token_saved_at") else None,
    }


@router.get("/scan-store", dependencies=[Depends(require_test_mode)])
async def scan_store_status(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    response: dict[str, Any] = {
        "stored_in_db": False,
        "table": "market_data.scan_results",
        "row_count": 0,
    }
    row = (await db.execute(text("SELECT COUNT(*) FROM market_data.scan_results"))).scalar()
    response["row_count"] = int(row if row else 0)
    response["stored_in_db"] = response["row_count"] > 0
    return response
