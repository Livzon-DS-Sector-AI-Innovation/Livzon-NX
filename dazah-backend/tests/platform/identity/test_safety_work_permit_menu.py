"""作业票与证件页面的菜单种子与权限目录一致性守护。"""

from app.platform.identity.menu_seed_data import SEED_MENUS
from app.platform.identity.page_policy import get_page_definition


def test_safety_work_permit_menu_and_permission_catalog_agree() -> None:
    safety = next(menu for menu in SEED_MENUS if menu["key"] == "safety")
    ops = next(
        item for item in safety["children"] if item.get("key") == "ops-safety"
    )
    keys = {entry.get("key") for entry in ops.get("children", [])}
    assert "work-permits" in keys
    assert "work-certificates" in keys

    permits = get_page_definition("safety:ops-safety:work-permits")
    assert permits is not None
    assert permits.route_path == "/safety/work-permits"
    certificates = get_page_definition("safety:ops-safety:work-certificates")
    assert certificates is not None
    assert certificates.route_path == "/safety/work-certificates"


def test_sign_relay_prefix_registered_as_public() -> None:
    """签名中继网关路径登记在公共前缀（不走登录与模块权限）。"""
    from app.platform.identity import rbac

    assert "/api/v1/safety/sign-relay/" in rbac.PUBLIC_PATH_PREFIXES
