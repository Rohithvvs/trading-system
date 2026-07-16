"""Unit tests for agent command routing — SC-001 and AC-US1-1.

Verifies:
  - All required governance commands are registered
  - Unknown commands return None
  - list_routes returns a non-empty dict
  - The /api/v1/governance/routes endpoint responds
"""
from __future__ import annotations

import pytest

from app.governance.router import get_route, list_routes


REQUIRED_COMMANDS = [
    "experiment.start",
    "experiment.pause",
    "experiment.resume",
    "experiment.complete",
    "experiment.list",
    "experiment.show",
    "experiment.metric",
    "audit.export",
]


def test_get_route_known_command():
    """AC-US1-1: all required governance commands are registered with a handler."""
    for cmd in REQUIRED_COMMANDS:
        route = get_route(cmd)
        assert route is not None, f"Missing route for command: {cmd}"
        assert "experiment_cli" in route or "audit" in route


def test_get_route_unknown_command_returns_none():
    """Failure: unknown command returns None."""
    assert get_route("nonexistent.command") is None
    assert get_route("") is None


def test_list_routes_returns_all():
    """AC-US1-1: list_routes returns all expected commands."""
    routes = list_routes()
    assert len(routes) >= len(REQUIRED_COMMANDS)
    for cmd in REQUIRED_COMMANDS:
        assert cmd in routes


def test_list_routes_is_immutable_copy():
    """Edge: modifying the returned dict does not affect internal state."""
    routes = list_routes()
    routes["injected"] = "evil"
    routes2 = list_routes()
    assert "injected" not in routes2


@pytest.mark.asyncio
async def test_get_routes_endpoint_returns_count():
    """SC-001: the /routes API endpoint returns a valid response with correct count."""
    from fastapi import FastAPI
    from httpx import AsyncClient, ASGITransport
    from app.governance.router import governance_router

    app = FastAPI()
    app.include_router(governance_router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/governance/routes")
        assert resp.status_code == 200
        data = resp.json()
        assert "routes" in data
        assert data["count"] == len(REQUIRED_COMMANDS)
        for cmd in REQUIRED_COMMANDS:
            assert cmd in data["routes"]