"""Container-internal readiness probe; deliberately no public HTTP endpoint."""
import asyncio
import sys
from urllib.request import urlopen


async def check() -> None:
    from redis.asyncio import Redis
    from sqlalchemy import text
    from app.core.config import get_settings
    from app.core.database import engine

    settings = get_settings()
    redis = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=3, socket_timeout=3)
    async def dependencies() -> None:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        await redis.ping()
        if settings.MINIO_ENABLED:
            scheme = "https" if settings.MINIO_SECURE else "http"
            url = f"{scheme}://{settings.MINIO_ENDPOINT}/minio/health/ready"
            def probe() -> None:
                with urlopen(url, timeout=3) as response:
                    if response.status != 200:
                        raise RuntimeError("storage not ready")
            await asyncio.to_thread(probe)
    try:
        await asyncio.wait_for(dependencies(), timeout=8)
    finally:
        try:
            await redis.aclose()
        finally:
            await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(check())
    except Exception:
        print("not-ready")
        sys.exit(1)
    print("ready")
