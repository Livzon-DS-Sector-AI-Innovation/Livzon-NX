"""计划维护派单联动与备件库存预警测试：自动生成工单进维修群，领料跌破安全线提醒。"""

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import app.modules.equipment.service.maintenance_plan as mp
import app.modules.equipment.service.work_order as wo_svc
import app.modules.equipment.service.spare_part as sp_service
from app.modules.equipment.service.maintenance_plan import (
    _dispatch_generated_orders,
    generate_due_work_orders,
)
from app.modules.equipment.service.work_order import _notify_low_stock


# ── 计划维护生成后派单 ──────────────────────────────────────────────

def _due_plan_env(monkeypatch):
    plan = SimpleNamespace(
        id=uuid.uuid4(),
        plan_name="季度保养",
        equipment_id=uuid.uuid4(),
        responsible_person_id=None,
        next_maintenance_date=date.today(),
        last_generated_date=None,
    )
    equipment = SimpleNamespace(
        id=plan.equipment_id,
        name="离心泵A",
        equipment_no="LB-1",
        status="在用",
        workshop_code="201-1",
    )
    monkeypatch.setattr(
        mp.repo, "get_maintenance_plans_due", AsyncMock(return_value=[plan])
    )
    monkeypatch.setattr(
        mp.repo, "get_equipment_by_id", AsyncMock(return_value=equipment)
    )
    monkeypatch.setattr(
        mp.repo, "exists_unclosed_work_order_for_plan", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        mp.repo, "get_max_work_order_no", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(mp.repo, "create_work_order", AsyncMock())
    db = Mock()
    db.flush = AsyncMock()
    return plan, equipment, db


@pytest.mark.asyncio
async def test_generated_plan_order_is_dispatched(monkeypatch):
    plan, equipment, db = _due_plan_env(monkeypatch)
    captured: list[dict] = []

    async def fake_dispatch(payloads):
        captured.extend(payloads)

    monkeypatch.setattr(mp, "_dispatch_generated_orders", fake_dispatch)

    created, skipped = await generate_due_work_orders(db)

    assert (created, skipped) == (1, 0)
    assert len(captured) == 1
    payload = captured[0]
    assert payload["work_order_no"].startswith("WO-")
    assert "离心泵A" in payload["equipment_label"]
    assert payload["workshop_code"] == "201-1"
    assert payload["plan_name"] == "季度保养"


@pytest.mark.asyncio
async def test_dispatch_generated_orders_sends_plan_card(monkeypatch):
    workshop = SimpleNamespace(code="201-1", name="201一车间")
    db = Mock()
    db.execute = AsyncMock(return_value=SimpleNamespace(
        scalars=lambda self=None: SimpleNamespace(first=lambda: workshop)
    ))

    class _Ctx:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr(mp, "async_session_factory", lambda: _Ctx())
    dispatch = AsyncMock(return_value="om_1")
    monkeypatch.setattr(
        "app.modules.equipment.service.work_order_feishu.dispatch_repair_card",
        dispatch,
    )

    await _dispatch_generated_orders([
        {
            "work_order_no": "WO-20261030-0001",
            "equipment_label": "离心泵A（LB-1）",
            "workshop_code": "201-1",
            "plan_name": "季度保养",
        }
    ])

    kwargs = dispatch.await_args.kwargs
    assert kwargs["workshop_name"] == "201一车间"
    assert kwargs["fault"] == "[计划维护] 季度保养"
    assert kwargs["reporter_name"] == "维护计划自动生成"
    assert kwargs["priority"] == "中"


@pytest.mark.asyncio
async def test_dispatch_failure_does_not_raise(monkeypatch):
    db = Mock()
    db.execute = AsyncMock(return_value=SimpleNamespace(
        scalars=lambda self=None: SimpleNamespace(first=lambda: None)
    ))

    class _Ctx:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr(mp, "async_session_factory", lambda: _Ctx())
    monkeypatch.setattr(
        "app.modules.equipment.service.work_order_feishu.dispatch_repair_card",
        AsyncMock(side_effect=RuntimeError("feishu down")),
    )

    # 不抛异常即通过
    await _dispatch_generated_orders([
        {
            "work_order_no": "WO-1",
            "equipment_label": "x",
            "workshop_code": "",
            "plan_name": "p",
        }
    ])


# ── 领料库存安全线提醒 ─────────────────────────────────────────────

def _stock_env(monkeypatch, *, current, safety):
    spare = SimpleNamespace(id=uuid.uuid4(), name="机械密封")
    stock = SimpleNamespace(current_qty=current, safety_qty=safety)
    monkeypatch.setattr(
        sp_service, "get_spare_part_by_id", AsyncMock(return_value=spare)
    )
    monkeypatch.setattr(
        sp_service, "get_stock_by_spare_part_id", AsyncMock(return_value=stock)
    )
    monkeypatch.setattr(
        "app.modules.equipment.service.work_order_feishu.resolve_repair_chat_id",
        AsyncMock(return_value="oc_group"),
    )
    group_card = AsyncMock()
    monkeypatch.setattr(
        "app.modules.equipment.feishu.repair_card.send_card_to_chat", group_card
    )
    return spare, group_card


@pytest.mark.asyncio
async def test_low_stock_after_consume_notifies_group(monkeypatch):
    spare, group_card = _stock_env(monkeypatch, current=2, safety=5)
    db = Mock()

    await _notify_low_stock(db, [{"spare_part_id": spare.id, "quantity": 3}])

    group_card.assert_awaited_once()
    content = group_card.await_args.args[1]["elements"][0]["text"]["content"]
    assert "机械密封" in content
    assert "安全线" in content


@pytest.mark.asyncio
async def test_stock_above_safety_line_no_notify(monkeypatch):
    spare, group_card = _stock_env(monkeypatch, current=10, safety=5)
    db = Mock()

    await _notify_low_stock(db, [{"spare_part_id": spare.id, "quantity": 1}])

    group_card.assert_not_awaited()


@pytest.mark.asyncio
async def test_notify_failure_does_not_propagate(monkeypatch):
    spare, group_card = _stock_env(monkeypatch, current=1, safety=5)
    group_card.side_effect = RuntimeError("feishu down")
    db = Mock()

    # 不抛异常即通过：库存提醒失败不影响领料主流程
    await _notify_low_stock(db, [{"spare_part_id": spare.id, "quantity": 9}])
