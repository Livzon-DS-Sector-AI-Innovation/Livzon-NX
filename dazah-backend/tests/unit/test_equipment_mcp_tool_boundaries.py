from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace as _SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.modules.equipment import mcp_tools

SimpleNamespace: Any = _SimpleNamespace


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





def test_equipment_mcp_serializers_cover_relationship_fallbacks() -> None:
    order = mcp_tools._wo_to_dict(_work_order())
    assert order["equipment_name"] == "反应釜"
    assert order["started_at"] == ""


@pytest.mark.anyio
async def test_resolve_user_uuid_feishu_keyword_and_error_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid.uuid4()
    active_user: Any = SimpleNamespace(id=user_id, is_deleted=False, name="张三")
    db: Any = SimpleNamespace(get=AsyncMock(return_value=active_user))

    assert await mcp_tools.resolve_user(db, str(user_id)) is active_user

    repo: Any = SimpleNamespace(
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
    db: Any = object()
    user: Any = SimpleNamespace(
        id=uuid.uuid4(),
        name="张三",
        employee_no="E001",
        department="设备部",
        position="工程师",
        email=None,
        mobile=None,
        feishu_user_id="ou_001",
    )
    repo: Any = SimpleNamespace(list_all=AsyncMock(return_value=([user], 1)))
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
        AsyncMock(
            return_value=SimpleNamespace(
                work_order_no="WO-001",
                status="执行中",
            )
        ),
    )
    monkeypatch.setattr(
        mcp_tools,
        "complete_work_order",
        AsyncMock(
            return_value=SimpleNamespace(
                work_order_no="WO-001",
                status="待验收",
            )
        ),
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
