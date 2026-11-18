"""印章管理/废旧物资页四处登记守护：lifecycle/菜单种子/路由目录/page_policy 一致。"""

import json
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[3]
PAGES = {
    "admin:seals": "/admin/seals",
    "admin:scrap-materials": "/admin/scrap-materials",
}


def test_lifecycle_registers_mirror_pages():
    data = json.loads(
        (
            BACKEND_ROOT / "app/platform/identity/page_permission_lifecycle.json"
        ).read_text(encoding="utf-8")
    )
    pages = data["pages"]
    for page_key, route in PAGES.items():
        assert page_key in pages, f"{page_key} 未登记 page_permission_lifecycle"
        entry = pages[page_key]
        assert entry["route_path"] == route
        assert entry["module_code"] == "administration"
        assert entry["status"] == "active"
        # 只读镜像页无高风险动作
        assert entry["actions"] == {}


def test_menu_seed_includes_mirror_pages():
    from app.platform.identity.menu_seed_data import _LEGACY_SEED_MENUS

    def _walk(nodes):
        for node in nodes:
            yield node
            yield from _walk(node.get("children") or [])

    flat = [n for n in _walk(_LEGACY_SEED_MENUS)]
    for key, name in (("seals", "印章管理"), ("scrap-materials", "废旧物资")):
        matched = [n for n in flat if n.get("key") == key]
        assert matched, f"菜单种子缺 {name} 项"
        assert matched[0].get("path") == PAGES[f"admin:{key}"]
        assert matched[0].get("name") == name


def test_route_catalog_contains_mirror_pages():
    data = json.loads(
        (BACKEND_ROOT / "app/platform/identity/page_route_catalog.json").read_text(
            encoding="utf-8"
        )
    )
    text = json.dumps(data, ensure_ascii=False)
    for route in PAGES.values():
        assert route in text, f"页面路由目录缺 {route}（跑 generate-page-routes.py）"


def test_page_policy_binds_mirror_pages_to_page_data_api():
    from app.platform.identity.page_policy import PAGE_API_BINDINGS, PAGES_BY_KEY

    for page_key in PAGES:
        assert page_key in PAGES_BY_KEY, (
            f"{page_key} 不在 PAGE_DEFINITIONS（菜单种子未生效）"
        )
    read_page = {
        binding.page_keys
        for binding in PAGE_API_BINDINGS
        if binding.route_path == "/api/v1/administration/page-data/{page_key}"
        and binding.method == "GET"
    }
    assert read_page, "绑定回显路由未登记"
    # 绑定回显路由必须覆盖新两页与烟酒礼品两页、飞书设置页
    union_read = set().union(*read_page)
    assert set(PAGES) <= union_read
    assert {"admin:tobacco-gift:items", "admin:tobacco-gift:records"} <= union_read
    assert "admin:feishu-settings" in union_read
    records = {
        frozenset(binding.page_keys)
        for binding in PAGE_API_BINDINGS
        if binding.route_path
        == "/api/v1/administration/page-data/{page_key}/{binding_id}/records"
        and binding.method == "GET"
    }
    assert records, "镜像记录路由未登记"
    assert set(PAGES) <= set().union(*records)
