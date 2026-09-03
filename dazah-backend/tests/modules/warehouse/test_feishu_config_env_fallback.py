"""仓储飞书凭证必须来自仓储模块数据库配置。"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.modules.warehouse.service import WarehouseService


@pytest.fixture
def empty_repo(monkeypatch: pytest.MonkeyPatch) -> WarehouseService:
    """repo 查询返回 None（无任何配置行）的 service。"""
    service = WarehouseService.__new__(WarehouseService)
    service.repo = AsyncMock()
    service.repo.get_active_feishu_config = AsyncMock(return_value=None)
    service.repo.get_any_feishu_config = AsyncMock(return_value=None)
    return service


@pytest.fixture
def platform_env_creds(monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    """显式注入平台共享飞书凭据，测试不依赖运行环境的 .env 取值。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "FEISHU_APP_ID", "cli_platform_app", raising=False)
    monkeypatch.setattr(settings, "FEISHU_APP_SECRET", "platform-secret", raising=False)
    return "cli_platform_app", "platform-secret"


async def test_active_config_does_not_fallback_to_platform_env(
    empty_repo: WarehouseService, platform_env_creds: tuple[str, str]
) -> None:
    """即使平台 env 有凭据，仓储未配置时也必须拒绝访问。"""
    with pytest.raises(AppException, match="请先启用仓储飞书配置"):
        await empty_repo._get_active_feishu_config_or_raise()


async def test_any_config_variant_does_not_fallback_to_platform_env(
    empty_repo: WarehouseService, platform_env_creds: tuple[str, str]
) -> None:
    """通用配置读取同样不得回退平台 env。"""
    assert await empty_repo._get_any_feishu_config_or_raise() is None
