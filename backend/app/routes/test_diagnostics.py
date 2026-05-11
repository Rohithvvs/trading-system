from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

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
def reset_test_state(db: Session = Depends(get_db)) -> dict[str, Any]:
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()

    from ..db import scan_store

    db_path = Path(scan_store.DB_PATH)
    if db_path.exists():
        with sqlite3.connect(db_path) as conn:
            conn.execute("DELETE FROM latest_scan")
            conn.commit()
    return {"status": "ok"}


@router.get("/source-of-truth", dependencies=[Depends(require_test_mode)])
def source_of_truth() -> dict[str, Any]:
    return {
        "database": {
            "kind": "sqlite" if settings.database_url.startswith("sqlite") else "external",
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


@router.get("/sqlite/tables", dependencies=[Depends(require_test_mode)])
def sqlite_tables(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    ).all()
    table_names = [row[0] for row in rows]
    counts: dict[str, int] = {}
    for name in table_names:
        counts[name] = int(db.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar() or 0)
    return {"tables": table_names, "row_counts": counts}


@router.get("/sqlite/table/{table_name}", dependencies=[Depends(require_test_mode)])
def sqlite_table_dump(
    table_name: str,
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    exists = db.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name = :name"),
        {"name": table_name},
    ).first()
    if not exists:
        raise HTTPException(status_code=404, detail=f"Table not found: {table_name}")

    result = db.execute(text(f'SELECT * FROM "{table_name}" LIMIT :limit'), {"limit": limit})
    rows = []
    for row in result.mappings().all():
        item = dict(row)
        for key in list(item):
            if "token" in key.lower() or "secret" in key.lower():
                item[key] = mask_secret(item[key])
        rows.append(item)
    return {"table": table_name, "rows": rows}


@router.get("/token", dependencies=[Depends(require_test_mode)])
def token_storage(db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.execute(text("SELECT * FROM fyers_tokens WHERE id = 1")).mappings().first()
    history_count = int(db.execute(text("SELECT COUNT(*) FROM fyers_token_history")).scalar() or 0)
    if not row:
        return {"stored_in_sqlite": False, "history_count": history_count, "token_masked": None}
    token = row.get("access_token")
    return {
        "stored_in_sqlite": bool(token),
        "table": "fyers_tokens",
        "history_table": "fyers_token_history",
        "history_count": history_count,
        "status": row.get("status"),
        "token_masked": mask_secret(token),
        "access_token_saved_at": str(row.get("access_token_saved_at")) if row.get("access_token_saved_at") else None,
    }


@router.get("/scan-store", dependencies=[Depends(require_test_mode)])
def scan_store_status() -> dict[str, Any]:
    from ..db import scan_store

    db_path = Path(scan_store.DB_PATH)
    response: dict[str, Any] = {
        "stored_in_sqlite": False,
        "table": "latest_scan",
        "db_path": str(db_path),
        "db_file_exists": db_path.exists(),
        "row_count": 0,
    }
    if not db_path.exists():
        return response
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS latest_scan (
                id INTEGER PRIMARY KEY,
                payload TEXT NOT NULL,
                saved_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        row = conn.execute("SELECT COUNT(*) FROM latest_scan").fetchone()
    response["row_count"] = int(row[0] if row else 0)
    response["stored_in_sqlite"] = response["row_count"] > 0
    return response
