"""Container readiness probe for a registered scheduler worker."""

import asyncio
import logging
import os
from collections.abc import Awaitable
from pathlib import Path
from typing import cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import engine
from app.core.redis import redis_client

READY_FILE = Path("/tmp/dazah-scheduler-worker-ready")


async def healthcheck() -> None:
    """Probe the initialized process and its dependencies during maintenance."""
    pid = int(READY_FILE.read_text())
    if pid <= 0:
        raise RuntimeError("invalid scheduler worker PID")
    os.kill(pid, 0)
    try:
        async with asyncio.timeout(5), AsyncSession(engine) as session:
            await session.execute(text("SELECT 1"))
            if not await cast(Awaitable[bool], redis_client.ping()):
                raise RuntimeError("scheduler worker Redis ping failed")
    finally:
        try:
            await redis_client.aclose()
        finally:
            await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(healthcheck())
    except Exception as exc:
        logging.error("Scheduler worker not ready (%s)", type(exc).__name__)
        raise SystemExit(1) from None
