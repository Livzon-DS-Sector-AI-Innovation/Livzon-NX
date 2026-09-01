"""仓储飞书凭证 env 回退测试。

warehouse.feishu_configs 无行时（首次部署/未保存凭证），
_get_active_feishu_config_or_raise 应回退平台 env 凭据构造内存配置，
对齐 quality/hr 模式；env 也为空时保持原"请先启用仓储飞书配置"错误。
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.core.config import get_settings
from app.core.secrets import decrypt_secret
from app.modules.warehouse.service import WarehouseService


@pytest.fixture
def empty_repo(monkeypatch: pytest.MonkeyPatch) -> WarehouseService:
    """repo 查询返回 None（无任何配置行）的 service。"""
    service = WarehouseService.__new__(WarehouseService)
    service.repo = AsyncMock()
    service.repo.get_active_feishu_config = AsyncMock(return_value=None)
    service.repo.get_any_feishu_config = AsyncMock(return_value=None)
    return service


async def test_env_fallback_returns_config_when_env_configured(
    empty_repo: WarehouseService,
) -> None:
    """env 有凭据时回退返回内存配置，secret 可解密还原。"""
    config = await empty_repo._get_active_feishu_config_or_raise()

    assert config is not None
    assert config.app_id == get_settings().FEISHU_APP_ID
    assert decrypt_secret(config.encrypted_app_secret) == (
        get_settings().FEISHU_APP_SECRET
    )
    assert config.is_active is True


async def test_env_fallback_raises_when_env_empty(
    empty_repo: WarehouseService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """env 也为空时保持原"请先启用仓储飞书配置"错误。"""
    from app.core.exceptions import AppException

    monkeypatch.setattr(
        type(empty_repo),
        "_env_fallback_feishu_config",
        staticmethod(lambda: None),
    )

    with pytest.raises(AppException, match="请先启用仓储飞书配置"):
        await empty_repo._get_active_feishu_config_or_raise()


async def test_any_config_variant_also_falls_back(
    empty_repo: WarehouseService,
) -> None:
    """_get_any_feishu_config_or_raise 同样具备 env 回退。"""
    config = await empty_repo._get_any_feishu_config_or_raise()

    assert config is not None
    assert config.app_id == get_settings().FEISHU_APP_ID
