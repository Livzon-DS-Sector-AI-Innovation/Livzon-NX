from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from httpx import AsyncClient

from app.main import app
from app.platform.identity.deps import get_current_user
from app.platform.identity.models import User


@pytest.fixture(autouse=True)
async def _authenticate_hr_routes(client: AsyncClient) -> AsyncIterator[None]:
    """Provide the stable local test identity used by migrated HR contracts."""
    user = User(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        name="人事模块测试管理员",
        username="hr-migration-admin",
        role="admin",
        status="active",
        auth_source="local",
        feishu_open_id="hr-source-migration-open-id",
        department="SPEC测试车间",
    )

    async def _override_current_user() -> User:
        return user

    app.dependency_overrides[get_current_user] = _override_current_user
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_user, None)
