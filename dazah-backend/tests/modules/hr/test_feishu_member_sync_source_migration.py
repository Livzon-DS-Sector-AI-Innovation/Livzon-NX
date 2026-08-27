"""飞书联系人同步测试：翻页失败抛异常、全量部门 BFS、失败保留旧数据"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.hr.feishu.contact import FeishuContact, FeishuContactError


@pytest.mark.asyncio
async def test_get_department_users_raises_when_page_fails():
    """翻页中途失败必须抛异常，而不是静默返回半截用户列表"""
    contact = FeishuContact()
    page1 = {
        "code": 0,
        "data": {
            "items": [{"open_id": "ou_1", "name": "张三"}],
            "has_more": True,
            "page_token": "t2",
        },
    }
    page2 = {"code": 99991663, "msg": "rate limit"}

    with patch.object(
        contact, "_make_request", new_callable=AsyncMock, side_effect=[page1, page2]
    ):
        with pytest.raises(FeishuContactError):
            await contact.get_department_users("od_x")


@pytest.mark.asyncio
async def test_get_department_children_raises_when_page_fails():
    """子部门翻页失败必须抛异常，避免 BFS 静默漏掉部门"""
    contact = FeishuContact()
    error_resp = {"code": 99991663, "msg": "rate limit"}

    with patch.object(
        contact, "_make_request", new_callable=AsyncMock, return_value=error_resp
    ):
        with pytest.raises(FeishuContactError):
            await contact.get_department_children("od_x")


@pytest.mark.asyncio
async def test_get_all_departments_bfs():
    """BFS 从根部门 0 遍历全部部门"""
    contact = FeishuContact()

    async def fake_children(dept_id: str):
        return {
            "0": [
                {"open_department_id": "od_a", "name": "部门A"},
                {"open_department_id": "od_b", "name": "部门B"},
            ],
            "od_a": [{"open_department_id": "od_a1", "name": "部门A1"}],
            "od_b": [],
            "od_a1": [],
        }[dept_id]

    with patch.object(contact, "get_department_children", side_effect=fake_children):
        depts = await contact.get_all_departments()

    assert [d["open_department_id"] for d in depts] == ["0", "od_a", "od_b", "od_a1"]
    assert depts[0]["name"] == "根部门"


def _mock_db() -> MagicMock:
    """构造带完整 execute 返回链的 db mock。

    AsyncMock 被 await 后返回 AsyncMock 实例本身，其属性（scalars/scalar_one_or_none）
    也是 AsyncMock，调用返回 coroutine 会导致 AttributeError。因此需为
    execute 的返回值显式设置普通 MagicMock 链：scalars().all() / scalar_one_or_none()。
    """
    db = MagicMock()
    db.execute = AsyncMock()

    # select(HrFeishuMember) 等查询结果的 scalars().all() 返回空列表
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    db.add = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    return db


def _fake_user(open_id: str, name: str) -> dict:
    return {
        "open_id": open_id,
        "name": name,
        "mobile": "13800000000",
        "employee_no": "10001",
        "job_title": "操作工",
        "gender": 1,
        "avatar": {"avatar_240": "https://example.com/a.png"},
        "status": {"is_activated": True, "is_frozen": False, "is_resigned": False},
    }


@pytest.mark.asyncio
async def test_sync_keeps_existing_data_when_dept_fails():
    """某部门拉取失败时不重写全表，抛异常让任务标记失败"""
    from app.modules.hr import contract_settings_api as api

    db = _mock_db()

    departments = [
        {"open_department_id": "0", "name": "根部门"},
        {"open_department_id": "od_bad", "name": "失败部门"},
    ]

    async def fake_fetch(contact, dept_id):
        if dept_id == "od_bad":
            raise FeishuContactError("boom")
        return [_fake_user("ou_1", "张三")]

    with (
        patch.object(
            api.FeishuContact,
            "get_all_departments",
            new_callable=AsyncMock,
            return_value=departments,
        ),
        patch.object(api, "_fetch_dept_users_with_retry", side_effect=fake_fetch),
    ):
        with pytest.raises(Exception, match="失败部门"):
            await api._sync_feishu_members(db)

    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_sync_rewrites_when_all_depts_succeed():
    """全部部门成功时清空旧数据并写入新数据"""
    from app.modules.hr import contract_settings_api as api

    db = _mock_db()

    departments = [
        {"open_department_id": "0", "name": "根部门"},
        {"open_department_id": "od_a", "name": "部门A"},
    ]

    async def fake_fetch(contact, dept_id):
        if dept_id == "0":
            return [_fake_user("ou_root", "根用户")]
        return [_fake_user("ou_a", "部门A用户"), _fake_user("ou_a", "部门A用户")]

    with (
        patch.object(
            api.FeishuContact,
            "get_all_departments",
            new_callable=AsyncMock,
            return_value=departments,
        ),
        patch.object(api, "_fetch_dept_users_with_retry", side_effect=fake_fetch),
    ):
        await api._sync_feishu_members(db)

    db.execute.assert_called()  # select(HrFeishuMember) + delete(HrFeishuMember)
    assert db.add.call_count == 2  # open_id+部门 去重后 2 条
    db.commit.assert_awaited()
