from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


SENSITIVE_KEYS = ("token", "secret", "password", "key")


def mask_value(key: str, value: Any) -> Any:
    if not isinstance(value, str) or not any(part in key.lower() for part in SENSITIVE_KEYS):
        return value
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def table_rows(db: Session, table_name: str, limit: int = 25) -> list[dict[str, Any]]:
    result = db.execute(text(f'SELECT * FROM "{table_name}" LIMIT :limit'), {"limit": limit})
    rows: list[dict[str, Any]] = []
    for row in result.mappings().all():
        item = dict(row)
        rows.append({key: mask_value(key, value) for key, value in item.items()})
    return rows


def row_count(db: Session, table_name: str) -> int:
    return int(db.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar() or 0)


def assert_token_stored(db: Session) -> dict[str, Any]:
    rows = table_rows(db, "fyers_tokens", limit=5)
    assert rows, "Expected fyers_tokens to contain an access token row"
    assert rows[0]["access_token"], "Expected fyers_tokens.access_token to be populated"
    return rows[0]


def assert_paper_order_stored(db: Session, symbol: str) -> dict[str, Any]:
    rows = db.execute(
        text("SELECT * FROM paper_trading_orders WHERE symbol = :symbol"),
        {"symbol": symbol},
    ).mappings().all()
    assert rows, f"Expected paper_trading_orders to contain a row for {symbol}"
    return dict(rows[0])


def assert_scan_history_stored(db: Session) -> dict[str, Any]:
    rows = table_rows(db, "scan_history_snapshots", limit=5)
    assert rows, "Expected scan_history_snapshots to contain at least one row"
    return rows[0]


def write_db_snapshot(db: Session, output_dir: Path, name: str, tables: list[str]) -> Path:
    payload = {table: table_rows(db, table, limit=50) for table in tables}
    path = output_dir / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path
