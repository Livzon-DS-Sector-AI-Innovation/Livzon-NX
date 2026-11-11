"""Administration module test fixtures."""

import re
import uuid
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import unquote

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import get_db
from app.main import app
from app.platform.identity.deps import get_current_user
from app.platform.identity.models import User, UserPageGrant
from app.platform.identity.page_policy import api_binding_for_route
from tests.db_safety import get_pytest_database_url

settings = get_settings()

_test_engine = create_async_engine(
    get_pytest_database_url(settings),
    poolclass=pool.NullPool,
)
_test_session_factory = async_sessionmaker(
    _test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

#: 镜像路由 URL 自带 page_key（与真实前端一致：请求哪个页面就带哪个上下文）
_PAGE_KEY_IN_PATH = re.compile(r"/api/v1/administration/page-data/([^/]+)")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Provide an AsyncSession that rolls back after each test."""
    async with _test_session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def admin_user(db_session: AsyncSession) -> AsyncIterator[User]:
    """管理员身份：走依赖覆盖后中间件放行模块路由。"""
    user = User(
        name="行政管理测试员",
        employee_no=f"EMP-ADM-{uuid.uuid4().hex[:8]}",
        role="admin",
        status="active",
    )
    db_session.add(user)
    await db_session.flush()
    yield user
    await db_session.rollback()


@pytest.fixture
async def items_viewer(db_session: AsyncSession) -> AsyncIterator[User]:
    """仅持有「物品清单」页面授权的普通用户（跨页/越权用例用）。"""
    user = User(
        name="物品清单查看员",
        employee_no=f"EMP-USR-{uuid.uuid4().hex[:8]}",
        role="user",
        status="active",
        auth_source="local",
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        UserPageGrant(
            user_id=user.id,
            page_key="admin:tobacco-gift:items",
            permissions=["access", "query"],
            sensitive_actions=[],
            scope_type="all",
            department_ids=[],
        )
    )
    await db_session.flush()
    yield user
    await db_session.rollback()


def _client_with_user(
    db_session: AsyncSession, user: User
) -> AsyncIterator[AsyncClient]:
    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        try:
            yield db_session
        finally:
            pass

    async def _override_get_current_user() -> User:
        return user

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user
    transport = ASGITransport(app=app)

    async def _attach_registered_page_context(request: Any) -> None:
        """与全局 client 一致：按接口登记自动补页面上下文头。

        镜像读取路由的 URL 自带 page_key，优先用它——与真实前端请求的
        页面上下文一致，也保证新增的跨页强校验被用例真实覆盖。
        """
        if (
            "X-Dazah-Page-Key" in request.headers
            or "X-Dazah-Page-Path" in request.headers
        ):
            return
        from_path = _PAGE_KEY_IN_PATH.search(request.url.path)
        if from_path:
            request.headers["X-Dazah-Page-Key"] = unquote(from_path.group(1))
            return
        for route in app.routes:
            methods = getattr(route, "methods", None)
            path_regex = getattr(route, "path_regex", None)
            if (
                methods
                and request.method in methods
                and path_regex is not None
                and path_regex.fullmatch(request.url.path)
            ):
                binding = api_binding_for_route(request.method, route.path)
                if binding is not None and binding.page_keys:
                    request.headers["X-Dazah-Page-Key"] = binding.page_keys[0]
                return

    async def _client() -> AsyncIterator[AsyncClient]:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            event_hooks={"request": [_attach_registered_page_context]},
        ) as ac:
            yield ac

    return _client


@pytest.fixture
async def client(
    db_session: AsyncSession,
    admin_user: User,
) -> AsyncIterator[AsyncClient]:
    """AsyncClient with get_db and get_current_user overridden."""
    async for ac in _client_with_user(db_session, admin_user)():
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def viewer_client(
    db_session: AsyncSession,
    items_viewer: User,
) -> AsyncIterator[AsyncClient]:
    """仅授权「物品清单」页面的普通用户客户端。"""
    async for ac in _client_with_user(db_session, items_viewer)():
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def clean_feishu_config() -> AsyncIterator[None]:
    """前后清空飞书配置表：服务层 flush 后由请求会话提交，不能依赖回滚。

    使用独立会话，避免把共享会话里的测试用户一并提交。
    """
    from sqlalchemy import delete

    from app.modules.administration.models import AdministrationFeishuConfig

    async with _test_session_factory() as session:
        await session.execute(delete(AdministrationFeishuConfig))
        await session.commit()
    yield
    async with _test_session_factory() as session:
        await session.execute(delete(AdministrationFeishuConfig))
        await session.commit()
