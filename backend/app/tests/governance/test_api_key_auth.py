"""Tests for diagnostics API key enforcement (NFR-005 / C5)."""

from __future__ import annotations

import os

import pytest
from fastapi import FastAPI, Depends, Header
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.core.security import verify_api_key
from app.routes.diagnostics import router, get_dashboard, _require_api_key
from app.observability.dashboard import DashboardProvider
from app.observability.log_aggregator import LogAggregator


@pytest.fixture
def api_app(temp_dir, monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    agg = LogAggregator(base_dir=str(temp_dir))
    dashboard = DashboardProvider(log_aggregator=agg)

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_dashboard] = lambda: dashboard
    return app


@pytest.mark.asyncio
async def test_open_access_when_api_key_unset(api_app):
    async with AsyncClient(
        transport=ASGITransport(app=api_app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/dashboard/metrics")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_rejects_missing_key_when_configured(api_app, monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-test-key")
    async with AsyncClient(
        transport=ASGITransport(app=api_app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/dashboard/metrics")
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_accepts_valid_bearer_key(api_app, monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-test-key")
    async with AsyncClient(
        transport=ASGITransport(app=api_app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/v1/dashboard/metrics",
            headers={"Authorization": "Bearer secret-test-key"},
        )
        assert resp.status_code == 200


def test_verify_api_key_raises_on_bad_token(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret")
    with pytest.raises(HTTPException) as exc:
        verify_api_key("Bearer wrong")
    assert exc.value.status_code == 401


def test_verify_api_key_ok_when_unset(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    assert verify_api_key(None) is True
