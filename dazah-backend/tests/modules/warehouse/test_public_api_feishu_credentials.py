"""warehouse.public_api.get_active_feishu_credentials 单元行为。"""

from types import SimpleNamespace
from typing import Any

import pytest

from app.modules.warehouse import public_api


@pytest.mark.anyio
async def test_get_active_feishu_credentials_returns_none_without_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _no_config(self: Any) -> Any:
        return None

    monkeypatch.setattr(
        public_api.WarehouseService, "get_active_feishu_config", _no_config
    )
    assert await public_api.get_active_feishu_credentials(object()) is None


@pytest.mark.anyio
async def test_get_active_feishu_credentials_returns_none_for_incomplete_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = SimpleNamespace(app_id="", encrypted_app_secret="whatever")

    async def _incomplete_config(self: Any) -> Any:
        return config

    monkeypatch.setattr(
        public_api.WarehouseService, "get_active_feishu_config", _incomplete_config
    )
    assert await public_api.get_active_feishu_credentials(object()) is None


@pytest.mark.anyio
async def test_get_active_feishu_credentials_decrypts_active_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = SimpleNamespace(app_id="cli_wh", encrypted_app_secret="wh-secret-plain")

    async def _active_config(self: Any) -> Any:
        return config

    monkeypatch.setattr(
        public_api.WarehouseService, "get_active_feishu_config", _active_config
    )
    credentials = await public_api.get_active_feishu_credentials(object())
    assert credentials is not None
    assert credentials.app_id == "cli_wh"
    # 非 fernet 密文按原样返回（解密器对无效 token 回退原文），不落日志
    assert credentials.app_secret == "wh-secret-plain"
