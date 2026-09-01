from __future__ import annotations

import warnings
from collections.abc import Iterator
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic.warnings import PydanticDeprecatedSince20

from app.main import app
from app.platform.identity.deps import get_current_user
from app.platform.identity.models import User

# Keep quality test output focused on quality warnings only.
warnings.filterwarnings("ignore", category=PydanticDeprecatedSince20)
warnings.filterwarnings(
    "ignore",
    message=r".*utcfromtimestamp\(\) is deprecated.*",
    category=DeprecationWarning,
)
warnings.filterwarnings(
    "ignore",
    message=r".*There is no current event loop.*",
    category=DeprecationWarning,
)


@pytest.fixture(autouse=True)
def _grant_quality_permissions(monkeypatch: pytest.MonkeyPatch) -> None:
    """质量端点内精校验依赖 resolve_user_permissions；测试用户视为通配权限。

    针对子域/记录归属的精细化行为由 test_edit_scope.py 自行打桩覆盖。
    """
    from app.modules.quality.api import deps as quality_deps

    monkeypatch.setattr(
        quality_deps,
        "resolve_user_permissions",
        AsyncMock(return_value=["*"]),
    )


@pytest.fixture(autouse=True)
def _authenticate_quality_routes() -> Iterator[None]:
    """Run quality API tests through the platform's module authorization guard."""
    user = User(
        id=uuid4(),
        name="质量模块测试管理员",
        username="quality-test-admin",
        role="admin",
        status="active",
        auth_source="local",
    )

    async def _override_current_user() -> User:
        return user

    app.dependency_overrides[get_current_user] = _override_current_user
    yield
    app.dependency_overrides.pop(get_current_user, None)
