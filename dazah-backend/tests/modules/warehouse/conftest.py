from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.main import app
from app.platform.identity.deps import get_current_user
from app.platform.identity.models import User


@pytest.fixture(autouse=True)
async def _authenticate_warehouse_routes(
    client: AsyncClient,
) -> AsyncIterator[None]:
    """Use an admin identity for migrated warehouse contract tests."""
    user = User(
        id=uuid4(),
        name="仓储模块测试管理员",
        username="warehouse-migration-admin",
        role="admin",
        status="active",
        auth_source="local",
    )

    async def _override_current_user() -> User:
        return user

    app.dependency_overrides[get_current_user] = _override_current_user
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_user, None)
