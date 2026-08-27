import logging
from typing import cast

import redis.asyncio as redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

redis_client = redis.from_url(
    settings.REDIS_URL,
    decode_responses=True,
)


async def get_redis() -> redis.Redis:
    return redis_client


async def cache_get(key: str) -> str | None:
    try:
        return cast(str | None, await redis_client.get(key))
    except Exception:
        # Cache outages must not turn a database-backed authorization/data-scope
        # lookup into a 500; callers recompute the value from the source of truth.
        logger.warning(
            "Redis cache read unavailable; falling back to source", extra={"key": key}
        )
        return None


async def cache_set(key: str, value: str, ex: int = 3600) -> None:
    try:
        await redis_client.set(key, value, ex=ex)
    except Exception:
        logger.warning("Redis cache write unavailable", extra={"key": key})


async def cache_delete(key: str) -> None:
    try:
        await redis_client.delete(key)
    except Exception:
        logger.warning("Redis cache delete unavailable", extra={"key": key})


async def cache_incr(key: str, ex: int = 60) -> int:
    """Atomically increment a counter and expire it on its first write."""
    value = await redis_client.incr(key)
    if value == 1:
        await redis_client.expire(key, ex)
    return cast(int, value)


async def acquire_lock(key: str, timeout: int = 10) -> bool:
    return bool(await redis_client.set(f"lock:{key}", "1", ex=timeout, nx=True))


async def renew_lock(key: str, timeout: int = 10) -> None:
    """续期已持有锁的 TTL，供长时间运行的后台任务保持互斥。"""
    await redis_client.expire(f"lock:{key}", timeout)


async def release_lock(key: str) -> None:
    await redis_client.delete(f"lock:{key}")
