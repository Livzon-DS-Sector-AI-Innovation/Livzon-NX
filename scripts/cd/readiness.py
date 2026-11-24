"""Container-internal readiness probe; deliberately no public HTTP endpoint."""
import asyncio
import sys
from urllib.request import urlopen


async def check(*, healthcheck: bool = False) -> None:
    from redis.asyncio import Redis

    from app.core.config import get_settings

    settings = get_settings()
    redis = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=3, socket_timeout=3)

    if healthcheck:
        def check_http() -> None:
            with urlopen("http://127.0.0.1:8000/health", timeout=2) as response:
                if response.status != 200:
                    raise RuntimeError("application not live")

        try:
            await asyncio.to_thread(check_http)
            if not await asyncio.wait_for(redis.ping(), timeout=2):
                raise RuntimeError("Redis not ready")
        finally:
            await redis.aclose()
        return

    from sqlalchemy import text

    from app.core.database import engine

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
        asyncio.run(check(healthcheck=sys.argv[1:] == ["--healthcheck"]))
    except Exception:
        print("not-ready")
        sys.exit(1)
    print("ready")
