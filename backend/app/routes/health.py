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
async def heartbeat() -> dict[str, object]:
    await market_engine.heartbeat()
    return sanitize_for_json({"status": "ok", "engine": market_engine.status()})


# Clean market status for clients (no auth needed for status)
try:
    from ..services.trading_hours_service import trading_hours as _ths
    _THS_OK = True
except Exception:
    _THS_OK = False

@router.get("/market-status")
def market_status_public():
    """Lightweight public market status. Use this from frontend before buy flows."""
    from ..core.response_cache import cache_get, cache_set

    cache_key = "market_status_public"
    hit = cache_get(cache_key)
    if hit is not None:
        return hit

    if not _THS_OK:
        return {"is_open": False, "status": "UNKNOWN", "reason": "unavailable"}
    info = _ths.get_market_status()
    payload = {
        "is_open": bool(info.get("is_open")),
        "status": info.get("status"),
        "reason": info.get("reason"),
        "current_ist": info.get("current_ist"),
        "next_open_ist": info.get("next_open_ist"),
        "market_hours_ist": "09:15 - 15:30",
    }
    # Short TTL — market open/close is time-sensitive
    cache_set(cache_key, payload, ttl_seconds=60.0)
    return payload
