"""Bounded, best-effort Redis caching for read-only business data."""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass
from random import randint
from time import monotonic

from redis.exceptions import RedisError

from app.core import redis
from app.core.exceptions import AppException

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CacheFill[T]:
    value: T
    ttl: int | None


class ReadThroughCache[T]:
    def __init__(
        self, name: str, *, max_loads: int, decode: Callable[[object], T | None]
    ) -> None:
        self._name = name
        self._max_loads = max_loads
        self._decode = decode
        self._loading: dict[str, asyncio.Future[T]] = {}
        self._pending_revisions: dict[str, object] = {}
        self._active_loads = 0
        self._retry_redis_at = 0.0

    def _redis_failed(self, exc: RedisError | TimeoutError) -> None:
        if monotonic() >= self._retry_redis_at:
            logger.warning("%s cache unavailable (%s)", self._name, type(exc).__name__)
            self._retry_redis_at = monotonic() + 2.0

    async def _read(self, key: str) -> tuple[bool, str | None]:
        if monotonic() < self._retry_redis_at:
            return False, None
        try:
            async with asyncio.timeout(0.25):
                return True, await redis.redis_client.get(key)
        except (RedisError, TimeoutError) as exc:
            self._redis_failed(exc)
            return False, None

    async def _get_cached(self, key: str) -> T | None:
        _, raw = await self._read(key)
        if raw is None:
            return None
        try:
            return self._decode(json.loads(raw))
        except (ValueError, TypeError):
            return None

    async def invalidate_group(self, revision_key: str) -> None:
        """Move readers to a fresh key space, including during an in-flight fill."""
        self._pending_revisions[revision_key] = object()
        await self._advance_revision(revision_key)

    async def _advance_revision(self, revision_key: str) -> None:
        pending = self._pending_revisions[revision_key]
        try:
            async with asyncio.timeout(0.25):
                await redis.redis_client.incr(revision_key)
        except (RedisError, TimeoutError) as exc:
            self._redis_failed(exc)
        else:
            if self._pending_revisions.get(revision_key) is pending:
                del self._pending_revisions[revision_key]

    async def get_or_load(
        self,
        key: str,
        load: Callable[[], Awaitable[CacheFill[T]]],
        *,
        revision_key: str | None = None,
    ) -> T:
        cache_available = True
        if revision_key is not None:
            if (
                revision_key in self._pending_revisions
                and monotonic() >= self._retry_redis_at
            ):
                await self._advance_revision(revision_key)
            if revision_key in self._pending_revisions:
                cache_available, revision = False, None
            else:
                cache_available, revision = await self._read(revision_key)
            key = f"{key}:{revision or ('initial' if cache_available else 'offline')}"

        pending = self._loading.get(key)
        if pending is not None:
            return deepcopy(await asyncio.shield(pending))
        pending = asyncio.get_running_loop().create_future()
        self._loading[key] = pending
        try:
            value = await self._find_or_fill(key, load, cache_available=cache_available)
            pending.set_result(value)
            return value
        except asyncio.CancelledError:
            pending.set_exception(
                AppException(status_code=503, message="查询已中断，请稍后重试")
            )
            pending.exception()
            raise
        except Exception as exc:
            pending.set_exception(exc)
            pending.exception()
            raise
        finally:
            self._loading.pop(key)

    async def _find_or_fill(
        self,
        key: str,
        load: Callable[[], Awaitable[CacheFill[T]]],
        *,
        cache_available: bool,
    ) -> T:
        if cache_available:
            cached = await self._get_cached(key)
            if cached is not None:
                return cached
        if self._active_loads >= self._max_loads:
            raise AppException(status_code=503, message="查询繁忙，请稍后重试")
        self._active_loads += 1
        try:
            filled = await load()
        finally:
            self._active_loads -= 1
        if (
            cache_available
            and filled.ttl is not None
            and monotonic() >= self._retry_redis_at
        ):
            try:
                # Spread expiration without extending the freshness budget.
                ttl = filled.ttl - randint(0, filled.ttl // 6)
                async with asyncio.timeout(0.25):
                    await redis.redis_client.set(
                        key,
                        json.dumps(filled.value, ensure_ascii=False, default=str),
                        ex=ttl,
                    )
            except (RedisError, TimeoutError) as exc:
                self._redis_failed(exc)
        return filled.value
