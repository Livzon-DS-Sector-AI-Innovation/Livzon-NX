import pytest
from pydantic import ValidationError

from app.platform.identity.schemas import PersonnelItem, UserResponse


def test_personnel_department_ids_accept_string_json_list() -> None:
    item = PersonnelItem(
        id="00000000-0000-0000-0000-000000000001",
        name="测试用户",
        feishu_department_ids='["dept-1", "dept-2"]',
    )

    assert item.feishu_department_ids == ["dept-1", "dept-2"]


def test_personnel_department_ids_reject_non_string_members() -> None:
    with pytest.raises(ValidationError, match="必须是字符串列表"):
        PersonnelItem(
            id="00000000-0000-0000-0000-000000000001",
            name="测试用户",
            feishu_department_ids=["dept-1", 2],
        )


def test_current_user_response_exposes_resolved_rbac_context() -> None:
    user = UserResponse(
        id="00000000-0000-0000-0000-000000000001",
        name="测试用户",
        roles=["quality_manager"],
        permissions=["quality:read", "quality:write"],
    )

    assert user.roles == ["quality_manager"]
    assert user.permissions == ["quality:read", "quality:write"]
