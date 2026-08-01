"""System logs CRUD integration tests (Sprint 5: auth + system_logs gate)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.models.system_log import SystemLog
from backend.app.main import app
from backend.app.db.session import AsyncSessionLocal
from backend.app.services.admin_bootstrap_service import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_PASSWORD,
    ensure_default_admin,
)
from backend.app.services.feature_permission_service import ensure_default_feature_permissions


def _run(coro):
    return asyncio.run(coro)


async def _bootstrap_admin_async() -> None:
    async with AsyncSessionLocal() as db:
        await ensure_default_admin(db)
        await ensure_default_feature_permissions(db, commit=True)
        await db.commit()


def _admin_headers(client: TestClient) -> dict:
    _run(_bootstrap_admin_async())
    res = client.post(
        "/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASSWORD},
    )
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_api_logs_get_and_delete(db_session: Session, test_engine):
    with TestClient(app) as client:
        headers = _admin_headers(client)
        # Ensure empty start
        client.delete("/api/logs?days_old=0", headers=headers)

        # Seed DB with explicit dates
        log1 = SystemLog(
            level="ERROR",
            module="test_module",
            message="error_msg",
            endpoint="/test_err",
            timestamp=datetime.utcnow() - timedelta(days=10),
        )
        log2 = SystemLog(
            level="INFO",
            module="test_module",
            message="info_msg",
            endpoint="/test_info",
            timestamp=datetime.utcnow() - timedelta(days=2),
        )
        db_session.add(log1)
        db_session.add(log2)
        db_session.commit()

        # Test GET
        res = client.get("/api/logs", headers=headers)
        assert res.status_code == 200, res.text
        data = res.json()
        assert len(data) >= 2

        # Test GET with level filter (seeded row may not be first if auth/API errors exist)
        res = client.get("/api/logs?level=ERROR&search=error_msg", headers=headers)
        data = res.json()
        assert len(data) >= 1
        assert any(d["message"] == "error_msg" for d in data)

        # Test DELETE old logs (days_old=7)
        res = client.delete("/api/logs?days_old=7", headers=headers)
        assert res.status_code == 200

        # Verify only log2 remains
        res = client.get("/api/logs", headers=headers)
        data = res.json()
        assert any(d["message"] == "info_msg" for d in data)
        assert not any(d["message"] == "error_msg" for d in data)

        # Test DELETE all (days_old=0)
        res = client.delete("/api/logs?days_old=0", headers=headers)
        assert res.status_code == 200

        res = client.get("/api/logs", headers=headers)
        # There should only be 1 log left (the DELETE command we just ran!)
        data = res.json()
        assert len(data) == 1
        assert "DELETE /api/logs" in data[0]["message"]


def test_exception_handler_and_middleware(db_session: Session, test_engine):
    with TestClient(app) as client:
        headers = _admin_headers(client)
        client.delete("/api/logs?days_old=0", headers=headers)

        @app.get("/api/crash_test")
        def crash_test():
            raise ValueError("Simulated crash")

        res = client.get("/api/crash_test")
        assert res.status_code == 500
        assert (
            res.json()["detail"]
            == "An unexpected system error occurred. This has been logged for our engineers."
        )

        res = client.get("/api/logs?level=ERROR", headers=headers)
        data = res.json()
        assert len(data) >= 1
        assert data[0]["module"] == "global_exception_handler"
        assert "Simulated crash" in data[0]["message"]
        assert "Traceback" in data[0]["traceback"]

        # Test HTTP middleware logs POST (unauthenticated still produces access logs)
        res = client.post("/api/logs", json={"some": "data"})

        res = client.get("/api/logs?level=INFO", headers=headers)
        data = res.json()
        assert len(data) > 0
        assert any("POST /api/logs" in d["message"] for d in data)
