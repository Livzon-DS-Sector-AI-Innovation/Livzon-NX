"""Equipment module test fixtures."""

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import get_db
from app.main import app
from app.platform.identity.deps import get_current_user
from app.platform.identity.models import User
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
async def _equipment_session() -> AsyncIterator[AsyncSession]:
    """Shared session for equipment API tests with test users pre-created."""
    async with _test_session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def test_reporter(_equipment_session: AsyncSession) -> User:
    """Create a test reporter user in the shared session."""
    user = User(name="测试报修人", employee_no=f"EMP-R-{uuid.uuid4().hex[:8]}")
    _equipment_session.add(user)
    await _equipment_session.flush()
    await _equipment_session.refresh(user)
    return user


@pytest.fixture
async def test_assignee(_equipment_session: AsyncSession) -> User:
    """Create a test assignee user in the shared session."""
    user = User(name="测试维修员", employee_no=f"EMP-A-{uuid.uuid4().hex[:8]}")
    _equipment_session.add(user)
    await _equipment_session.flush()
    await _equipment_session.refresh(user)
    return user


@pytest.fixture
async def client(
    _equipment_session: AsyncSession,
    test_reporter: User,
) -> AsyncIterator[AsyncClient]:
    """Provide an AsyncClient with get_db and get_current_user overridden."""
    session = _equipment_session

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        try:
            yield session
        finally:
            pass

    async def _override_get_current_user() -> User:
        return test_reporter

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
