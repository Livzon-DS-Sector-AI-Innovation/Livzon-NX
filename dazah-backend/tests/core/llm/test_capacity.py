import asyncio

import pytest

from app.core.llm.capacity import Capacity, bounded_stream
from app.core.llm.exceptions import LLMRateLimitError


@pytest.mark.asyncio
async def test_queue_is_bounded_and_cancelled_waiter_releases_admission():
    limiter = Capacity(active=1, waiting=1, timeout=1)
    async with limiter.hold():
        async def wait():
            async with limiter.hold():
                pytest.fail("must not acquire before holder exits")
        task = asyncio.create_task(wait())
        await asyncio.sleep(0)
        with pytest.raises(LLMRateLimitError):
            async with limiter.hold():
                pass
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert limiter.admitted == 1
    assert limiter.admitted == 0


@pytest.mark.asyncio
async def test_timeout_does_not_leak_capacity():
    limiter = Capacity(active=1, waiting=1, timeout=0.01)
    async with limiter.hold():
        with pytest.raises(LLMRateLimitError):
            async with limiter.hold():
                pass
        assert limiter.admitted == 1
    async with limiter.hold():
        assert limiter.admitted == 1


@pytest.mark.asyncio
async def test_stream_closes_provider_when_consumer_closes():
    closed = False
    @bounded_stream
    async def provider():
        nonlocal closed
        try:
            yield "chunk"
            await asyncio.sleep(10)
        finally:
            closed = True
    stream = provider()
    assert await anext(stream) == "chunk"
    await stream.aclose()
    assert closed
