import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core import read_through_cache, redis
from app.core.exceptions import AppException
from app.core.read_through_cache import CacheFill, ReadThroughCache


@pytest.fixture
def cache() -> ReadThroughCache[str]:
    return ReadThroughCache(
        "test read cache",
        max_loads=1,
        decode=lambda value: value if isinstance(value, str) else None,
    )


@pytest.fixture
def redis_client(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    client = SimpleNamespace(
        get=AsyncMock(return_value=None),
        set=AsyncMock(),
        incr=AsyncMock(),
        aclose=AsyncMock(),
    )
    monkeypatch.setattr(redis, "redis_client", client)
    return client


async def test_distinct_keys_cannot_overload_source_and_cache_hits_still_work(
    cache: ReadThroughCache[str],
    redis_client: SimpleNamespace,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_fill() -> CacheFill[str]:
        started.set()
        await release.wait()
        return CacheFill("filled", 60)

    first = asyncio.create_task(cache.get_or_load("first", slow_fill))
    other = AsyncMock(return_value=CacheFill("other", 60))
    try:
        await asyncio.wait_for(started.wait(), 1)
        with pytest.raises(AppException) as failure:
            await cache.get_or_load("other", other)
        assert failure.value.status_code == 503
        other.assert_not_awaited()
        redis_client.get.return_value = '"hit"'
        assert await cache.get_or_load("cached", other) == "hit"
        other.assert_not_awaited()
    finally:
        release.set()
        assert await first == "filled"

    redis_client.get.return_value = None
    assert await cache.get_or_load("other", other) == "other"
    other.assert_awaited_once()


async def test_disconnection_temporarily_skips_redis_and_retries_after_cooldown(
    cache: ReadThroughCache[str],
    redis_client: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = 10.0
    monkeypatch.setattr(read_through_cache, "monotonic", lambda: now)
    redis_client.get.side_effect = RedisConnectionError("synthetic disconnect")
    load = AsyncMock(return_value=CacheFill("source", 60))

    assert await cache.get_or_load("a", load) == "source"
    assert await cache.get_or_load("b", load) == "source"
    redis_client.get.assert_awaited_once_with("a")
    redis_client.set.assert_not_awaited()

    now += 3
    redis_client.get.side_effect = None
    redis_client.get.return_value = '"recovered"'
    assert await cache.get_or_load("a", load) == "recovered"
    assert load.await_count == 2


async def test_waiter_cancellation_leaves_shared_fill_running(
    cache: ReadThroughCache[str],
    redis_client: SimpleNamespace,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def load() -> CacheFill[str]:
        started.set()
        await release.wait()
        return CacheFill("saved", 60)

    leader = asyncio.create_task(cache.get_or_load("key", load))
    await asyncio.wait_for(started.wait(), 1)
    other = AsyncMock()
    waiter = asyncio.create_task(cache.get_or_load("key", other))
    await asyncio.sleep(0)
    waiter.cancel()
    try:
        with pytest.raises(asyncio.CancelledError):
            await waiter
    finally:
        release.set()
        assert await leader == "saved"
    other.assert_not_awaited()
    redis_client.set.assert_awaited_once()


async def test_source_failure_does_not_cache_a_negative_result(
    cache: ReadThroughCache[str],
    redis_client: SimpleNamespace,
) -> None:
    load = AsyncMock(side_effect=[AppException(status_code=502), CacheFill("ok", 60)])
    with pytest.raises(AppException) as failure:
        await cache.get_or_load("key", load)
    assert failure.value.status_code == 502
    redis_client.set.assert_not_awaited()
    assert await cache.get_or_load("key", load) == "ok"
    redis_client.set.assert_awaited_once()


async def test_redis_disconnect_during_cache_write_preserves_source_result(
    cache: ReadThroughCache[str],
    redis_client: SimpleNamespace,
) -> None:
    redis_client.set.side_effect = RedisConnectionError("synthetic disconnect")
    load = AsyncMock(return_value=CacheFill("source", 60))

    assert await cache.get_or_load("key", load) == "source"
    assert await cache.get_or_load("other", load) == "source"
    redis_client.get.assert_awaited_once_with("key")
    redis_client.set.assert_awaited_once()


async def test_failed_invalidation_is_retried_before_reusing_redis(
    cache: ReadThroughCache[str],
    redis_client: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = 10.0
    monkeypatch.setattr(read_through_cache, "monotonic", lambda: now)
    load = AsyncMock(return_value=CacheFill("fresh", 60))
    redis_client.incr.side_effect = RedisConnectionError("synthetic disconnect")

    await cache.invalidate_group("revision")
    assert await cache.get_or_load("ledger", load, revision_key="revision") == "fresh"
    redis_client.get.assert_not_awaited()
    redis_client.set.assert_not_awaited()

    now += 3
    redis_client.incr.side_effect = None
    redis_client.get.side_effect = {"revision": "2", "ledger:1": '"stale"'}.get
    assert await cache.get_or_load("ledger", load, revision_key="revision") == "fresh"
    assert redis_client.incr.await_count == 2
    redis_client.get.assert_any_await("ledger:2")
    redis_client.set.assert_awaited_once()
    assert redis_client.set.await_args.args[0] == "ledger:2"
