from types import SimpleNamespace

import pytest

from app.platform.identity import public_api


class _FakeRepository:
    def __init__(self, config) -> None:
        self.config = config

    async def get_active(self, _db):
        return self.config


@pytest.mark.anyio
async def test_platform_feishu_credentials_prefer_active_database_config(monkeypatch):
    config = SimpleNamespace(
        app_id="db-app-id",
        encrypted_app_secret="encrypted-secret",
    )
    monkeypatch.setattr(
        public_api,
        "FeishuConfigRepository",
        lambda: _FakeRepository(config),
    )
    monkeypatch.setattr(public_api, "decrypt_secret", lambda value: f"plain:{value}")
    monkeypatch.setattr(
        public_api,
        "get_settings",
        lambda: SimpleNamespace(
            FEISHU_APP_ID="env-app-id",
            FEISHU_APP_SECRET="env-secret",
        ),
    )

    credentials = await public_api.get_platform_feishu_app_credentials(None)

    assert credentials is not None
    assert credentials.app_id == "db-app-id"
    assert credentials.app_secret == "plain:encrypted-secret"


@pytest.mark.anyio
async def test_platform_feishu_credentials_fall_back_to_environment(monkeypatch):
    monkeypatch.setattr(
        public_api,
        "FeishuConfigRepository",
        lambda: _FakeRepository(None),
    )
    monkeypatch.setattr(
        public_api,
        "get_settings",
        lambda: SimpleNamespace(
            FEISHU_APP_ID="env-app-id",
            FEISHU_APP_SECRET="env-secret",
        ),
    )

    credentials = await public_api.get_platform_feishu_app_credentials(None)

    assert credentials is not None
    assert credentials.app_id == "env-app-id"
    assert credentials.app_secret == "env-secret"


@pytest.mark.anyio
async def test_platform_feishu_credentials_return_none_when_unconfigured(monkeypatch):
    monkeypatch.setattr(
        public_api,
        "FeishuConfigRepository",
        lambda: _FakeRepository(None),
    )
    monkeypatch.setattr(
        public_api,
        "get_settings",
        lambda: SimpleNamespace(FEISHU_APP_ID="", FEISHU_APP_SECRET=""),
    )

    assert await public_api.get_platform_feishu_app_credentials(None) is None
