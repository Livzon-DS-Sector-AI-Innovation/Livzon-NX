"""重复报修解锁与待验收超时自动结单测试。"""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import app.modules.equipment.scheduler as sched
import app.modules.equipment.service.work_order as wo_svc
from app.core.exceptions import AppException
from app.modules.equipment.schemas import WorkOrderCreate

EQ_ID = uuid.uuid4()


class _Scalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return list(self._items)

    def first(self):
        return self._items[0] if self._items else None


class _Result:
    def __init__(self, items, scalar=None):
        self._scalars = _Scalars(items)
        self._scalar = scalar

    def scalars(self):
        return self._scalars

    def scalar(self):
        return self._scalar


def _hold(status="待验收", no="WO-P9"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        work_order_no=no,
        status=status,
        equipment_id=EQ_ID,
        is_deleted=False,
    )


def _create_data(fault="又坏了"):
    return WorkOrderCreate(
        equipment_id=EQ_ID,
        order_type="故障维修",
        priority="高",
        fault_description=fault,
    )


def _patch_create(monkeypatch, equipment_status, execute_results):
    equipment = SimpleNamespace(id=EQ_ID, status=equipment_status)
    monkeypatch.setattr(
        wo_svc.repo, "get_equipment_by_id", AsyncMock(return_value=equipment)
    )
    db = Mock()
    db.execute = AsyncMock(side_effect=execute_results)
    monkeypatch.setattr(wo_svc, "generate_work_order_no", AsyncMock(
        return_value="WO-N1"
    ))
    monkeypatch.setattr(wo_svc, "_update_equipment_status", AsyncMock())
    monkeypatch.setattr(
        wo_svc,
        "auto_finish_pending_verify",
        AsyncMock(),
    )
    saved = SimpleNamespace(
        id=uuid.uuid4(), work_order_no="WO-N1", fault_description=""
    )
    monkeypatch.setattr(
        wo_svc.repo, "create_work_order", AsyncMock(return_value=saved)
    )
    monkeypatch.setattr(
        wo_svc.repo, "get_work_order_by_id", AsyncMock(return_value=saved)
    )
    return db, saved


@pytest.mark.asyncio
async def test_repeat_repair_auto_unlocks_pending_verify_order(monkeypatch):
    """设备「维修中」且旧单待验收 → 自动结旧单并建新单，标注第 N 次报修。"""
    hold = _hold()
    db, saved = _patch_create(
        monkeypatch,
        "维修中",
        [_Result([hold]), _Result([], scalar=1)],
    )

    result = await wo_svc.create_work_order(db, _create_data(), uuid.uuid4())

    wo_svc.auto_finish_pending_verify.assert_awaited_once()
    args = wo_svc.auto_finish_pending_verify.await_args
    assert args.args[1] is hold
    assert "重复报修" in args.kwargs["reason"]
    wo_data = wo_svc.repo.create_work_order.await_args.args[1]
    assert wo_data["fault_description"].startswith(
        "[第2次报修·前单WO-P9] 又坏了"
    )
    assert result is saved


@pytest.mark.asyncio
async def test_repeat_repair_blocked_while_still_in_progress(monkeypatch):
    """旧单还在执行中（未提交完成）→ 维持拒绝，并提示占用工单号。"""
    hold = _hold(status="执行中", no="WO-BUSY")
    db, _saved = _patch_create(
        monkeypatch, "维修中", [_Result([hold])]
    )

    with pytest.raises(AppException) as exc:
        await wo_svc.create_work_order(db, _create_data(), uuid.uuid4())

    assert "WO-BUSY" in str(exc.value)
    assert "尚未完成" in str(exc.value)
    wo_svc.auto_finish_pending_verify.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_rejects_non_repairing_status_without_lookup(monkeypatch):
    """非「维修中」的不可用状态（如停用）→ 原文案拒绝，不查占用单。"""
    db, _saved = _patch_create(monkeypatch, "停用", [])

    with pytest.raises(AppException) as exc:
        await wo_svc.create_work_order(db, _create_data(), uuid.uuid4())

    assert "停用" in str(exc.value)
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_finish_pending_verify_verifies_then_closes(monkeypatch):
    """自动结单 = 系统管理员验收合格 + 关闭（两步走，保留轨迹）。"""
    monkeypatch.setattr(
        "app.platform.identity.service.get_or_create_system_admin",
        AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
    )
    verify = AsyncMock()
    close = AsyncMock()
    monkeypatch.setattr(wo_svc, "verify_work_order", verify)
    monkeypatch.setattr(wo_svc, "close_work_order", close)
    hold = _hold()
    db = Mock()

    await wo_svc.auto_finish_pending_verify(db, hold, reason="测试自动验收")

    verify.assert_awaited_once()
    v_args = verify.await_args
    assert v_args.args[0] is db
    assert v_args.args[2] is not None  # verifier_id = 系统管理员
    assert v_args.args[3].result == "合格"
    assert v_args.args[3].remark == "测试自动验收"
    close.assert_awaited_once_with(db, hold.id)


