import redis.asyncio as redis
from typing import Optional
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

redis_client = redis.from_url(REDIS_URL, decode_responses=True)

class RedisBlocklist:
    @staticmethod
    async def add_token(jti: str, expires_in: int):
        """Add a JWT ID (jti) to the blocklist with an expiration"""
        await redis_client.setex(f"blocklist:{jti}", expires_in, "revoked")

    @staticmethod
    async def is_revoked(jti: str) -> bool:
        """Check if a JWT ID is in the blocklist"""
        return await redis_client.exists(f"blocklist:{jti}") > 0

class RateLimiter:
    @staticmethod
    async def is_rate_limited(key: str, max_requests: int, window_seconds: int) -> bool:
        """Simple rate limiter using Redis"""
        current_count = await redis_client.incr(f"ratelimit:{key}")
        if current_count == 1:
            await redis_client.expire(f"ratelimit:{key}", window_seconds)
        
        return current_count > max_requests

    @staticmethod
    async def check_lockout(key: str, max_attempts: int, lockout_minutes: int) -> bool:
        """Lockout after max_attempts. Returns True if locked out."""
        # This checks if lockout key exists
        locked = await redis_client.exists(f"lockout:{key}")
        if locked:
            return True
            
        attempts = await redis_client.get(f"attempts:{key}")
        if attempts and int(attempts) >= max_attempts:
            # Create lockout key
            await redis_client.setex(f"lockout:{key}", lockout_minutes * 60, "locked")
            await redis_client.delete(f"attempts:{key}")
            return True
        return False

    @staticmethod
    async def increment_attempt(key: str, window_minutes: int = 15):
        """Increment attempt count for a key"""
        count = await redis_client.incr(f"attempts:{key}")
        if count == 1:
            await redis_client.expire(f"attempts:{key}", window_minutes * 60)
        return count
    
    @staticmethod
    async def reset_attempts(key: str):
        """Reset attempts after successful login"""
        await redis_client.delete(f"attempts:{key}")
        await redis_client.delete(f"lockout:{key}")
