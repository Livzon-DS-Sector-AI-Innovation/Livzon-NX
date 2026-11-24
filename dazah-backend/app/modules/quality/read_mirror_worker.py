"""Run the quality read-only mirror scheduler as a standalone process."""

import asyncio
import logging
import os
import signal

from app.core.config import get_settings
from app.core.database import async_session_factory, engine
from app.core.redis import redis_client
from app.core.schema_guard import assert_database_schema_current
from app.platform.integrations.feishu.read_scheduler import register_quality_read_mirror
from app.platform.scheduler import SchedulerEngine, SchedulerRegistry
from app.platform.scheduler.worker_health import READY_FILE


async def run() -> None:
    settings = get_settings()
    if settings.QUALITY_READ_MIRROR_SCHEDULER != "worker":
        raise RuntimeError("QUALITY_READ_MIRROR_SCHEDULER=worker is required")

    READY_FILE.unlink(missing_ok=True)
    registry = SchedulerRegistry()
    scheduler = SchedulerEngine(registry)
    loop = asyncio.get_running_loop()

    def stop(_signum: int, _frame: object) -> None:
        loop.call_soon_threadsafe(scheduler.stop)

    previous = {
        sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        async with async_session_factory() as session:
            await assert_database_schema_current(session)
        register_quality_read_mirror(registry, settings, owner="worker")
        READY_FILE.write_text(str(os.getpid()))
        await scheduler.run()
    finally:
        READY_FILE.unlink(missing_ok=True)
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        try:
            await redis_client.aclose()
        finally:
            await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    asyncio.run(run())
