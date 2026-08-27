from __future__ import annotations

import warnings
from collections.abc import Iterator
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
