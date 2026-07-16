"""System log API and live stream endpoints."""

from __future__ import annotations

import asyncio
import csv
import io
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_db
from ..models.system_log import SystemLog
from ..services.logger_service import register_ws_client, unregister_ws_client

router = APIRouter(prefix="/api/logs", tags=["logs"])


def serialize_log(log: SystemLog) -> dict[str, Any]:
    return {
        "id": log.id,
        "timestamp": log.timestamp.isoformat() if log.timestamp else None,
        "level": log.level,
        "source": log.source,
        "module": log.module,
        "endpoint": log.endpoint,
        "message": log.message,
        "error_hash": log.error_hash,
        "traceback": log.traceback,
        "structured_data": log.structured_data,
        "correlationId": log.correlationId,
        "userId": log.userId,
        "symbol": log.symbol,
        "orderId": log.orderId,
        "environment": log.environment,
    }


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def build_logs_query(
    *,
    level: str | None,
    source: str | None,
    symbol: str | None,
    correlationId: str | None,
    error_hash: str | None,
    environment: str | None,
    date_from: str | None,
    date_to: str | None,
    search: str | None,
):
    query = select(SystemLog).order_by(desc(SystemLog.timestamp), desc(SystemLog.id))
    if level:
        query = query.where(SystemLog.level == level.upper())
    if source:
        query = query.where(SystemLog.source == source.upper())
    if symbol:
        query = query.where(SystemLog.symbol == symbol)
    if correlationId:
        query = query.where(SystemLog.correlationId == correlationId)
    if error_hash:
        query = query.where(SystemLog.error_hash == error_hash)
    if environment:
        query = query.where(SystemLog.environment == environment.upper())
    start_at = parse_dt(date_from)
    end_at = parse_dt(date_to)
    if start_at:
        query = query.where(SystemLog.timestamp >= start_at)
    if end_at:
        query = query.where(SystemLog.timestamp <= end_at)
    if search:
        query = query.where(SystemLog.message.ilike(f"%{search}%"))
    return query


@router.get("")
async def get_logs(
    limit: int = Query(100, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    level: str | None = None,
    source: str | None = None,
    symbol: str | None = None,
    correlationId: str | None = None,
    error_hash: str | None = None,
    environment: str | None = None,
    date_from: str | None = Query(None, alias="dateFrom"),
    date_to: str | None = Query(None, alias="dateTo"),
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = build_logs_query(
        level=level,
        source=source,
        symbol=symbol,
        correlationId=correlationId,
        error_hash=error_hash,
        environment=environment,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )
    logs = (await db.scalars(query.offset(offset).limit(limit))).all()
    return [serialize_log(log) for log in logs]


async def clear_logs_impl(confirm: str | None, days_old: int, db: AsyncSession):
    if days_old == 0 and confirm not in {"WIPE_ALL", "CONFIRM"}:
        return JSONResponse(
            status_code=400,
            content={"detail": "To delete all logs, pass ?confirm=WIPE_ALL&days_old=0"},
        )
    import time
    from sqlalchemy.exc import OperationalError
    
    if days_old == 0:
        stmt = delete(SystemLog)
    else:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_old)
        stmt = delete(SystemLog).where(SystemLog.timestamp < cutoff)
        
    for attempt in range(5):
        try:
            result = await db.execute(stmt.execution_options(synchronize_session=False))
            await db.commit()
            return {"detail": f"Deleted {result.rowcount or 0} logs.", "deleted": result.rowcount or 0}
        except OperationalError as e:
            await db.rollback()
            if "database is locked" in str(e) and attempt < 4:
                time.sleep(0.5)
                continue
            return JSONResponse(status_code=500, content={"detail": f"Failed to clear logs: Database is locked by the active logging thread. Please try again."})
        except Exception as e:
            await db.rollback()
            return JSONResponse(status_code=500, content={"detail": f"An error occurred: {str(e)}"})


@router.delete("")
async def clear_logs_legacy(
    confirm: str | None = Query("WIPE_ALL"),
    days_old: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    return clear_logs_impl(confirm, days_old, db)


@router.delete("/clear")
async def clear_logs(
    confirm: str | None = Query("WIPE_ALL"),
    days_old: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    return clear_logs_impl(confirm, days_old, db)


@router.get("/export")
async def export_logs(
    format: str = Query("csv", pattern="^(csv|json)$"),
    level: str | None = None,
    source: str | None = None,
    symbol: str | None = None,
    correlationId: str | None = None,
    error_hash: str | None = None,
    environment: str | None = None,
    date_from: str | None = Query(None, alias="dateFrom"),
    date_to: str | None = Query(None, alias="dateTo"),
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = build_logs_query(
        level=level,
        source=source,
        symbol=symbol,
        correlationId=correlationId,
        error_hash=error_hash,
        environment=environment,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )
    rows = [serialize_log(log) for log in (await db.scalars(query)).all()]
    if format == "json":
        return Response(
            json.dumps(rows, default=str),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=system_logs.json"},
        )

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(serialize_log(SystemLog()).keys()))
    writer.writeheader()
    for row in rows:
        writer.writerow({**row, "structured_data": json.dumps(row.get("structured_data"), default=str)})
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=system_logs.csv"},
    )


@router.websocket("/stream")
async def logs_stream(ws: WebSocket):
    await ws.accept()
    client_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=500)
    register_ws_client(client_queue)
    try:
        while True:
            entry = await client_queue.get()
            await ws.send_json(entry)
    except WebSocketDisconnect:
        pass
    finally:
        unregister_ws_client(client_queue)
