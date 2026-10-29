"""删除工单测试：开放状态删除必须恢复设备状态，已结束工单删除不动设备。"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import app.modules.equipment.service.work_order as wo_svc


def _wo(status="待处理", original="在用"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        work_order_no="WO-D1",
        status=status,
        original_equipment_status=original,
        equipment_id=uuid.uuid4(),
        is_deleted=False,
    )


def _equipment(status="维修中"):
    return SimpleNamespace(id=uuid.uuid4(), status=status)


def _patch(monkeypatch, wo, equipment):
    monkeypatch.setattr(
        wo_svc.repo, "get_work_order_by_id", AsyncMock(return_value=wo)
    )
    monkeypatch.setattr(
        wo_svc.repo, "get_equipment_by_id", AsyncMock(return_value=equipment)
    )
    db = Mock()
    db.flush = AsyncMock()
    return db


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["待处理", "执行中", "待验收"])
async def test_delete_open_order_restores_equipment(monkeypatch, status):
    wo = _wo(status=status, original="备用")
    equipment = _equipment(status="维修中")
    db = _patch(monkeypatch, wo, equipment)

    result = await wo_svc.delete_work_order(db, wo.id)

    assert result.is_deleted is True
    assert equipment.status == "备用"  # 恢复到建单前原始状态
    db.flush.assert_awaited()


@pytest.mark.asyncio
async def test_delete_open_order_without_original_falls_back_to_in_use(monkeypatch):
    wo = _wo(original=None)
    equipment = _equipment()
    db = _patch(monkeypatch, wo, equipment)

    await wo_svc.delete_work_order(db, wo.id)
    assert equipment.status == "在用"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["已关闭", "已完成"])
async def test_delete_finished_order_keeps_equipment_untouched(monkeypatch, status):
    wo = _wo(status=status)
    equipment = _equipment(status="在用")
    db = _patch(monkeypatch, wo, equipment)

    await wo_svc.delete_work_order(db, wo.id)

    assert result_ok(wo) and equipment.status == "在用"


def result_ok(wo) -> bool:
    return wo.is_deleted is True
