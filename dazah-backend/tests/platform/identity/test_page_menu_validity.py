from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.platform.identity.page_permission_repository import (
    active_menu_page_catalog,
    active_menu_page_keys,
)
from app.platform.identity.page_policy import _walk_pages


def menu_pair():
    parent = SimpleNamespace(
        id=uuid4(),
        key="hr",
        name="人事管理",
        type="directory",
        parent_id=None,
        route_path="/hr",
        status="active",
        is_deleted=False,
    )
    child = SimpleNamespace(
        id=uuid4(),
        key="hr:employee-management:profile",
        name="员工管理",
        type="menu",
        parent_id=parent.id,
        route_path="/hr/profile",
        status="active",
        is_deleted=False,
    )
    return parent, child


def test_only_live_routable_leaf_menu_can_authorize():
    parent, child = menu_pair()
    assert active_menu_page_keys([parent, child]) == {child.key}
    child.route_path = "/hr/different-page"
    assert active_menu_page_keys([parent, child]) == set()


def test_button_children_do_not_turn_a_menu_page_into_a_directory():
    parent, child = menu_pair()
    button = SimpleNamespace(
        id=uuid4(),
        key="hr:employee-management:profile:edit",
        type="button",
        parent_id=child.id,
        route_path=None,
        status="active",
        is_deleted=False,
    )
    assert active_menu_page_keys([parent, child, button]) == {child.key}


def test_active_menu_catalog_keeps_unregistered_leaf_for_publish_validation():
    parent, child = menu_pair()
    child.key = None
    child.name = "新增员工页面"
    child.route_path = "/hr/new-employee-page"

    catalog = active_menu_page_catalog([parent, child])

    actual = [
        (item.key, item.name, item.route_path, item.root_key) for item in catalog
    ]
    assert actual == [
        (None, "新增员工页面", "/hr/new-employee-page", "hr")
    ]
    assert active_menu_page_keys([parent, child]) == set()


@pytest.mark.parametrize("target", ["parent", "child"])
@pytest.mark.parametrize("field,value", [("status", "disabled"), ("is_deleted", True)])
def test_disabled_or_deleted_page_or_ancestor_revokes_access(target, field, value):
    parent, child = menu_pair()
    setattr(parent if target == "parent" else child, field, value)
    assert active_menu_page_keys([parent, child]) == set()


def test_orphan_and_cyclic_menu_fail_closed():
    parent, child = menu_pair()
    assert active_menu_page_keys([child]) == set()
    parent.parent_id = child.id
    assert active_menu_page_keys([parent, child]) == set()


def test_static_disabled_directory_does_not_authorize_children():
    assert (
        _walk_pages(
            [
                {
                    "key": "hr",
                    "name": "人事管理",
                    "disabled": True,
                    "children": [
                        {
                            "key": "employee-management",
                            "name": "员工管理",
                            "path": "/hr/employee-management",
                        }
                    ],
                }
            ]
        )
        == []
    )
