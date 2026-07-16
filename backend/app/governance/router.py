"""Agent command routing activation workflow.

Routes ``/specify`` agent commands through a defined activation workflow
module. In Phase 0 this establishes the routing framework; future phases
will add more sophisticated dispatch logic.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

governance_router = APIRouter(prefix="/api/v1/governance", tags=["Governance"])

_COMMAND_ROUTES: dict[str, str] = {
    "experiment.start": "app.governance.experiment_cli:experiment_cli start",
    "experiment.pause": "app.governance.experiment_cli:experiment_cli pause",
    "experiment.resume": "app.governance.experiment_cli:experiment_cli resume",
    "experiment.complete": "app.governance.experiment_cli:experiment_cli complete",
    "experiment.list": "app.governance.experiment_cli:experiment_cli list",
    "experiment.show": "app.governance.experiment_cli:experiment_cli show",
    "experiment.metric": "app.governance.experiment_cli:experiment_cli metric",
    "audit.export": "app.governance.experiment_cli:experiment_cli audit export",
}


def get_route(command: str) -> str | None:
    """Resolve a governance command to its handler module path."""
    return _COMMAND_ROUTES.get(command)


def list_routes() -> dict[str, str]:
    """Return all registered command routes."""
    return dict(_COMMAND_ROUTES)


@governance_router.get("/routes")
async def get_routes() -> dict[str, Any]:
    return {
        "routes": _COMMAND_ROUTES,
        "count": len(_COMMAND_ROUTES),
    }