@pytest.mark.asyncio
async def test_stale_pending_verify_auto_finished_after_24h(monkeypatch):
    """完成超 24 小时的待验收工单自动结单；未超时/无完成时间的跳过。"""
    now = datetime.now(UTC)
    stale = SimpleNamespace(
        work_order_no="WO-S1",
        completed_at=now - timedelta(hours=25),
    )
    fresh = SimpleNamespace(
        work_order_no="WO-S2",
        completed_at=now - timedelta(hours=2),
    )
    no_completed = SimpleNamespace(work_order_no="WO-S3", completed_at=None)
    db = Mock()
    db.execute = AsyncMock(return_value=_Result([stale, fresh, no_completed]))
    finished = AsyncMock()
    monkeypatch.setattr(
        "app.modules.equipment.service.work_order.auto_finish_pending_verify",
        finished,
    )

    await sched._auto_finish_stale_pending_verify(db, now)

    finished.assert_awaited_once()
    assert finished.await_args.args[1] is stale


@pytest.mark.asyncio
async def test_verify_reject_notifies_assignee(monkeypatch):
    """验收不合格打回 → 飞书通知维修人返修（带验收备注）。"""
    import asyncio

    notified: list[dict] = []

    async def _fake_notify(**kw):
        notified.append(kw)

    monkeypatch.setattr(wo_svc, "_notify_rework", _fake_notify)

    wo = SimpleNamespace(
        id=uuid.uuid4(),
        work_order_no="WO-RJ1",
        status="待验收",
        order_type="故障维修",
        verification_result=None,
        verified_by=None,
        verified_at=None,
        verification_remark=None,
        started_at=None,
        completed_at=None,
        actual_duration=10,
        assignee=SimpleNamespace(name="维修工", feishu_union_id="fu_1"),
        equipment=SimpleNamespace(name="102A"),
    )
    monkeypatch.setattr(
        wo_svc.repo, "get_work_order_by_id", AsyncMock(return_value=wo)
    )
    db = Mock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    from app.modules.equipment.schemas import WorkOrderVerify

    result = await wo_svc.verify_work_order(
        db,
        wo.id,
        uuid.uuid4(),
        WorkOrderVerify(result="不合格", remark="没修好，还是漏"),
    )
    await asyncio.sleep(0)  # 让 ensure_future 的通知任务落地

    assert result.status == "执行中"
    assert notified and notified[0]["feishu_union_id"] == "fu_1"
    assert notified[0]["remark"] == "没修好，还是漏"
    assert notified[0]["equipment_name"] == "102A"


@pytest.mark.asyncio
async def test_notify_rework_sends_card_with_complete_button(monkeypatch):
    """直接执行 _notify_rework 真实函数体：union_id 寻址 + 卡片带返修完成按钮。"""
    sent: list[dict] = []

    async def _fake_send(**kw):
        sent.append(kw)
        return True

    monkeypatch.setattr(
        "app.modules.equipment.feishu.notification.send_user_card", _fake_send
    )

    await wo_svc._notify_rework(
        feishu_union_id="on_1",
        work_order_no="WO-N1",
        equipment_name="离心泵A",
        remark="没修好，还是漏",
    )

    assert len(sent) == 1
    card = sent[0]
    assert card["open_id"] == "on_1"
    assert card["receive_id_type"] == "union_id"
    assert "WO-N1" in card["title"] and "不合格" in card["title"]
    assert "没修好，还是漏" in card["content"]
    button = card["elements"][0]["actions"][0]
    assert button["value"] == {"act": "complete", "oid": "WO-N1"}


@pytest.mark.asyncio
async def test_notify_rework_send_failure_only_logs(monkeypatch):
    """发送失败仅记日志不抛异常（非关键路径）。"""
    async def _fake_send(**kw):
        return False

    monkeypatch.setattr(
        "app.modules.equipment.feishu.notification.send_user_card", _fake_send
    )
    await wo_svc._notify_rework(  # 不应抛异常
        feishu_union_id="on_1",
        work_order_no="WO-N2",
        equipment_name="设备",
        remark="",
    )

