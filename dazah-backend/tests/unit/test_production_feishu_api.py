"""production_feishu_api 飞书配置 端点测试（SQL 全 mock）。"""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest

from app.modules.production import production_feishu_api as api


def _config_obj() -> Any:
    return SimpleNamespace(
        id="cfg-1",
        name="测试配置",
        product_name="霉酚酸",
        app_id="cli_1234",
        bitable_app_token="sptoken",
        table_id="tbl123",
        is_active=True,
        remark="备注",
        sync_target="production_plan",
        field_mapping={},
        sync_table_name="mc_crude",
        encrypted_app_secret="enc",
        app_secret="secret",
        created_at=datetime(2026, 8, 1),
        updated_at=datetime(2026, 8, 2),
    )


class _Scalars:
    def __init__(self, items: Any) -> None:
        self._items = items

    def all(self) -> Any:
        return self._items

    def first(self) -> Any:
        return self._items[0] if self._items else None


class _Result:
    def __init__(self, items: Any) -> None:
        self._s = _Scalars(items)

    def scalars(self) -> Any:
        return self._s


@pytest.mark.anyio
async def test__config_to_dict() -> Any:
    """_config_to_dict: 序列化配置对象。"""
    c = _config_obj()
    d = api._config_to_dict(c)
    assert d["id"] == "cfg-1"
    assert d["product_name"] == "霉酚酸"
    assert d["app_secret_configured"] is True
    assert d["app_secret_masked"] == "1234"
    assert d["sync_target"] == "production_plan"
    assert d["created_at"] == "2026-08-01T00:00:00"


@pytest.mark.anyio
async def test_list_feishu_configs() -> Any:
    """list_feishu_configs: 返回配置列表。"""
    session = AsyncMock()
    session.execute.return_value = _Result([_config_obj()])
    resp = await api.list_feishu_configs(session=session)
    data = json.loads(resp.body)["data"]
    assert len(data) == 1
    assert data[0]["product_name"] == "霉酚酸"


@pytest.mark.anyio
async def test_upsert_feishu_config_create() -> Any:
    """upsert_feishu_config: 创建新配置。"""
    session = AsyncMock()
    session.execute.return_value = _Result([])  # 无已有配置
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    def _refresh(config: Any) -> Any:
        config.created_at = datetime(2026, 8, 1)
        config.updated_at = datetime(2026, 8, 2)

    session.refresh = AsyncMock(side_effect=_refresh)

    body = SimpleNamespace(
        name="新配置", product_name="霉酚酸", app_id="cli_new",
        app_secret="secret", bitable_app_token="tok", table_id="tbx",
        sync_target="production_plan", is_active=True, remark="r",
    )
    with patch.object(
        api, "encrypt_secret", return_value="enc-secret"
    ), patch(
        "app.modules.production.auto_sync_service.discover_and_save_mapping",
        new=AsyncMock(return_value=None),
    ):
        resp = await api.upsert_feishu_config(
            body=cast(api.ProductionFeishuConfigUpsert, body), session=session
        )
    assert json.loads(resp.body)["message"] == "配置已保存"


@pytest.mark.anyio
async def test_upsert_feishu_config_update() -> Any:
    """upsert_feishu_config: 更新已有配置。"""
    session = AsyncMock()
    session.execute.return_value = _Result([_config_obj()])  # 已有配置
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.commit = AsyncMock()

    body = SimpleNamespace(
        name="更新配置", product_name="霉酚酸", app_id="cli_new",
        app_secret="new_secret", bitable_app_token="tok2", table_id="tbx2",
        sync_target="production_plan", is_active=False, remark="r2",
    )
    with patch.object(
        api, "encrypt_secret", return_value="enc-secret"
    ), patch(
        "app.modules.production.auto_sync_service.discover_and_save_mapping",
        new=AsyncMock(return_value=None),
    ):
        resp = await api.upsert_feishu_config(
            body=cast(api.ProductionFeishuConfigUpsert, body), session=session
        )
    assert json.loads(resp.body)["message"] == "配置已保存"
