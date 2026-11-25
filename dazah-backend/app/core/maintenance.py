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
from typing import TypedDict, cast
from uuid import uuid4

from app.core.redis import redis_client

STATE_KEY = "dazah:maintenance:phase"
ACTIVE_KEY = "dazah:maintenance:active"
BACKGROUND_PAUSE_KEY = "dazah:maintenance:background-pause"
LONG_REQUEST_SECONDS = 120
ACTIVITY_KINDS = {"request", "job", "scheduler", "sync", "database-task", "event"}
_activity: ContextVar[str | None] = ContextVar("maintenance_activity", default=None)
_instance_id = uuid4().hex

ADMIT = """
local phase = redis.call('GET', KEYS[1])
if (phase == 'draining' or (phase == 'starting' and ARGV[2] ~= 'database-task'))
  and (ARGV[3] == '' or redis.call('HEXISTS', KEYS[2], ARGV[3]) == 0) then
  return 0
end
if (ARGV[2] == 'scheduler' or ARGV[2] == 'sync')
  and redis.call('EXISTS', KEYS[3]) == 1 then
  return -1
end
redis.call('HSET', KEYS[2], ARGV[1], ARGV[4])
return 1
"""

RELEASE_PAUSE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


class ActivitySummary(TypedDict):
    count: int
    oldest_seconds: int | None


class ReleasePreflight(TypedDict):
    pause_owned: bool
    blocking: int
    activities: dict[str, ActivitySummary]


class MaintenanceActiveError(RuntimeError):
    """New work was refused by the release barrier."""


class BackgroundPausedError(MaintenanceActiveError):
    """New synchronization was deferred while public traffic is still open."""


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
                ADMIT, 3, STATE_KEY, ACTIVE_KEY, BACKGROUND_PAUSE_KEY,
                identifier, kind, parent, metadata,
            ),
        )
    if admitted == -1:
        raise BackgroundPausedError("发布准备期间暂缓同步，请稍后重试")
    if not admitted:
        raise MaintenanceActiveError("系统维护中，尚未受理本次操作")
    return identifier


async def finish_activity(identifier: str) -> None:
    async with asyncio.timeout(3):
        await cast(Awaitable[int], redis_client.hdel(ACTIVE_KEY, identifier))


@asynccontextmanager
async def admitted_activity(
    identifier: str, *, preserve_on_error: bool = False
) -> AsyncIterator[None]:
    """Keep uncertain resource cleanup registered until explicitly confirmed."""
    context = _activity.set(identifier)
    try:
        yield
    except asyncio.CancelledError:
        # Keep evidence of work whose outcome could not be confirmed.
        raise
    except Exception:
        if not preserve_on_error:
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


async def pause_background_work(token: str, lease_seconds: int) -> bool:
    async with asyncio.timeout(3):
        acquired = await redis_client.set(
            BACKGROUND_PAUSE_KEY, token, ex=lease_seconds, nx=True
        )
        return bool(acquired)


async def resume_background_work(token: str) -> bool:
    async with asyncio.timeout(3):
        removed = await cast(
            Awaitable[int],
            redis_client.eval(RELEASE_PAUSE, 1, BACKGROUND_PAUSE_KEY, token),
        )
        return removed == 1


async def release_preflight(token: str = "") -> ReleasePreflight:
    """Summarize active work without exposing identifiers or business data."""
    async with asyncio.timeout(3), redis_client.pipeline(transaction=True) as pipe:
        pipe.get(BACKGROUND_PAUSE_KEY)
        pipe.hgetall(ACTIVE_KEY)
        lease, raw_entries = await pipe.execute()
    entries: dict[str, dict[str, object]] = {}
    for identifier, value in raw_entries.items():
        try:
            decoded = json.loads(value)
        except (ValueError, TypeError):
            decoded = None
        entries[identifier] = decoded if isinstance(decoded, dict) else {}

    now = time.time()
    activities: dict[str, ActivitySummary] = {}
    blocking = 0
    for metadata in entries.values():
        kind = metadata.get("kind")
        if not isinstance(kind, str) or kind not in ACTIVITY_KINDS:
            kind = "unknown"
        started = metadata.get("started_at")
        age = None
        if (
            isinstance(started, (int, float))
            and not isinstance(started, bool)
            and 0 < started <= now
        ):
            age = int(now - started)
        summary = activities.setdefault(kind, {"count": 0, "oldest_seconds": None})
        summary["count"] += 1
        if age is not None:
            oldest = summary["oldest_seconds"]
            summary["oldest_seconds"] = age if oldest is None else max(age, oldest)

        if kind == "request" and age is not None and age < LONG_REQUEST_SECONDS:
            continue
        parent = metadata.get("parent")
        if (
            kind == "database-task"
            and isinstance(parent, str)
            and entries.get(parent, {}).get("kind") == "request"
        ):
            # The request already represents its database work during online preflight.
            continue
        blocking += 1
    return {
        "pause_owned": bool(token) and lease == token,
        "blocking": blocking,
        "activities": activities,
    }


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
