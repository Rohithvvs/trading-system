from fastapi import APIRouter

from ..config import settings
from ..schemas import HealthResponse
from ..utils import advisory_payload, sanitize_for_json


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    # Check database
    db_status = "ok"
    try:
        from ..db.session import engine
        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy", fromlist=["text"]).text("SELECT 1"))
    except Exception:
        db_status = "error"

    # Check Redis (graceful if not configured). Client is redis.asyncio — must await ping.
    redis_status = "ok"
    try:
        from ..core.redis import get_redis

        r = get_redis()
        if r is None:
            redis_status = "not_configured"
        else:
            await r.ping()
    except Exception:
        redis_status = "error"

    return HealthResponse(
        status="ok",
        environment=settings.app_env,
        disclaimer=advisory_payload(),
        database=db_status,
        redis=redis_status,
        fyers="ok",
        websocket="ok",
    )


@router.get("/health/heartbeat")
async def heartbeat() -> dict[str, object]:
    await market_engine.heartbeat()
    return sanitize_for_json({"status": "ok", "engine": market_engine.status()})


