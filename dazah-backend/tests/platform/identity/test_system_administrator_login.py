from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.platform.identity import service
from app.platform.identity.models import User


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["admin", "user"])
async def test_sso_preserves_explicit_administrator_identity(monkeypatch, role):
    user = User(id=uuid4(), name="登录测试", role=role, status="active")
    oauth = SimpleNamespace(
        app_id="test-app",
        exchange_code=AsyncMock(return_value={"access_token": "synthetic-test-token"}),
        get_user_info=AsyncMock(
            return_value={"open_id": "test-open-id", "name": "登录测试"}
        ),
    )
    monkeypatch.setattr(service.FeishuOAuthClient, "from_settings", lambda: oauth)
    monkeypatch.setattr(
        service, "_get_oauth_directory_profile", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        service._repo, "get_by_feishu_open_id", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(service, "_save_feishu_user_token", AsyncMock())
    monkeypatch.setattr(
        service, "get_settings", lambda: SimpleNamespace(SSO_ADMIN_IDENTIFIERS="")
    )
    monkeypatch.setattr(service, "generate_jwt", lambda _: "synthetic-test-jwt")
    returned, _ = await service.handle_oauth_callback(AsyncMock(), "test-code")
    assert returned.role == role
