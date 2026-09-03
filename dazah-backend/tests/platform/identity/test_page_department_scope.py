from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.platform.identity.data_scope import page_department_scope


def department(key, name, parent=None, deleted=False):
    return SimpleNamespace(
        feishu_department_id=key,
        name=name,
        parent_feishu_department_id=parent,
        is_deleted=deleted,
        status_is_deleted=False,
    )


def test_page_scope_expands_ids_and_terminates_cycles():
    departments = [department("a", "一部", "b"), department("b", "二部", "a")]
    scope = page_department_scope(departments, ["a"])
    assert scope.department_names == {"一部", "二部"}
    assert not scope.is_all


@pytest.mark.parametrize("deleted", [False, True])
def test_same_name_outside_scope_cannot_widen_access(deleted):
    departments = [
        department("a", "采购部"),
        department("b", "采购部", deleted=deleted),
    ]
    with pytest.raises(HTTPException) as error:
        page_department_scope(departments, ["a"])
    assert error.value.status_code == 403
    assert "歧义" in error.value.detail


def test_missing_and_retired_departments_are_not_authorized():
    scope = page_department_scope(
        [department("a", "旧部门", deleted=True)], ["a", "missing"]
    )
    assert scope.department_names == set()
    assert not scope.allows("旧部门")


def test_same_name_is_safe_only_when_all_matching_ids_are_in_scope():
    scope = page_department_scope(
        [department("a", "采购部"), department("b", "采购部")], ["a", "b"]
    )
    assert scope.allows("采购部")
