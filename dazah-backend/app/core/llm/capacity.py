"""Bound provider work for the complete call/stream lifetime, including cancellation."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from functools import wraps
from weakref import WeakKeyDictionary

from .exceptions import LLMRateLimitError


class Capacity:
    def __init__(self, active: int = 2, waiting: int = 10, timeout: float = 10):
        self.slots = asyncio.Semaphore(active)
        self.limit = active + waiting
        self.admitted = 0
        self.timeout = timeout

    @asynccontextmanager
    async def hold(self) -> AsyncIterator[None]:
        if self.admitted >= self.limit:
            raise LLMRateLimitError("AI 服务繁忙，请稍后重试", status_code=429)
        self.admitted += 1
        acquired = False
        try:
            try:
                await asyncio.wait_for(self.slots.acquire(), self.timeout)
                acquired = True
            except TimeoutError as exc:
                raise LLMRateLimitError(
                    "AI 等待超时，请稍后重试", status_code=429
                ) from exc
            yield
        finally:
            if acquired:
                self.slots.release()
            self.admitted -= 1


_limits: WeakKeyDictionary[asyncio.AbstractEventLoop, Capacity] = WeakKeyDictionary()


@asynccontextmanager
async def hold_capacity() -> AsyncIterator[None]:
    loop = asyncio.get_running_loop()
    limiter = _limits.setdefault(loop, Capacity())
    async with limiter.hold():
        yield


def bounded_call[**P, T](func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
    @wraps(func)
    async def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
        async with hold_capacity():
            return await func(*args, **kwargs)
    return wrapped


def bounded_stream[**P, T](
    func: Callable[P, AsyncIterator[T]],
) -> Callable[P, AsyncIterator[T]]:
    @wraps(func)
    async def wrapped(*args: P.args, **kwargs: P.kwargs) -> AsyncIterator[T]:
        async with hold_capacity():
            stream = func(*args, **kwargs)
            try:
                async for chunk in stream:
                    yield chunk
            finally:
                # The provider generator owns its HTTP connection.
                closer = getattr(stream, "aclose", None)
                if closer is not None:
                    await closer()
    return wrapped
