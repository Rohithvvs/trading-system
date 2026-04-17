from fastapi import APIRouter

from ..config import settings
from ..schemas import HealthResponse
from ..utils import advisory_payload


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        environment=settings.app_env,
        disclaimer=advisory_payload(),
    )
