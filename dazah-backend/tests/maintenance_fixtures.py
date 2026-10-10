"""Explicitly isolated Redis for maintenance and background-work contracts."""

import os

import pytest
from redis.asyncio import Redis

from app.core import jobs, maintenance, maintenance_middleware
from app.platform.system import operations


@pytest.fixture
async def isolated_redis(monkeypatch):
    url = os.environ.get("MAINTENANCE_TEST_REDIS_URL")
    if not url:
        pytest.skip("explicit isolated maintenance test Redis required")
    client = Redis.from_url(url, decode_responses=True)
    # Never fall back to application Redis. This URL denotes a dedicated test DB.
    await client.flushdb()
    for module in (maintenance, maintenance_middleware, operations):
        monkeypatch.setattr(module, "redis_client", client)

    async def cache_set(key, value, ex=3600):
        await client.set(key, value, ex=ex)

    monkeypatch.setattr(jobs, "cache_set", cache_set)
    monkeypatch.setattr(jobs, "cache_get", client.get)
    monkeypatch.setattr(jobs, "cache_delete", client.delete)
    yield client
    # A test must not leave a worker running against the next test's Redis.
    if jobs._running_tasks:
        import asyncio

        tasks = list(jobs._running_tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    await client.flushdb()
    await client.aclose()
