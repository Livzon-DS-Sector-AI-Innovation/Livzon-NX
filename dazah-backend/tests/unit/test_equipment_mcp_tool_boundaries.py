from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.equipment import mcp_tools


def _work_order(status: str = "待处理") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        work_order_no="WO-001",
        order_type="维修",
        status=status,
        priority="high",
        equipment=SimpleNamespace(name="反应釜"),
        fault_description="密封泄漏",
        assignee=SimpleNamespace(name="张三"),
        reporter=SimpleNamespace(name="李四"),
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
        started_at=None,
    )


def _inspection_task(status: str = "待执行") -> SimpleNamespace:
    equipment = SimpleNamespace(is_deleted=False)
    location = SimpleNamespace(equipments=[equipment])
    route = SimpleNamespace(
        id=uuid.uuid4(),
        name="一车间路线",
        locations_rel=[location],
    )
    return SimpleNamespace(
        id=uuid.uuid4(),
        task_no="IT-001",
        plan_type="route",
        status=status,
        route=route,
        route_id=route.id,
        equipment=None,
        equipment_ids=None,
        equipment_id=None,
        equipment_templates=None,
        template_ids=None,
        planned_time=datetime(2026, 7, 1, tzinfo=UTC),
        overall_result=None,
        assignee=SimpleNamespace(name="张三"),
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
    )


def test_equipment_mcp_serializers_cover_relationship_fallbacks() -> None:
    order = mcp_tools._wo_to_dict(_work_order())
    assert order["equipment_name"] == "反应釜"
    assert order["started_at"] == ""

    task = mcp_tools._it_to_dict(_inspection_task())
    assert task["route_name"] == "一车间路线"
    assert task["equipment_count"] == 1

    equipment_task = _inspection_task()
    equipment_task.route = None
    equipment_task.route_id = None
    equipment_task.equipment_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    assert mcp_tools._it_to_dict(equipment_task)["equipment_count"] == 2

    equipment_task.equipment_ids = None
    equipment_task.equipment_id = uuid.uuid4()
    assert mcp_tools._it_to_dict(equipment_task)["equipment_count"] == 1


@pytest.mark.anyio
async def test_resolve_user_uuid_feishu_keyword_and_error_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid.uuid4()
    active_user = SimpleNamespace(id=user_id, is_deleted=False, name="张三")
    db = SimpleNamespace(get=AsyncMock(return_value=active_user))

    assert await mcp_tools.resolve_user(db, str(user_id)) is active_user

    repo = SimpleNamespace(
        get_by_feishu_user_id=AsyncMock(return_value=active_user),
        list_all=AsyncMock(return_value=([], 0)),
    )
    monkeypatch.setattr(mcp_tools, "UserRepository", lambda: repo)
    db.get.return_value = None
    assert await mcp_tools.resolve_user(db, "ou_001") is active_user

    repo.get_by_feishu_user_id.return_value = None
    repo.list_all.return_value = ([active_user], 1)
    assert await mcp_tools.resolve_user(db, "张三") is active_user

    repo.list_all.return_value = ([active_user, active_user], 2)
    with pytest.raises(ValueError, match="多个匹配用户"):
        await mcp_tools.resolve_user(db, "张")

    repo.list_all.return_value = ([], 0)
    with pytest.raises(ValueError, match="未找到用户"):
        await mcp_tools.resolve_user(db, "missing")


@pytest.mark.anyio
async def test_query_and_work_order_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = object()
    user = SimpleNamespace(
        id=uuid.uuid4(),
        name="张三",
        employee_no="E001",
        department="设备部",
        position="工程师",
        email=None,
        mobile=None,
        feishu_user_id="ou_001",
    )
    repo = SimpleNamespace(list_all=AsyncMock(return_value=([user], 1)))
    monkeypatch.setattr(mcp_tools, "get_db", lambda: db)
    monkeypatch.setattr(mcp_tools, "UserRepository", lambda: repo)

    users = await mcp_tools.query_user("张三")
    assert users[0]["employee_no"] == "E001"

    monkeypatch.setattr(
        mcp_tools,
        "resolve_user",
        AsyncMock(return_value=user),
    )
    orders = [_work_order("待处理"), _work_order("已完成")]
    monkeypatch.setattr(
        mcp_tools,
        "get_user_work_orders",
        AsyncMock(return_value=orders),
    )
    pending = await mcp_tools.list_work_orders(str(user.id), status="待处理")
    assert [item["status"] for item in pending] == ["待处理"]

    with pytest.raises(ValueError, match="无效的工单状态"):
        await mcp_tools.list_work_orders(str(user.id), status="invalid")

    order = _work_order()
    monkeypatch.setattr(
        mcp_tools,
        "get_work_order_by_id",
        AsyncMock(return_value=order),
    )
    monkeypatch.setattr(
        mcp_tools,
        "start_work_order",
        AsyncMock(return_value=SimpleNamespace(
            work_order_no="WO-001",
            status="执行中",
        )),
    )
    monkeypatch.setattr(
        mcp_tools,
        "complete_work_order",
        AsyncMock(return_value=SimpleNamespace(
            work_order_no="WO-001",
            status="待验收",
        )),
    )
    started = await mcp_tools.operate_work_order(
        str(order.id),
        "start",
        str(user.id),
    )
    assert started["new_status"] == "执行中"
    completed = await mcp_tools.operate_work_order(
        str(order.id),
        "complete",
        str(user.id),
        repair_detail=" 更换密封件 ",
    )
    assert completed["new_status"] == "待验收"

    with pytest.raises(ValueError, match="repair_detail"):
        await mcp_tools.operate_work_order(
            str(order.id),
            "complete",
            str(user.id),
        )
    with pytest.raises(ValueError, match="无效的操作类型"):
        await mcp_tools.operate_work_order(
            str(order.id),
            "invalid",
            str(user.id),
        )


