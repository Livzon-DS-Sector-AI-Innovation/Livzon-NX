"""监护人名单页四处登记守护：lifecycle/菜单种子/路由目录一致。"""

import json
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[3]
PAGE_KEY = "safety:ops-safety:guardian-roster"
ROUTE = "/safety/guardian-roster"


def test_lifecycle_registers_guardian_roster_page():
    data = json.loads(
        (
            BACKEND_ROOT / "app/platform/identity/page_permission_lifecycle.json"
        ).read_text(encoding="utf-8")
    )
    pages = data["pages"]
    assert PAGE_KEY in pages, "监护人名单页未登记 page_permission_lifecycle"
    entry = pages[PAGE_KEY]
    assert entry["route_path"] == ROUTE
    assert entry["module_code"] == "safety"
    assert entry["status"] == "active"
    # 行级删除是破坏性操作，必须保留 destructive 分类
    assert entry["actions"]["delete"]["category"] == "destructive"


def test_menu_seed_includes_guardian_roster():
    from app.platform.identity.menu_seed_data import _LEGACY_SEED_MENUS

    def _walk(nodes):
        for node in nodes:
            yield node
            yield from _walk(node.get("children") or [])

    flat = [n for n in _walk(_LEGACY_SEED_MENUS)]
    matched = [n for n in flat if n.get("key") == "guardian-roster"]
    assert matched, "菜单种子缺监护人名单项"
    assert matched[0].get("path") == ROUTE
    assert matched[0].get("name") == "监护人名单"


def test_route_catalog_contains_guardian_roster():
    data = json.loads(
        (BACKEND_ROOT / "app/platform/identity/page_route_catalog.json").read_text(
            encoding="utf-8"
        )
    )
    text = json.dumps(data, ensure_ascii=False)
    assert ROUTE in text, (
        "页面路由目录缺 /safety/guardian-roster（跑 generate-page-routes.py）"
    )
