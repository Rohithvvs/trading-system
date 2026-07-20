import asyncio
import json

import pytest

from backend.app.services.logger_service import LoggingService


@pytest.fixture()
def isolated_logger(tmp_path):
    # LoggingService is a process singleton — reset so each test is isolated.
    LoggingService._instance = None
    service = LoggingService()
    service._queue = asyncio.Queue(maxsize=10_000)
    service._worker_task = None
    service._shutting_down = False
    service._fallback_path = tmp_path / "fallback_logs.jsonl"
    yield service
    if service._worker_task and not service._worker_task.done():
        service._worker_task.cancel()
    LoggingService._instance = None


@pytest.mark.asyncio
async def test_logger_masks_secrets_before_db_persist(isolated_logger, monkeypatch):
    captured: list[dict] = []

    async def capture_persist(entries):
        captured.extend(entries)

    monkeypatch.setattr(isolated_logger, "_async_persist", capture_persist)
    isolated_logger.log(
        level="ERROR",
        source="API",
        module="unit_masking",
        message="failed access_token=tok123 password=hunter2 client_secret=secret456",
        traceback_str="Traceback with password=raw-secret and client_secret=raw-client-secret",
        structured_data={
            "access_token": "raw-token",
            "payload": {
                "password": "raw-password",
                "client_secret": "raw-client-secret",
                "notes": "client_secret=embedded-secret",
            },
        },
    )

    await isolated_logger.flush_now()

    assert len(captured) == 1
    entry = captured[0]
    serialized = json.dumps(entry, default=str)

    assert serialized.count("***MASKED***") >= 7
    assert "tok123" not in serialized
    assert "hunter2" not in serialized
    assert "secret456" not in serialized
    assert "raw-token" not in serialized
    assert "raw-password" not in serialized
    assert "raw-client-secret" not in serialized
    assert "embedded-secret" not in serialized


def test_queue_full_writes_second_log_to_fallback_jsonl(isolated_logger):
    isolated_logger._queue = asyncio.Queue(maxsize=1)

    isolated_logger.log(level="INFO", source="SYSTEM", module="oom_first", message="queued")
    isolated_logger.log(level="ERROR", source="SYSTEM", module="oom_second", message="fallback password=hidden")

    assert isolated_logger.queue.qsize() == 1
    assert isolated_logger._fallback_path.exists()

    fallback_rows = [
        json.loads(line)
        for line in isolated_logger._fallback_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(fallback_rows) == 1
    assert fallback_rows[0]["module"] == "oom_second"
    assert fallback_rows[0]["message"] == "fallback password=***MASKED***"
    assert fallback_rows[0]["level"] == "ERROR"


@pytest.mark.asyncio
async def test_shutdown_drains_remaining_queue_to_database(isolated_logger, monkeypatch):
    captured: list[dict] = []

    async def capture_persist(entries):
        captured.extend(entries)

    monkeypatch.setattr(isolated_logger, "_async_persist", capture_persist)

    for index in range(5):
        isolated_logger.log(
            level="INFO",
            source="JOB",
            module="lifespan_drain",
            message=f"queued shutdown item {index}",
        )

    assert isolated_logger.queue.qsize() == 5

    await isolated_logger.shutdown()

    assert len(captured) == 5
    assert all(row["module"] == "lifespan_drain" for row in captured)
    assert isolated_logger.queue.empty()


@pytest.mark.asyncio
async def test_db_failure_during_flush_falls_back_to_jsonl(isolated_logger, monkeypatch):
    async def fail_persist(entries):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(isolated_logger, "_async_persist", fail_persist)
    isolated_logger.log(level="CRITICAL", source="SYSTEM", module="db_down", message="panic")

    await isolated_logger.flush_now()

    fallback_rows = [
        json.loads(line)
        for line in isolated_logger._fallback_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert fallback_rows[0]["module"] == "db_down"
    assert fallback_rows[0]["level"] == "CRITICAL"
    assert "emergency_snapshot" in fallback_rows[0]["structured_data"]