@pytest.mark.anyio
async def test_submit_inspection_validates_items_and_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = object()
    user = SimpleNamespace(id=uuid.uuid4())
    task = _inspection_task("执行中")
    task_after = _inspection_task("已完成")
    equipment_id = uuid.uuid4()
    monkeypatch.setattr(mcp_tools, "get_db", lambda: db)
    monkeypatch.setattr(
        mcp_tools,
        "resolve_user",
        AsyncMock(return_value=user),
    )
    get_task = AsyncMock(side_effect=[task, task_after])
    monkeypatch.setattr(
        mcp_tools,
        "get_inspection_task_by_id",
        get_task,
    )
    monkeypatch.setattr(
        mcp_tools,
        "_get_template_item_map",
        AsyncMock(return_value={"温度": str(uuid.uuid4())}),
    )
    submit = AsyncMock(return_value=[object(), object()])
    monkeypatch.setattr(mcp_tools, "submit_equipment_check", submit)

    result = await mcp_tools.submit_inspection(
        str(task.id),
        str(equipment_id),
        str(user.id),
        [
            {"item_name": "温度", "result": "正常"},
            {
                "item_name": "振动",
                "result": "异常",
                "remark": "轻微异常",
                "template_item_id": str(uuid.uuid4()),
            },
        ],
    )
    assert result["submitted_count"] == 2
    assert result["all_done"] is True
    assert "巡检任务已完成" in result["message"]
    get_task.side_effect = None
    get_task.return_value = task

    with pytest.raises(ValueError, match="item_name"):
        await mcp_tools.submit_inspection(
            str(task.id),
            str(equipment_id),
            str(user.id),
            [{"result": "正常"}],
        )
    with pytest.raises(ValueError, match="result"):
        await mcp_tools.submit_inspection(
            str(task.id),
            str(equipment_id),
            str(user.id),
            [{"item_name": "温度", "result": "invalid"}],
        )
    with pytest.raises(ValueError, match="必须填写"):
        await mcp_tools.submit_inspection(
            str(task.id),
            str(equipment_id),
            str(user.id),
            [{"item_name": "温度", "result": "异常"}],
        )


@pytest.mark.anyio
async def test_list_and_update_inspection_task_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = object()
    user = SimpleNamespace(id=uuid.uuid4())
    task = _inspection_task("待执行")
    monkeypatch.setattr(mcp_tools, "get_db", lambda: db)
    monkeypatch.setattr(
        mcp_tools,
        "resolve_user",
        AsyncMock(return_value=user),
    )
    monkeypatch.setattr(
        mcp_tools,
        "get_inspection_tasks",
        AsyncMock(return_value=([task], 1)),
    )
    monkeypatch.setattr(
        mcp_tools,
        "get_inspection_task_by_id",
        AsyncMock(return_value=task),
    )
    monkeypatch.setattr(
        mcp_tools,
        "start_inspection_task",
        AsyncMock(
            return_value=SimpleNamespace(task_no="IT-001", status="执行中")
        ),
    )
    monkeypatch.setattr(
        mcp_tools,
        "complete_inspection_task",
        AsyncMock(
            return_value=SimpleNamespace(task_no="IT-001", status="已完成")
        ),
    )
    monkeypatch.setattr(
        mcp_tools,
        "close_inspection_task",
        AsyncMock(
            return_value=SimpleNamespace(task_no="IT-001", status="已关闭")
        ),
    )

    tasks = await mcp_tools.list_inspection_tasks(
        str(user.id),
        status="待执行",
    )
    assert tasks[0]["task_no"] == "IT-001"
    with pytest.raises(ValueError, match="无效的任务状态"):
        await mcp_tools.list_inspection_tasks(
            str(user.id),
            status="invalid",
        )

    started = await mcp_tools.update_inspection_task(
        str(task.id),
        "start",
        str(user.id),
    )
    completed = await mcp_tools.update_inspection_task(
        str(task.id),
        "complete",
        str(user.id),
    )
    closed = await mcp_tools.update_inspection_task(
        str(task.id),
        "close",
        str(user.id),
        remark="任务取消",
    )
    assert started["new_status"] == "执行中"
    assert completed["new_status"] == "已完成"
    assert closed["new_status"] == "已关闭"

    with pytest.raises(ValueError, match="无效的操作类型"):
        await mcp_tools.update_inspection_task(
            str(task.id),
            "invalid",
            str(user.id),
        )
