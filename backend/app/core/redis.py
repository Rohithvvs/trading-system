import redis.asyncio as redis
from typing import Optional
import os
import logging

logger = logging.getLogger("app.redis")

REDIS_URL = os.getenv("REDIS_URL", "")
redis_client = None


def _connect_timeout_seconds() -> float:
    """Bound Redis TCP connect; keep short so unavailable Redis fails fast."""
    try:
        from app.config.settings import settings

        # Align with write budget as an upper bound for connect; minimum 50ms.
        return max(0.05, min(0.5, settings.redis_cache_write_timeout_ms / 1000.0))
    except Exception:
        return 0.1


def _create_redis_client(url: str):
    """Create async Redis client with connect timeout (op timeouts enforced by callers)."""
    return redis.from_url(
        url,
        decode_responses=True,
        socket_connect_timeout=_connect_timeout_seconds(),
        health_check_interval=30,
    )


if not REDIS_URL:
    app_env = os.getenv("APP_ENV", "production").lower()
    if app_env in ("production", "prod", "staging"):
        logger.warning("REDIS_URL not set in production — Redis features will be disabled")
        redis_client = None
    else:
        REDIS_URL = "redis://localhost:6379/0"
        try:
            redis_client = _create_redis_client(REDIS_URL)
        except Exception as exc:
            logger.error("Failed to connect to Redis at %s: %s", REDIS_URL, exc)
            redis_client = None
else:
    try:
        redis_client = _create_redis_client(REDIS_URL)
    except Exception as exc:
        logger.error("Failed to connect to Redis at %s: %s", REDIS_URL, exc)
        redis_client = None


def get_redis_client():
    """Return the global async Redis client instance, or None if unavailable."""
    global redis_client
    if redis_client is None:
        try:
            from app.config.settings import settings
            target_url = settings.redis_url or REDIS_URL or "redis://localhost:6379/0"
            redis_client = _create_redis_client(target_url)
        except Exception as exc:
            logger.error("Failed to initialize Redis client: %s", exc)
            redis_client = None
    return redis_client


def get_redis():
    """Backward-compatible alias used by health checks and older call sites."""
    return get_redis_client()


def _redis_available() -> bool:
    """True when a live client can be obtained (recreates after close if possible)."""
    return get_redis_client() is not None


async def close_redis_client() -> None:
    """Dispose the global Redis client (call on app shutdown)."""
    global redis_client
    client = redis_client
    redis_client = None
    if client is None:
        return
    try:
        aclose = getattr(client, "aclose", None)
        if callable(aclose):
            await aclose()
        else:
            close = getattr(client, "close", None)
            if callable(close):
                result = close()
                if hasattr(result, "__await__"):
                    await result
        logger.info("Redis client closed")
    except Exception as exc:
        logger.warning("Redis client close failed: %s", exc)


class RedisBlocklist:
    @staticmethod
    async def add_token(jti: str, expires_in: int):
        """Add a JWT ID (jti) to the blocklist with an expiration"""
        client = get_redis_client()
        if client is None:
            return
        await client.setex(f"blocklist:{jti}", expires_in, "revoked")

    @staticmethod
    async def is_revoked(jti: str) -> bool:
        """Check if a JWT ID is in the blocklist"""
        client = get_redis_client()
        if client is None:
            return False
        return await client.exists(f"blocklist:{jti}") > 0

class RateLimiter:
    @staticmethod
    async def is_rate_limited(key: str, max_requests: int, window_seconds: int) -> bool:
        """Simple rate limiter using Redis"""
        client = get_redis_client()
        if client is None:
            return False
        current_count = await client.incr(f"ratelimit:{key}")
        if current_count == 1:
            await client.expire(f"ratelimit:{key}", window_seconds)
        
        return current_count > max_requests

    @staticmethod
    async def check_lockout(key: str, max_attempts: int, lockout_minutes: int) -> bool:
        """Lockout after max_attempts. Returns True if locked out."""
        client = get_redis_client()
        if client is None:
            return False
        # This checks if lockout key exists
        locked = await client.exists(f"lockout:{key}")
        if locked:
            return True
            
        attempts = await client.get(f"attempts:{key}")
        if attempts and int(attempts) >= max_attempts:
            # Create lockout key
            await client.setex(f"lockout:{key}", lockout_minutes * 60, "locked")
            await client.delete(f"attempts:{key}")
            return True
        return False

    @staticmethod
    async def increment_attempt(key: str, window_minutes: int = 15):
        """Increment attempt count for a key"""
        client = get_redis_client()
        if client is None:
            return 0
        count = await client.incr(f"attempts:{key}")
        if count == 1:
            await client.expire(f"attempts:{key}", window_minutes * 60)
        return count
    
    @staticmethod
    async def reset_attempts(key: str):
        """Reset attempts after successful login"""
        client = get_redis_client()
        if client is None:
            return
        await client.delete(f"attempts:{key}")
        await client.delete(f"lockout:{key}")
