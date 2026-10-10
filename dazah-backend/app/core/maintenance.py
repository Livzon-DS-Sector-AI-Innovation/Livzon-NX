"""Distributed admission and drain barrier shared by HTTP, jobs and schedulers.

Active entries deliberately have no TTL: a dead worker must never be mistaken
for successfully completed work. Recovery requires an operator to reconcile it.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import cast
from uuid import uuid4

from app.core.redis import redis_client

STATE_KEY = "dazah:maintenance:phase"
ACTIVE_KEY = "dazah:maintenance:active"
_activity: ContextVar[str | None] = ContextVar("maintenance_activity", default=None)
_instance_id = uuid4().hex

ADMIT = """
local phase = redis.call('GET', KEYS[1])
if (phase == 'draining' or (phase == 'starting' and ARGV[2] ~= 'database-task'))
  and (ARGV[3] == '' or redis.call('HEXISTS', KEYS[2], ARGV[3]) == 0) then
  return 0
end
redis.call('HSET', KEYS[2], ARGV[1], ARGV[4])
return 1
"""


class MaintenanceActiveError(RuntimeError):
    """New work was refused by the release barrier."""


async def admit_activity(kind: str, *, reference: str | None = None) -> str:
    identifier = uuid4().hex
    parent = _activity.get() or ""
    metadata = json.dumps(
        {
            "kind": kind,
            "instance": _instance_id,
            "started_at": time.time(),
            "parent": parent,
            "reference": reference,
        }
    )
    async with asyncio.timeout(3):
        admitted = await cast(
            Awaitable[int],
            redis_client.eval(
                ADMIT, 2, STATE_KEY, ACTIVE_KEY, identifier, kind, parent, metadata
            ),
        )
    if not admitted:
        raise MaintenanceActiveError("系统维护中，尚未受理本次操作")
    return identifier


async def finish_activity(identifier: str) -> None:
    async with asyncio.timeout(3):
        await cast(Awaitable[int], redis_client.hdel(ACTIVE_KEY, identifier))


@asynccontextmanager
async def admitted_activity(identifier: str) -> AsyncIterator[None]:
    context = _activity.set(identifier)
    try:
        yield
    except asyncio.CancelledError:
        # Keep evidence of work whose outcome could not be confirmed.
        raise
    except Exception:
        await finish_activity(identifier)
        raise
    else:
        await finish_activity(identifier)
    finally:
        _activity.reset(context)


@asynccontextmanager
async def business_activity(kind: str) -> AsyncIterator[None]:
    async with admitted_activity(await admit_activity(kind)):
        yield


async def set_release_phase(phase: str) -> None:
    if phase not in {"normal", "draining", "starting"}:
        raise ValueError("invalid maintenance phase")
    async with asyncio.timeout(3):
        await redis_client.set(STATE_KEY, phase)


async def active_work() -> dict[str, int]:
    async with asyncio.timeout(3):
        entries = await cast(
            Awaitable[dict[str, str]], redis_client.hgetall(ACTIVE_KEY)
        )
    counts: dict[str, int] = {}
    for value in entries.values():
        try:
            metadata = json.loads(value)
            kind = str(metadata.get("kind", "unknown"))
        except (json.JSONDecodeError, AttributeError):
            # Older records still count; malformed metadata never means idle.
            kind = value or "unknown"
        counts[kind] = counts.get(kind, 0) + 1
    return counts


async def drain_report() -> str:
    return json.dumps({"active": sum((await active_work()).values())})
