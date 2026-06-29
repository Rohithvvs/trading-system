import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.routes.scheduler import router as scheduler_router
from backend.app.schemas import AnalysisMode
from backend.app.services.lock_service import LockAcquisitionError
from backend.app.services.scan_execution_service import ScanExecutionService


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(scheduler_router)
    with TestClient(app) as test_client:
        yield test_client


def test_run_scanner_endpoint_is_visible_in_openapi(client):
    schema = client.get("/openapi.json").json()

    assert "/scheduler/run-scanner" in schema["paths"]
    assert "get" in schema["paths"]["/scheduler/run-scanner"]


def test_run_scanner_rejects_missing_or_invalid_key(client, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "valid-secret")

    missing = client.get("/scheduler/run-scanner")
    invalid = client.get("/scheduler/run-scanner?key=wrong")

    assert missing.status_code == 403
    assert invalid.status_code == 403


def test_run_scanner_uses_default_payload_and_waits_for_completion(client, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "valid-secret")
    captured = {}

    async def fake_execute_scan(payload, progress_queue, trigger_source):
        captured["payload"] = payload
        captured["trigger_source"] = trigger_source
        await progress_queue.put(
            {
                "status": "complete",
                "scan_id": "scan-123",
                "result": {
                    "scanned_symbols": 755,
                    "shortlisted_symbols": [],
                    "buy_candidate_symbols": [],
                    "watch_candidate_symbols": [],
                    "matched_symbols": [],
                    "eligible_symbols": [],
                    "data_source": "mock",
                    "screener_name": "test_screener",
                    "scan_stages": [],
                    "market_context": {},
                    "duplicate_symbols_skipped": 0,
                },
            }
        )
        return "scan-123"

    monkeypatch.setattr(ScanExecutionService, "execute_scan", fake_execute_scan)

    response = client.get("/scheduler/run-scanner?key=valid-secret")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "Scanner executed successfully"
    assert body["scan_id"] == "scan-123"
    assert body["scanned_symbols"] == 755
    assert body["shortlisted_count"] == 0
    assert body["metadata"]["data_source"] == "mock"

    payload = captured["payload"]
    assert captured["trigger_source"] == "cron"
    assert payload.mode == AnalysisMode.swing
    assert payload.timeframe.intraday == "5m"
    assert payload.timeframe.swing == "1d"
    assert payload.timeframe.lookback_window == 260
    assert payload.symbols == []
    assert payload.top_n == 20


def test_run_scanner_returns_409_when_scan_is_already_running(client, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "valid-secret")

    async def fake_execute_scan(payload, progress_queue, trigger_source):
        raise LockAcquisitionError("Scan is already in progress.")

    monkeypatch.setattr(ScanExecutionService, "execute_scan", fake_execute_scan)

    response = client.get("/scheduler/run-scanner?key=valid-secret")

    assert response.status_code == 409
    assert response.json() == {
        "success": False,
        "message": "Scanner already running",
    }


def test_run_scanner_returns_500_when_scan_task_reports_error(client, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "valid-secret")

    async def fake_execute_scan(payload, progress_queue, trigger_source):
        await progress_queue.put(
            {
                "status": "error",
                "scan_id": "scan-123",
                "message": "boom",
                "error_type": "RuntimeError",
            }
        )
        return "scan-123"

    monkeypatch.setattr(ScanExecutionService, "execute_scan", fake_execute_scan)

    response = client.get("/scheduler/run-scanner?key=valid-secret")

    assert response.status_code == 500
    assert response.json() == {
        "success": False,
        "message": "Scanner execution failed",
        "scan_id": "scan-123",
    }
