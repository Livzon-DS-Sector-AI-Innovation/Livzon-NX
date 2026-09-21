"""仓储编辑权限按子领域细分（成品/五金/原辅料及包材）测试。"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.modules.warehouse.api import _assert_warehouse_edit_scope


def test_assert_edit_scope_allows_subscope_code() -> None:
    """拥有对应子领域细分码 → 通过。"""
    _assert_warehouse_edit_scope(
        "product-summary", ["warehouse:read", "warehouse:product:write"]
    )
    _assert_warehouse_edit_scope(
        "hardware-summary", ["warehouse:read", "warehouse:hardware:write"]
    )
    _assert_warehouse_edit_scope(
        "raw-summary", ["warehouse:read", "warehouse:raw:write"]
    )
    # 液体入库页归类 raw 子领域
    _assert_warehouse_edit_scope(
        "liquid-raw-inbound", ["warehouse:read", "warehouse:raw:write"]
    )


def test_assert_edit_scope_allows_module_write_and_wildcard() -> None:
    """模块级 warehouse:write 与通配（super_admin）→ 全部通过。"""
    _assert_warehouse_edit_scope("product-summary", ["warehouse:write"])
    _assert_warehouse_edit_scope("hardware-summary", ["*"])


def test_assert_edit_scope_forbidden_wrong_subscope() -> None:
    """其他子领域细分码或仅 read → 403。"""
    with pytest.raises(HTTPException) as exc:
        _assert_warehouse_edit_scope(
            "product-summary",
            ["warehouse:read", "warehouse:raw:write"],
        )
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException):
        _assert_warehouse_edit_scope("hardware-summary", ["warehouse:read"])


def test_edit_scope_permission_covers_all_registered_pages() -> None:
    """页面注册表中全部 page_key 都有细分权限映射（换 Base 不影响权限）。"""
    from app.modules.warehouse.api import WAREHOUSE_EDIT_SCOPE_PERMISSION
    from app.modules.warehouse.feishu_material_pages import (
        FEISHU_WAREHOUSE_MATERIAL_PAGES,
    )

    for page_key in FEISHU_WAREHOUSE_MATERIAL_PAGES:
        assert page_key in WAREHOUSE_EDIT_SCOPE_PERMISSION, page_key
