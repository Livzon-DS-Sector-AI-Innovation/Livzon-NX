from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import get_db
from app.main import app  # noqa: A001
from app.platform.identity.models import User  # noqa: F401
from tests.db_safety import get_pytest_database_url

settings = get_settings()

# Test engine uses NullPool so each test gets a fresh connection on its own event loop.
_test_engine = create_async_engine(
    get_pytest_database_url(settings),
    poolclass=pool.NullPool,
)
_test_session_factory = async_sessionmaker(
    _test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest.fixture
def anyio_backend() -> tuple[str, dict[str, Any]]:
    # 强制标准 asyncio loop：CI(Linux) 装有 uvloop，anyio 默认会选用它，
    # 而 pytest-asyncio 驱动的测试与 app 全局 engine 走标准 asyncio——
    # 两套 loop 并存时 asyncpg 连接的 Future 跨 loop，报
    # "got Future attached to a different loop"（347 errors 的根因）。
    # Windows 本地无 uvloop 天然不复现。
    return "asyncio", {"use_uvloop": False}


@pytest.fixture(autouse=True)
async def _dispose_app_engine_pools() -> AsyncIterator[None]:
    """每个测试结束后释放 app 全局 engine 与测试引擎的池连接。

    app 的全局 engine 使用 QueuePool（pool_size=10 + max_overflow=20），集成测试
    通过 ASGITransport 触发其连接；pytest 的每个测试运行在独立事件循环上，绑定
    到已关闭循环的池连接不会被复用。Linux CI 上这些孤儿连接依赖 GC 回收，累积
    后会打满 PostgreSQL 的 max_connections（TooManyConnectionsError）。测试结束
    时显式 dispose，保证池连接不跨测试累积。测试引擎（NullPool）也随测试 dispose，
    避免跨事件循环的未完成关闭产生孤儿连接。
    """
    yield
    try:
        from app.core.database import engine

        await engine.dispose()
    except Exception:  # noqa: BLE001 —— 清理失败不应影响测试结果
        pass
    try:
        await _test_engine.dispose()
    except Exception:  # noqa: BLE001
        pass


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Provide an AsyncSession that rolls back after each test."""
    async with _test_session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Provide an AsyncClient with get_db overridden to use a rolled-back session."""
    async with _test_session_factory() as session:

        async def _override_get_db() -> AsyncIterator[AsyncSession]:
            try:
                yield session
            finally:
                pass  # session lifecycle is managed by the outer fixture

        app.dependency_overrides[get_db] = _override_get_db
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
        app.dependency_overrides.clear()
        await session.rollback()
