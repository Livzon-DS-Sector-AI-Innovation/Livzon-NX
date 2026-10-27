"""设备车间管理菜单与页面权限目录的一致性。"""

from app.platform.identity.menu_seed_data import SEED_MENUS
from app.platform.identity.page_policy import get_page_definition


def test_equipment_workshop_admin_menu_and_permission_catalog_agree() -> None:
    equipment = next(menu for menu in SEED_MENUS if menu["key"] == "equipment")
    admin = next(
        item
        for item in equipment["children"]
        if item["path"] == "/equipment/workshop-admin"
    )
    assert admin["name"] == "车间管理"
    page = get_page_definition("equipment:workshop-admin")
    assert page is not None
    assert page.page_name == "车间管理"
    assert page.route_path == "/equipment/workshop-admin"


def test_equipment_children_keep_workbench_module_tabs() -> None:
    """统一工作台的五个功能模块标签保持不变，车间管理独立于标签之外。"""
    equipment = next(menu for menu in SEED_MENUS if menu["key"] == "equipment")
    paths = [item["path"] for item in equipment["children"]]
    for module in (
        "/equipment/assets",
        "/equipment/maintenance",
        "/equipment/inspection",
        "/equipment/spare-parts",
        "/equipment/personnel",
    ):
        assert module in paths
