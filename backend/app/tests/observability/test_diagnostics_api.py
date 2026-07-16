"""Integration tests for Diagnostics Dashboard API endpoints.

Acceptance criteria covered:
  AC-US2-1: GET /api/v1/dashboard/metrics returns system metrics
  AC-US2-2: GET /api/v1/dashboard/logs with filters
  AC-US2-3: GET /api/v1/dashboard/alerts
  POST /api/v1/dashboard/logs/ingest (201)
  Failure: invalid level, empty source, missing body, rate limit
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from app.routes.diagnostics import router, get_dashboard, _rate_limit_store
from app.observability.dashboard import DashboardProvider
from app.observability.log_aggregator import LogAggregator
from app.observability.alert_engine import AlertEngine


@pytest.fixture
def api_app(temp_dir):
    """Build a minimal FastAPI app with the diagnostics router and temp-dir storage."""
    agg = LogAggregator(base_dir=str(temp_dir))

    rules_path = temp_dir / "alerts.yml"
    with open(rules_path, "w", encoding="utf-8") as f:
        yaml.dump([{
            "name": "high-cpu", "metric_name": "cpu_percent",
            "condition": "gt", "threshold": 50.0,
            "severity": "warning", "enabled": True,
        }], f)
    engine = AlertEngine(rules_path=str(rules_path), base_dir=str(temp_dir))

    dashboard = DashboardProvider(
        log_aggregator=agg,
        alert_engine=engine,
    )

    # Override the dependency to use temp-dir-based components
    def _get_test_dashboard():
        return dashboard

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_dashboard] = _get_test_dashboard

    # Reset rate limit store for each test
    _rate_limit_store.clear()

    return app


@pytest.fixture
async def client(api_app):
    async with AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# GET /api/v1/dashboard/metrics — AC-US2-1
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_metrics(client):
    """AC-US2-1: metrics endpoint returns system CPU, memory, request rate, error rate."""
    resp = await client.get("/api/v1/dashboard/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "system" in data
    assert "cpu_percent" in data["system"]
    assert "memory_percent" in data["system"]
    assert "request_rate_per_sec" in data["system"]
    assert "error_rate_per_sec" in data["system"]


@pytest.mark.asyncio
async def test_get_metrics_values_are_floats(client):
    """Edge: system metrics are numeric."""
    resp = await client.get("/api/v1/dashboard/metrics")
    sys_data = resp.json()["system"]
    assert isinstance(sys_data["cpu_percent"], (int, float))
    assert isinstance(sys_data["memory_percent"], (int, float))


# ---------------------------------------------------------------------------
# GET /api/v1/dashboard/logs — AC-US2-2
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_logs_empty(client):
    """Edge: no logs ingested → empty entries."""
    resp = await client.get("/api/v1/dashboard/logs")
    assert resp.status_code == 200
    data = resp.json()
    assert "entries" in data
    assert "total" in data
    assert data["entries"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_get_logs_returns_ingested(client):
    """AC-US2-2: ingested logs appear in query results."""
    resp = await client.post("/api/v1/dashboard/logs/ingest", json={
        "level": "info", "source": "api-test", "message": "ingested via API",
    })
    assert resp.status_code == 201

    resp = await client.get("/api/v1/dashboard/logs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any("api-test" in e["source"] for e in data["entries"])


@pytest.mark.asyncio
async def test_get_logs_filter_by_level(client):
    """AC-US2-2: level filter returns matching entries."""
    await client.post("/api/v1/dashboard/logs/ingest", json={
        "level": "error", "source": "s1", "message": "error msg",
    })
    await client.post("/api/v1/dashboard/logs/ingest", json={
        "level": "info", "source": "s2", "message": "info msg",
    })

    resp = await client.get("/api/v1/dashboard/logs?level=error")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["entries"][0]["level"] == "error"


@pytest.mark.asyncio
async def test_get_logs_filter_by_source(client):
    """AC-US2-2: source filter returns matching entries."""
    await client.post("/api/v1/dashboard/logs/ingest", json={
        "level": "info", "source": "alpha", "message": "a",
    })
    await client.post("/api/v1/dashboard/logs/ingest", json={
        "level": "info", "source": "beta", "message": "b",
    })

    resp = await client.get("/api/v1/dashboard/logs?source=alpha")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["entries"][0]["source"] == "alpha"


@pytest.mark.asyncio
async def test_get_logs_pagination(client):
    """Edge: limit and offset params work."""
    for i in range(5):
        await client.post("/api/v1/dashboard/logs/ingest", json={
            "level": "info", "source": "page-test", "message": f"m-{i}",
        })

    resp = await client.get("/api/v1/dashboard/logs?limit=2&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["entries"]) == 2
    assert data["limit"] == 2


@pytest.mark.asyncio
async def test_get_logs_limit_below_min_rejected(client):
    """Failure: limit=0 is rejected by validation."""
    resp = await client.get("/api/v1/dashboard/logs?limit=0")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_logs_limit_above_max_rejected(client):
    """Failure: limit=1001 is rejected by validation."""
    resp = await client.get("/api/v1/dashboard/logs?limit=1001")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/dashboard/alerts — AC-US2-3
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_alerts_empty(client):
    """Edge: no alerts → empty list."""
    resp = await client.get("/api/v1/dashboard/alerts")
    assert resp.status_code == 200
    data = resp.json()
    assert "alerts" in data
    assert data["alerts"] == []


@pytest.mark.asyncio
async def test_get_alerts_after_evaluation(client, temp_dir):
    """AC-US2-3: alerts appear after a metric breaches threshold."""
    # Manually evaluate via the alert engine in the test dashboard
    app = client._transport.app
    dashboard = app.dependency_overrides[get_dashboard]()
    dashboard.alert_engine.evaluate("cpu_percent", 75.0)  # threshold 50 → triggers

    resp = await client.get("/api/v1/dashboard/alerts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["alerts"]) >= 1


@pytest.mark.asyncio
async def test_get_alerts_filter_by_severity(client, temp_dir):
    """Edge: severity filter returns only matching alerts."""
    app = client._transport.app
    dashboard = app.dependency_overrides[get_dashboard]()
    dashboard.alert_engine.evaluate("cpu_percent", 75.0)

    resp = await client.get("/api/v1/dashboard/alerts?severity=warning")
    assert resp.status_code == 200
    data = resp.json()
    assert all(a["severity"] == "warning" for a in data["alerts"])


# ---------------------------------------------------------------------------
# POST /api/v1/dashboard/logs/ingest
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ingest_log_success(client):
    """POST /logs/ingest returns 201 with status=accepted and uuid."""
    resp = await client.post("/api/v1/dashboard/logs/ingest", json={
        "level": "info", "source": "test-ingest", "message": "hello world",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "accepted"
    assert "uuid" in data
    assert len(data["uuid"]) > 0


@pytest.mark.asyncio
async def test_ingest_log_with_metadata(client):
    """Edge: ingestion preserves metadata."""
    resp = await client.post("/api/v1/dashboard/logs/ingest", json={
        "level": "warning", "source": "meta-test", "message": "with meta",
        "metadata": {"experiment_id": "abc-123", "count": 5},
    })
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_ingest_log_all_levels(client):
    """Edge: all five log levels can be ingested via API."""
    for level in ["debug", "info", "warning", "error", "critical"]:
        resp = await client.post("/api/v1/dashboard/logs/ingest", json={
            "level": level, "source": "levels", "message": f"level-{level}",
        })
        assert resp.status_code == 201, f"Level {level} failed"


# ---------------------------------------------------------------------------
# Failure path tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ingest_invalid_level_rejected(client):
    """Failure: invalid log level is rejected (422)."""
    resp = await client.post("/api/v1/dashboard/logs/ingest", json={
        "level": "trace", "source": "s", "message": "m",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ingest_empty_source_rejected(client):
    """Failure: empty source is rejected (422)."""
    resp = await client.post("/api/v1/dashboard/logs/ingest", json={
        "level": "info", "source": "", "message": "m",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ingest_empty_message_rejected(client):
    """Failure: empty message is rejected (422)."""
    resp = await client.post("/api/v1/dashboard/logs/ingest", json={
        "level": "info", "source": "s", "message": "",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ingest_missing_level_rejected(client):
    """Failure: missing level field is rejected (422)."""
    resp = await client.post("/api/v1/dashboard/logs/ingest", json={
        "source": "s", "message": "m",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ingest_missing_source_rejected(client):
    """Failure: missing source field is rejected (422)."""
    resp = await client.post("/api/v1/dashboard/logs/ingest", json={
        "level": "info", "message": "m",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ingest_empty_body_rejected(client):
    """Failure: empty body is rejected (422)."""
    resp = await client.post("/api/v1/dashboard/logs/ingest", json={})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Rate limiting — T037
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rate_limit_exceeds_threshold(client):
    """T037: after exceeding the rate limit (60 req/60s), 429 is returned."""
    from app.routes.diagnostics import _RATE_LIMIT_MAX, _rate_limit_store
    # Clear store and lower threshold for test
    _rate_limit_store.clear()

    # Send exactly RATE_LIMIT_MAX successful requests
    for i in range(_RATE_LIMIT_MAX):
        resp = await client.post("/api/v1/dashboard/logs/ingest", json={
            "level": "info", "source": "rate-test", "message": f"m-{i}",
        })
        if resp.status_code == 429:
            break
        assert resp.status_code == 201

    # Next request should be rate-limited
    resp = await client.post("/api/v1/dashboard/logs/ingest", json={
        "level": "info", "source": "rate-test", "message": "over-limit",
    })
    assert resp.status_code == 429
    _rate_limit_store.clear()


# ---------------------------------------------------------------------------
# Prometheus metrics endpoint — T038
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_prometheus_metrics(client):
    """T038: prometheus metrics endpoint returns CPU and memory."""
    resp = await client.get("/api/v1/dashboard/metrics/prometheus")
    assert resp.status_code == 200
    data = resp.json()
    assert "trading_cpu_percent" in data
    assert "trading_memory_percent" in data
    assert "trading_memory_used_mb" in data