"""人员名单只向平台/HR 读者返回联系方式与飞书标识。"""

from __future__ import annotations

import uuid

from app.platform.identity.api import serialize_personnel_item
from app.platform.identity.models import User


def _user() -> User:
    return User(
        id=uuid.uuid4(),
        username="zhangsan",
        name="张三",
        role="user",
        status="active",
        auth_source="local",
        email="zhangsan@example.com",
        mobile="13800000000",
        department="质量部",
        position="QA",
        feishu_open_id="ou_123",
        feishu_user_id="u_123",
    )


def test_contact_fields_are_hidden_from_regular_directory_readers() -> None:
    payload = serialize_personnel_item(_user(), include_contact=False)

    assert payload["name"] == "张三"
    assert payload["department"] == "质量部"
    assert payload["position"] == "QA"
    for field in (
        "email",
        "mobile",
        "feishu_open_id",
        "feishu_user_id",
        "feishu_department_ids",
    ):
        assert payload[field] is None


def test_contact_fields_are_visible_to_platform_readers() -> None:
    payload = serialize_personnel_item(_user(), include_contact=True)

    assert payload["email"] == "zhangsan@example.com"
    assert payload["mobile"] == "13800000000"
    assert payload["feishu_open_id"] == "ou_123"
