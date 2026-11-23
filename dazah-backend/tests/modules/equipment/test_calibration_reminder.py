"""校准到期提醒测试：筛选窗口、按天防重、负责人单聊寻址与群兜底。"""

import uuid
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import app.modules.equipment.service.calibration_reminder as cr
from app.modules.equipment.service.calibration_reminder import (
    remind_due_calibration_plans,
)


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _Scalars(self._rows)


def _plan(*, next_date=None, responsible=True):
    return SimpleNamespace(
        id=uuid.uuid4(),
        status="启用",
        is_deleted=False,
        next_calibration_date=next_date or date.today() + timedelta(days=3),
        calibration_type="内部校准",
        responsible_person_id=uuid.uuid4() if responsible else None,
        equipment=SimpleNamespace(
            name="离心泵A", equipment_no="LB-1", workshop_code="201-1"
        ),
        equipment_id=uuid.uuid4(),
    )


def _feishu_env(monkeypatch, plan, user, *, redis_new=True):
    monkeypatch.setattr(
        cr.redis_client,
        "set",
        AsyncMock(return_value=redis_new),
    )
    dm = AsyncMock(return_value=user is not None)
    group_card = AsyncMock()
    chat_id = AsyncMock(return_value="oc_group")
    monkeypatch.setattr(
        "app.modules.equipment.feishu.notification.send_user_card", dm
    )
    monkeypatch.setattr(
        "app.modules.equipment.feishu.repair_card.send_card_to_chat", group_card
    )
    monkeypatch.setattr(
        "app.modules.equipment.service.work_order_feishu.resolve_repair_chat_id",
        chat_id,
    )
    db = Mock()
    db.execute = AsyncMock(
        side_effect=[_Result([plan]), _Result([user] if user else [])]
    )
    return db, dm, group_card


@pytest.mark.asyncio
async def test_remind_sends_dm_to_responsible_by_union_id(monkeypatch):
    plan = _plan()
    user = SimpleNamespace(
        id=plan.responsible_person_id, feishu_union_id="on_u1"
    )
    db, dm, group_card = _feishu_env(monkeypatch, plan, user)

    reminded, skipped = await remind_due_calibration_plans(db)

    assert (reminded, skipped) == (1, 0)
    dm.assert_awaited_once()
    assert dm.await_args.kwargs["receive_id_type"] == "union_id"
    assert dm.await_args.kwargs["open_id"] == "on_u1"
    # 单聊成功则不再发群兜底
    group_card.assert_not_awaited()


@pytest.mark.asyncio
async def test_remind_falls_back_to_group_without_binding(monkeypatch):
    plan = _plan(responsible=False)
    db, dm, group_card = _feishu_env(monkeypatch, plan, None)

    reminded, skipped = await remind_due_calibration_plans(db)

    assert (reminded, skipped) == (1, 0)
    dm.assert_not_awaited()
    group_card.assert_awaited_once()
    card = group_card.await_args.args[1]
    title = card["header"]["title"]["content"]
    assert "3 天后到期" in title


@pytest.mark.asyncio
async def test_remind_skips_when_already_reminded_today(monkeypatch):
    plan = _plan()
    db, dm, group_card = _feishu_env(
        monkeypatch, plan, None, redis_new=False
    )

    reminded, skipped = await remind_due_calibration_plans(db)

    assert (reminded, skipped) == (0, 1)
    dm.assert_not_awaited()
    group_card.assert_not_awaited()


@pytest.mark.asyncio
async def test_remind_overdue_plan_uses_red_header(monkeypatch):
    plan = _plan(next_date=date.today() - timedelta(days=2), responsible=False)
    db, dm, group_card = _feishu_env(monkeypatch, plan, None)

    await remind_due_calibration_plans(db)

    card = group_card.await_args.args[1]
    assert card["header"]["template"] == "red"
    assert "已逾期 2 天" in card["header"]["title"]["content"]
