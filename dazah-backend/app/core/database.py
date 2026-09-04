from collections.abc import AsyncGenerator

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.shared.module_registry import BUSINESS_SCHEMAS

settings = get_settings()

_search_path = "public,identity,core," + ",".join(BUSINESS_SCHEMAS)

# 测试环境（APP_ENV=test）使用 NullPool：pytest 每个测试运行在独立事件循环上，
# QueuePool 的长连接会绑定到已关闭的循环，Linux 上孤儿连接不被及时回收，
# 累积后打满 PostgreSQL max_connections；NullPool 让连接在当前循环用完即关。
def _build_engine_kwargs(app_env: str) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "echo": settings.DEBUG,
        "pool_pre_ping": True,
        "pool_size": 10,
        "max_overflow": 20,
        "connect_args": {"server_settings": {"search_path": _search_path}},
    }
    if app_env == "test":
        kwargs["poolclass"] = pool.NullPool
        kwargs.pop("pool_size", None)
        kwargs.pop("max_overflow", None)
        kwargs.pop("pool_pre_ping", None)
    return kwargs


engine = create_async_engine(
    settings.DATABASE_URL,
    **_build_engine_kwargs(settings.APP_ENV),
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
