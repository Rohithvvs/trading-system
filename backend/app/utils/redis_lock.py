import uuid
import redis.asyncio as redis
from contextlib import asynccontextmanager
from dataclasses import dataclass
from ..config import settings

# If no redis url, fallback to localhost for development
redis_client = redis.Redis.from_url(settings.redis_url)

RELEASE_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

@dataclass(frozen=True)
class FencedLock:
    name: str
    token: str
    fencing_token: int

@asynccontextmanager
async def distributed_lock(lock_name: str, timeout: int = 300):
    """
    Acquires a safe Redlock-style distributed lock using a unique token.
    Prevents a delayed worker from releasing a lock that has expired and been acquired by a new worker.
    """
    token = str(uuid.uuid4())
    fencing_token = int(await redis_client.incr(f"{lock_name}:fence"))
    acquired = await redis_client.set(lock_name, token, nx=True, ex=timeout)
    if not acquired:
        raise RuntimeError(f"Lock {lock_name} is already acquired by another worker.")
    
    try:
        yield FencedLock(lock_name, token, fencing_token)
    finally:
        # Safe release: evaluate lua script to check token ownership before deleting
        await redis_client.eval(RELEASE_LUA, 1, lock_name, token)
