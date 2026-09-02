from types import SimpleNamespace as _SimpleNamespace
from typing import Any

import pytest

from app.platform.identity import public_api

SimpleNamespace: Any = _SimpleNamespace


class _FakeRepository:
    def __init__(self: Any, config: Any) -> None:
        self.config = config

    async def get_active(self: Any, _db: Any) -> Any:
        return self.config


@pytest.mark.anyio
async def test_platform_feishu_credentials_prefer_active_database_config(
    monkeypatch: Any,
) -> Any:
    config: Any = SimpleNamespace(
        app_id="db-app-id",
        encrypted_app_secret="encrypted-secret",
    )
    monkeypatch.setattr(
        public_api,
        "FeishuConfigRepository",
        lambda: _FakeRepository(config),
    )
    monkeypatch.setattr(public_api, "decrypt_secret", lambda value: f"plain:{value}")

    credentials = await public_api.get_platform_feishu_app_credentials(None)  # type: ignore[arg-type]

    assert credentials is not None
    assert credentials.app_id == "db-app-id"
    assert credentials.app_secret == "plain:encrypted-secret"


@pytest.mark.anyio
async def test_platform_feishu_credentials_do_not_fall_back_to_environment(
    monkeypatch: Any,
) -> Any:
    monkeypatch.setattr(
        public_api,
        "FeishuConfigRepository",
        lambda: _FakeRepository(None),
    )

    credentials = await public_api.get_platform_feishu_app_credentials(None)  # type: ignore[arg-type]

    assert credentials is None


@pytest.mark.anyio
async def test_platform_feishu_credentials_return_none_when_unconfigured(
    monkeypatch: Any,
) -> Any:
    monkeypatch.setattr(
        public_api,
        "FeishuConfigRepository",
        lambda: _FakeRepository(None),
    )

    assert await public_api.get_platform_feishu_app_credentials(None) is None  # type: ignore[arg-type]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "user,expected",
    [
        (
            SimpleNamespace(feishu_user_id="employee", enterprise_email=None),
            ("employee", "user_id"),
        ),
        (
            SimpleNamespace(feishu_user_id=None, enterprise_email="user@example.test"),
            ("user@example.test", "email"),
        ),
        (SimpleNamespace(feishu_user_id=None, enterprise_email=None), None),
        (None, ("ou-module", "open_id")),
    ],
)
async def test_notification_recipient_avoids_login_open_id(monkeypatch, user, expected):
    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        public_api.UserRepository, "get_by_feishu_open_id", AsyncMock(return_value=user)
    )
    assert (
        await public_api.resolve_feishu_notification_recipient(
            AsyncMock(), "ou-module", "open_id"
        )
        == expected
    )
