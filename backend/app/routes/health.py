from fastapi import APIRouter

from ..config import settings
from ..schemas import HealthResponse
from ..utils import advisory_payload, sanitize_for_json
from ..services.market_engine_service import market_engine


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        environment=settings.app_env,
        disclaimer=advisory_payload(),
    )


@router.get("/health/heartbeat")
def heartbeat() -> dict[str, object]:
    market_engine.heartbeat()
    return sanitize_for_json({"status": "ok", "engine": market_engine.status()})
