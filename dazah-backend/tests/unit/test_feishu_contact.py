"""Unit tests for Feishu contact mapping, pagination, and caching."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.platform.integrations.feishu import contact


def _raw_response(data: dict, *, success: bool = True):
    return SimpleNamespace(
        success=lambda: success,
        code=0 if success else 1,
        msg="" if success else "failed",
        raw=SimpleNamespace(content=json.dumps({"data": data}).encode()),
        data=None,
    )


def test_department_to_dict_normalizes_identifiers_and_order() -> None:
    item = SimpleNamespace(
        open_department_id="open-d1",
        department_id="raw-d1",
        name="生产部",
        order="12",
        leader_user_id="u1",
        member_count=5,
    )
    assert contact._department_to_dict(item, "parent") == {
        "department_id": "open-d1",
        "raw_department_id": "raw-d1",
        "open_department_id": "open-d1",
        "name": "生产部",
        "parent_department_id": "parent",
        "leader_user_id": "u1",
        "member_count": 5,
        "status_is_deleted": False,
        "order": 12,
    }
    item.order = "invalid"
    assert contact._department_to_dict(item)["order"] == 0


@pytest.mark.asyncio
async def test_department_members_uses_cache(monkeypatch) -> None:
    cached = [{"user_id": "u1", "name": "张三"}]
    monkeypatch.setattr(
        contact,
        "cache_get",
        AsyncMock(return_value=json.dumps(cached)),
    )
    assert await contact.get_department_members("d1") == cached


@pytest.mark.asyncio
async def test_contact_scope_collects_authorized_ids(monkeypatch) -> None:
    data = SimpleNamespace(
        department_ids=["d1"],
        user_ids=["u1"],
        group_ids=["g1"],
        has_more=False,
        page_token="",
    )
    response = SimpleNamespace(
        success=lambda: True,
        code=0,
        msg="",
        data=data,
    )
    client = SimpleNamespace(
        contact=SimpleNamespace(
            v3=SimpleNamespace(
                scope=SimpleNamespace(alist=AsyncMock(return_value=response))
            )
        )
    )
    monkeypatch.setattr(contact, "_get_feishu_client", AsyncMock(return_value=client))
    monkeypatch.setattr(contact, "_get_tenant_token", AsyncMock(return_value="token"))
    assert await contact.get_contact_scope() == {
        "department_ids": ["d1"],
        "user_ids": ["u1"],
        "group_ids": ["g1"],
    }


@pytest.mark.asyncio
async def test_get_all_departments_deduplicates_and_normalizes_root(
    monkeypatch,
) -> None:
    items = [
        SimpleNamespace(
            open_department_id="d1",
            department_id="raw-d1",
            name="生产部",
            order=1,
            leader_user_id="u1",
            member_count=2,
            parent_department_id="root",
        ),
        SimpleNamespace(
            open_department_id="d1",
            department_id="raw-d1",
            name="重复",
            order=2,
            leader_user_id=None,
            member_count=0,
            parent_department_id="root",
        ),
    ]
    data = SimpleNamespace(items=items, has_more=False, page_token="")
    response = SimpleNamespace(
        success=lambda: True,
        code=0,
        msg="",
        data=data,
    )
    department_api = SimpleNamespace(
        achildren=AsyncMock(return_value=response)
    )
    client = SimpleNamespace(
        contact=SimpleNamespace(v3=SimpleNamespace(department=department_api))
    )
    monkeypatch.setattr(contact, "_get_feishu_client", AsyncMock(return_value=client))
    monkeypatch.setattr(contact, "_get_tenant_token", AsyncMock(return_value="token"))

    departments = await contact.get_all_departments(root_department_id="root")
    assert len(departments) == 1
    assert departments[0]["department_id"] == "d1"
    assert departments[0]["parent_department_id"] == ""


@pytest.mark.asyncio
async def test_department_members_fetches_pages_and_caches(monkeypatch) -> None:
    responses = [
        _raw_response(
            {
                "items": [{"user_id": "u1", "name": "张三", "employee_no": "E1"}],
                "has_more": True,
                "page_token": "next",
            }
        ),
        _raw_response(
            {
                "items": [{"user_id": "u2", "name": "李四"}],
                "has_more": False,
            }
        ),
    ]
    user_api = SimpleNamespace(alist=AsyncMock(side_effect=responses))
    client = SimpleNamespace(
        contact=SimpleNamespace(v3=SimpleNamespace(user=user_api))
    )
    monkeypatch.setattr(contact, "cache_get", AsyncMock(return_value=None))
    cache_set = AsyncMock()
    monkeypatch.setattr(contact, "cache_set", cache_set)
    monkeypatch.setattr(contact, "_get_feishu_client", AsyncMock(return_value=client))
    monkeypatch.setattr(contact, "_get_tenant_token", AsyncMock(return_value="token"))

    members = await contact.get_department_members("d1")
    assert [member["user_id"] for member in members] == ["u1", "u2"]
    cache_set.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_all_users_maps_raw_pages(monkeypatch) -> None:
    response = _raw_response(
        {
            "items": [
                {
                    "user_id": "u1",
                    "open_id": "ou1",
                    "name": "张三",
                    "department_ids": ["d1"],
                }
            ],
            "has_more": False,
        }
    )
    client = SimpleNamespace(
        contact=SimpleNamespace(
            v3=SimpleNamespace(user=SimpleNamespace(alist=AsyncMock(return_value=response)))
        )
    )
    monkeypatch.setattr(contact, "_get_feishu_client", AsyncMock(return_value=client))
    monkeypatch.setattr(contact, "_get_tenant_token", AsyncMock(return_value="token"))

    users = await contact.get_all_users()
    assert users == [
        {
            "user_id": "u1",
            "open_id": "ou1",
            "name": "张三",
            "employee_no": "",
            "email": "",
            "mobile": "",
            "job_title": "",
            "department_ids": ["d1"],
        }
    ]


def _user_object():
    position = SimpleNamespace(
        position_code="P1",
        position_name="工程师",
        department_id="d1",
        is_major=True,
    )
    department_path = SimpleNamespace(
        department_id="d1",
        department_name=SimpleNamespace(name="生产部"),
    )
    return SimpleNamespace(
        user_id="u1",
        open_id="ou1",
        name="张三",
        en_name="Zhang San",
        email="z@example.com",
        mobile="13800000000",
        employee_no="E1",
        job_title="工程师",
        department_ids=["d1"],
        positions=[position],
        department_path=[department_path],
        avatar_key="avatar",
        join_time=1,
        is_frozen=None,
    )


@pytest.mark.asyncio
async def test_find_users_by_department_maps_nested_fields(monkeypatch) -> None:
    data = SimpleNamespace(items=[_user_object()], has_more=False, page_token="")
    response = SimpleNamespace(
        success=lambda: True,
        code=0,
        msg="",
        data=data,
    )
    client = SimpleNamespace(
        contact=SimpleNamespace(
            v3=SimpleNamespace(
                user=SimpleNamespace(afind_by_department=AsyncMock(return_value=response))
            )
        )
    )
    monkeypatch.setattr(contact, "_get_feishu_client", AsyncMock(return_value=client))
    monkeypatch.setattr(contact, "_get_tenant_token", AsyncMock(return_value="token"))

    users = await contact.find_users_by_department("d1")
    assert users[0]["positions"][0]["position_name"] == "工程师"
    assert users[0]["department_path"][0]["department_name"] == "生产部"
    assert users[0]["is_frozen"] is False


@pytest.mark.asyncio
async def test_get_user_detail_maps_user_and_handles_api_failure(monkeypatch) -> None:
    response = SimpleNamespace(
        success=lambda: True,
        code=0,
        msg="",
        data=SimpleNamespace(user=_user_object()),
    )
    user_api = SimpleNamespace(aget=AsyncMock(return_value=response))
    client = SimpleNamespace(
        contact=SimpleNamespace(v3=SimpleNamespace(user=user_api))
    )
    monkeypatch.setattr(contact, "_get_feishu_client", AsyncMock(return_value=client))
    monkeypatch.setattr(contact, "_get_tenant_token", AsyncMock(return_value="token"))

    user = await contact.get_user_detail("u1")
    assert user is not None
    assert user["positions"][0]["position_code"] == "P1"
    assert user["department_path"][0]["department_id"] == "d1"

    response.success = lambda: False
    assert await contact.get_user_detail("missing") is None


@pytest.mark.asyncio
async def test_department_detail_and_leader_cache(monkeypatch) -> None:
    detail_response = _raw_response(
        {
            "department": {
                "open_department_id": "d1",
                "name": "生产部",
                "parent_department_id": "root",
                "leader_user_id": "u1",
            }
        }
    )
    department_api = SimpleNamespace(aget=AsyncMock(return_value=detail_response))
    client = SimpleNamespace(
        contact=SimpleNamespace(v3=SimpleNamespace(department=department_api))
    )
    monkeypatch.setattr(contact, "_get_feishu_client", AsyncMock(return_value=client))
    monkeypatch.setattr(contact, "_get_tenant_token", AsyncMock(return_value="token"))
    monkeypatch.setattr(contact, "cache_get", AsyncMock(return_value=None))
    cache_set = AsyncMock()
    monkeypatch.setattr(contact, "cache_set", cache_set)

    detail = await contact.get_department_detail("d1")
    assert detail == {
        "department_id": "d1",
        "department_name": "生产部",
        "parent_department_id": "root",
    }
    assert await contact.get_department_leader("d1") == {"user_id": "u1"}
    cache_set.assert_awaited_once()
    monkeypatch.setattr(
        contact,
        "cache_get",
        AsyncMock(return_value='{"user_id": "cached"}'),
    )
    assert await contact.get_department_leader("d1") == {"user_id": "cached"}


@pytest.mark.asyncio
async def test_membership_check(monkeypatch) -> None:
    monkeypatch.setattr(
        contact,
        "get_department_members",
        AsyncMock(return_value=[{"user_id": "u1"}]),
    )
    assert await contact.is_department_member("u1", "d1")
    assert not await contact.is_department_member("u2", "d1")
