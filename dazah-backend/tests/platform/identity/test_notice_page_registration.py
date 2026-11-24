"""公告通知页登记守护：lifecycle/菜单种子/路由目录/page_policy 绑定一致。

公告通知为平台原生台账（非飞书镜像）：元数据随 query 放行，公告内容与
原文仅经 operate 绑定的专用端点下发，删除挂已登记的 delete 动作。
"""

import json
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[3]
PAGE_KEY = "admin:notice"
ROUTE = "/admin/notice"


def test_lifecycle_registers_notice_page():
    data = json.loads(
        (
            BACKEND_ROOT / "app/platform/identity/page_permission_lifecycle.json"
        ).read_text(encoding="utf-8")
    )
    pages = data["pages"]
    assert PAGE_KEY in pages, "公告通知未登记 page_permission_lifecycle"
    entry = pages[PAGE_KEY]
    assert entry["route_path"] == ROUTE
    assert entry["module_code"] == "administration"
    assert entry["status"] == "active"
    # 删除台账记录是破坏性动作；内容/原文读取绑定 operate 而非敏感动作
    assert entry["actions"] == {
        "delete": {"status": "active", "category": "destructive"}
    }


def test_menu_seed_enables_notice_page():
    from app.platform.identity.menu_seed_data import _LEGACY_SEED_MENUS

    def _walk(nodes):
        for node in nodes:
            yield node
            yield from _walk(node.get("children") or [])

    matched = [n for n in _walk(_LEGACY_SEED_MENUS) if n.get("key") == "notice"]
    assert matched, "菜单种子缺公告通知项"
    node = matched[0]
    assert node.get("path") == ROUTE
    assert node.get("name") == "公告通知"
    assert not node.get("disabled"), "公告通知菜单仍处于禁用状态"


def test_route_catalog_contains_notice_page():
    data = json.loads(
        (BACKEND_ROOT / "app/platform/identity/page_route_catalog.json").read_text(
            encoding="utf-8"
        )
    )
    text = json.dumps(data, ensure_ascii=False)
    assert ROUTE in text, "页面路由目录缺 /admin/notice（跑 generate-page-routes.py）"


def _notice_bindings(method: str, suffix: str):
    from app.platform.identity.page_policy import PAGE_API_BINDINGS

    route_path = f"/api/v1/administration/notices{suffix}"
    return [
        binding
        for binding in PAGE_API_BINDINGS
        if binding.route_path == route_path and binding.method == method
    ]


def test_page_policy_registers_notice_page_and_bindings():
    from app.platform.identity.page_policy import PAGE_API_BINDINGS, PAGES_BY_KEY

    assert PAGE_KEY in PAGES_BY_KEY, "admin:notice 不在 PAGE_DEFINITIONS"

    query_expectations = {
        ("GET", ""): "query",
        ("GET", "/{notice_id}"): "query",
    }
    operate_expectations = {
        ("POST", "/parse"): "operate",
        ("POST", ""): "operate",
        ("GET", "/{notice_id}/content"): "operate",
        ("GET", "/{notice_id}/file"): "operate",
        ("PUT", "/{notice_id}"): "operate",
    }
    expectations = {**query_expectations, **operate_expectations}
    for (method, suffix), permission in expectations.items():
        bindings = _notice_bindings(method, suffix)
        assert bindings, f"公告接口未登记绑定: {method} /notices{suffix}"
        assert all(binding.permission == permission for binding in bindings), (
            f"公告接口权限口径不符: {method} /notices{suffix}"
        )
        assert all(PAGE_KEY in binding.page_keys for binding in bindings), (
            f"公告接口绑定页面不符: {method} /notices{suffix}"
        )

    deletes = _notice_bindings("DELETE", "/{notice_id}")
    assert deletes, "公告删除接口未登记绑定"
    assert all(
        binding.permission == "operate" and binding.sensitive_action == "delete"
        for binding in deletes
    ), "公告删除必须是 operate + delete 动作"

    # 内容与原文端点不允许出现 query 口径绑定（fail closed）
    leaked = [
        binding
        for binding in PAGE_API_BINDINGS
        if binding.route_path.startswith("/api/v1/administration/notices")
        and ("/content" in binding.route_path or binding.route_path.endswith("/file"))
        and binding.permission != "operate"
    ]
    assert not leaked, "公告内容/原文端点存在非 operate 绑定"
