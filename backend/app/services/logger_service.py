"""Centralized async logging service for the trading system."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import platform
import re
import traceback as traceback_module
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..db.session import SessionLocal
from ..models.system_log import SystemLog

SENSITIVE_FIELDS = {
    "access_token",
    "refresh_token",
    "client_id",
    "client_secret",
    "password",
    "pin",
    "auth_code",
}

SENSITIVE_PATTERN = re.compile(
    r'(?i)(access_token|refresh_token|client_id|client_secret|password|pin|auth_code)'
    r'(\s*[:=]\s*|"\s*:\s*")'
    r'([^,\s&"}]+)'
)

MASK = "***MASKED***"
MAX_QUEUE_SIZE = 10_000
DB_BATCH_SIZE = 50
WS_QUEUE_SIZE = 500

_ws_clients: list[asyncio.Queue[dict[str, Any]]] = []


def register_ws_client(queue: asyncio.Queue[dict[str, Any]]) -> None:
    _ws_clients.append(queue)


def unregister_ws_client(queue: asyncio.Queue[dict[str, Any]]) -> None:
    try:
        _ws_clients.remove(queue)
    except ValueError:
        pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def mask_sensitive_data(value: Any) -> Any:
    if isinstance(value, dict):
        masked: dict[Any, Any] = {}
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_FIELDS:
                masked[key] = MASK
            else:
                masked[key] = mask_sensitive_data(item)
        return masked
    if isinstance(value, list):
        return [mask_sensitive_data(item) for item in value]
    if isinstance(value, tuple):
        return [mask_sensitive_data(item) for item in value]
    if isinstance(value, str):
        return SENSITIVE_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}{MASK}", value)
    return value


def generate_error_hash(traceback_str: str | None, endpoint: str | None = None) -> str | None:
    if not traceback_str:
        return None
    fingerprint = f"{endpoint or ''}\n{traceback_str.strip()}".encode("utf-8", errors="replace")
    return hashlib.sha256(fingerprint).hexdigest()[:16]


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class LoggingService:
    _instance: "LoggingService | None" = None

    def __new__(cls) -> "LoggingService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        self._worker_task: asyncio.Task[None] | None = None
        self._shutting_down = False
        self._environment = os.getenv("ENVIRONMENT", os.getenv("APP_ENV", "DEV")).upper()
        self._fallback_path = Path(__file__).resolve().parents[2] / "fallback_logs.jsonl"

    @property
    def queue(self) -> asyncio.Queue[dict[str, Any]]:
        return self._queue

    async def start(self) -> None:
        self._ensure_queue_for_current_loop()
        if self._worker_task is None or self._worker_task.done():
            self._shutting_down = False
            self._worker_task = asyncio.create_task(self._flush_worker())

    async def shutdown(self) -> None:
        self._shutting_down = True
        try:
            await asyncio.wait_for(self.flush_now(), timeout=5.0)
        except asyncio.TimeoutError:
            pass
        if self._worker_task and not self._worker_task.done():
            try:
                await asyncio.wait_for(self._worker_task, timeout=5.0)
            except asyncio.TimeoutError:
                self._worker_task.cancel()

    async def flush_now(self) -> None:
        while not self._queue.empty():
            batch = self._drain_batch(DB_BATCH_SIZE)
            if not batch:
                break
            await self._persist_batch(batch)
            for _ in batch:
                self._queue.task_done()

    def log(
        self,
        *,
        level: str,
        source: str,
        module: str,
        message: str,
        endpoint: str | None = None,
        traceback_str: str | None = None,
        structured_data: dict[str, Any] | None = None,
        correlationId: str | None = None,
        userId: str | None = None,
        symbol: str | None = None,
        orderId: str | None = None,
        error_hash: str | None = None,
    ) -> None:
        normalized_level = level.upper()
        masked_traceback = mask_sensitive_data(traceback_str) if traceback_str else None
        masked_message = mask_sensitive_data(message)
        masked_data = mask_sensitive_data(structured_data or {})

        if normalized_level == "CRITICAL":
            masked_data = {
                **masked_data,
                "emergency_snapshot": self._emergency_snapshot(),
            }

        entry = {
            "timestamp": utc_now().isoformat(),
            "level": normalized_level,
            "source": source.upper(),
            "module": module,
            "endpoint": endpoint,
            "message": masked_message,
            "error_hash": error_hash or generate_error_hash(masked_traceback, endpoint),
            "traceback": masked_traceback,
            "structured_data": masked_data or None,
            "correlationId": correlationId,
            "userId": userId,
            "symbol": symbol,
            "orderId": orderId,
            "environment": self._environment,
        }

        try:
            self._queue.put_nowait(entry)
        except asyncio.QueueFull:
            self._write_fallback(entry)

        self._broadcast(entry)

    def log_error(
        self,
        module: str,
        message: str,
        exc: Exception | None = None,
        endpoint: str | None = None,
        correlationId: str | None = None,
        structured_data: dict[str, Any] | None = None,
        source: str = "API",
    ) -> None:
        traceback_str = "".join(traceback_module.format_exception(type(exc), exc, exc.__traceback__)) if exc else traceback_module.format_exc()
        self.log(
            level="ERROR",
            source=source,
            module=module,
            message=message,
            endpoint=endpoint,
            traceback_str=traceback_str,
            structured_data=structured_data,
            correlationId=correlationId,
        )

    def log_trade(self, module: str, message: str, **kwargs: Any) -> None:
        self.log(level=kwargs.pop("level", "INFO"), source="MARKET_EVENT", module=module, message=message, **kwargs)

    def log_job(self, module: str, message: str, level: str = "INFO", **kwargs: Any) -> None:
        self.log(level=level, source="JOB", module=module, message=message, **kwargs)

    def log_info(self, module: str, message: str, **kwargs: Any) -> None:
        self.log(level="INFO", source=kwargs.pop("source", "SYSTEM"), module=module, message=message, **kwargs)

    def log_warn(self, module: str, message: str, **kwargs: Any) -> None:
        self.log(level="WARN", source=kwargs.pop("source", "SYSTEM"), module=module, message=message, **kwargs)

    def _broadcast(self, entry: dict[str, Any]) -> None:
        for client_queue in list(_ws_clients):
            try:
                client_queue.put_nowait(entry)
            except asyncio.QueueFull:
                pass

    def _ensure_queue_for_current_loop(self) -> None:
        bound_loop = getattr(self._queue, "_loop", None)
        current_loop = asyncio.get_running_loop()
        if bound_loop is not None and bound_loop is not current_loop and self._queue.empty():
            self._queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)

    def _write_fallback(self, entry: dict[str, Any]) -> None:
        try:
            self._fallback_path.parent.mkdir(parents=True, exist_ok=True)
            with self._fallback_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, default=_json_default) + "\n")
        except Exception as exc:
            print(f"[LoggingService] fallback write failed: {exc}")

    async def _flush_worker(self) -> None:
        while True:
            if self._shutting_down and self._queue.empty():
                break
            try:
                first = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            batch = [first, *self._drain_batch(DB_BATCH_SIZE - 1)]
            await self._persist_batch(batch)
            for _ in batch:
                self._queue.task_done()

    def _drain_batch(self, limit: int) -> list[dict[str, Any]]:
        batch: list[dict[str, Any]] = []
        while len(batch) < limit:
            try:
                batch.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return batch

    async def _persist_batch(self, entries: list[dict[str, Any]]) -> None:
        try:
            await asyncio.to_thread(self._sync_persist, entries)
        except Exception:
            for entry in entries:
                self._write_fallback(entry)

    def _sync_persist(self, entries: list[dict[str, Any]]) -> None:
        db = SessionLocal()
        try:
            for entry in entries:
                db.add(
                    SystemLog(
                        timestamp=datetime.fromisoformat(entry["timestamp"]),
                        level=entry["level"],
                        source=entry["source"],
                        module=entry["module"],
                        endpoint=entry.get("endpoint"),
                        message=entry["message"],
                        error_hash=entry.get("error_hash"),
                        traceback=entry.get("traceback"),
                        structured_data=entry.get("structured_data"),
                        correlationId=entry.get("correlationId"),
                        userId=entry.get("userId"),
                        symbol=entry.get("symbol"),
                        orderId=entry.get("orderId"),
                        environment=entry.get("environment"),
                    )
                )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _emergency_snapshot(self) -> dict[str, Any]:
        return {
            "captured_at": utc_now().isoformat(),
            "pid": os.getpid(),
            "platform": platform.platform(),
            "queue_size": self._queue.qsize(),
            "environment": self._environment,
        }


logger_service = LoggingService()
