"""网页建单派单联动测试：建单后向车间维修群发接单卡片，发卡失败不影响建单。"""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import app.modules.equipment.api.work_orders as api_wo
from app.modules.equipment.schemas import WorkOrderCreate, WorkOrderResponse


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def first(self):
        return self._rows[0] if self._rows else None


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _Scalars(self._rows)


def _env(monkeypatch, *, workshop_code="201-1", dispatch_return="om_x",
         dispatch_error=None):
    eq_id = uuid.uuid4()
    equipment = SimpleNamespace(
        id=eq_id, name="离心泵A", equipment_no="LB-1", workshop_code=workshop_code
    )
    wo = SimpleNamespace(
        id=uuid.uuid4(),
        work_order_no="WO-20261030-0001",
        equipment_id=eq_id,
        priority="高",
    )
    workshop = SimpleNamespace(code=workshop_code, name="201一车间")
    monkeypatch.setattr(
        api_wo.service, "create_work_order", AsyncMock(return_value=wo)
    )
    db = Mock()
    db.get = AsyncMock(return_value=equipment)
    db.execute = AsyncMock(return_value=_Result([workshop]))
    db.commit = AsyncMock()
    if dispatch_error is not None:
        dispatch = AsyncMock(side_effect=dispatch_error)
    else:
        dispatch = AsyncMock(return_value=dispatch_return)
    monkeypatch.setattr(api_wo, "dispatch_repair_card", dispatch)
    resp_obj = WorkOrderResponse.model_construct(
        id=wo.id,
        work_order_no=wo.work_order_no,
        equipment_id=eq_id,
        order_type="故障维修",
        priority="高",
        status="待处理",
    )
    monkeypatch.setattr(api_wo, "_to_response", Mock(return_value=resp_obj))
    user = SimpleNamespace(id=uuid.uuid4(), name="秦佳豪")
    return wo, equipment, db, dispatch, user


@pytest.mark.asyncio
async def test_web_create_dispatches_to_workshop_group(monkeypatch):
    wo, equipment, db, dispatch, user = _env(monkeypatch)
    data = WorkOrderCreate(equipment_id=equipment.id, fault_description="泄漏")

    response = await api_wo.create_work_order(data=data, db=db, current_user=user)

    dispatch.assert_awaited_once()
    kwargs = dispatch.await_args.kwargs
    assert kwargs["workshop_code"] == "201-1"
    assert kwargs["workshop_name"] == "201一车间"
    assert "离心泵A" in kwargs["equipment_label"]
    assert kwargs["reporter_name"] == "秦佳豪"
    assert kwargs["fault"] == "泄漏"
    # 先落库再发卡
    db.commit.assert_awaited()
    payload = json.loads(response.body)["data"]
    assert payload["dispatched"] is True


@pytest.mark.asyncio
async def test_web_create_without_description_uses_default_fault(monkeypatch):
    wo, equipment, db, dispatch, user = _env(monkeypatch)
    data = WorkOrderCreate(equipment_id=equipment.id)

    await api_wo.create_work_order(data=data, db=db, current_user=user)

    assert dispatch.await_args.kwargs["fault"] == "平台报修"


@pytest.mark.asyncio
async def test_web_create_without_workshop_falls_back(monkeypatch):
    wo, equipment, db, dispatch, user = _env(monkeypatch, workshop_code="")

    await api_wo.create_work_order(
        data=WorkOrderCreate(equipment_id=equipment.id), db=db, current_user=user
    )

    kwargs = dispatch.await_args.kwargs
    assert kwargs["workshop_code"] == ""
    assert kwargs["workshop_name"] == "未分配车间"


@pytest.mark.asyncio
async def test_web_create_survives_dispatch_failure(monkeypatch):
    wo, equipment, db, dispatch, user = _env(
        monkeypatch, dispatch_error=RuntimeError("feishu down")
    )

    response = await api_wo.create_work_order(
        data=WorkOrderCreate(equipment_id=equipment.id), db=db, current_user=user
    )

    payload = json.loads(response.body)["data"]
    assert payload["work_order_no"] == wo.work_order_no
    assert payload["dispatched"] is False


@pytest.mark.asyncio
async def test_web_create_no_group_marks_not_dispatched(monkeypatch):
    wo, equipment, db, dispatch, user = _env(monkeypatch, dispatch_return=None)

    response = await api_wo.create_work_order(
        data=WorkOrderCreate(equipment_id=equipment.id), db=db, current_user=user
    )

    payload = json.loads(response.body)["data"]
    assert payload["dispatched"] is False
