"""仓储编辑权限按子领域细分（成品/五金/原辅料及包材）测试。"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.modules.warehouse.api import _assert_warehouse_edit_scope
from app.modules.warehouse.feishu_material_pages import (
    FEISHU_FINISHED_PRODUCT_APP_TOKEN,
    FEISHU_HARDWARE_APP_TOKEN,
    FEISHU_WAREHOUSE_APP_TOKEN,
)


def test_assert_edit_scope_allows_subscope_code() -> None:
    """拥有对应子领域细分码 → 通过。"""
    _assert_warehouse_edit_scope(
        FEISHU_FINISHED_PRODUCT_APP_TOKEN, ["warehouse:read", "warehouse:product:write"]
    )
    _assert_warehouse_edit_scope(
        FEISHU_HARDWARE_APP_TOKEN, ["warehouse:read", "warehouse:hardware:write"]
    )
    _assert_warehouse_edit_scope(
        FEISHU_WAREHOUSE_APP_TOKEN, ["warehouse:read", "warehouse:raw:write"]
    )


def test_assert_edit_scope_allows_module_write_and_wildcard() -> None:
    """模块级 warehouse:write 与通配（super_admin）→ 全部通过。"""
    _assert_warehouse_edit_scope(FEISHU_FINISHED_PRODUCT_APP_TOKEN, ["warehouse:write"])
    _assert_warehouse_edit_scope(FEISHU_HARDWARE_APP_TOKEN, ["*"])


def test_assert_edit_scope_forbidden_wrong_subscope() -> None:
    """其他子领域细分码或仅 read → 403。"""
    with pytest.raises(HTTPException) as exc:
        _assert_warehouse_edit_scope(
            FEISHU_FINISHED_PRODUCT_APP_TOKEN,
            ["warehouse:read", "warehouse:raw:write"],
        )
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException):
        _assert_warehouse_edit_scope(FEISHU_HARDWARE_APP_TOKEN, ["warehouse:read"])
