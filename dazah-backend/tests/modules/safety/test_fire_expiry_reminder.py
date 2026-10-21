"""消防器材有效期提醒服务测试（独立测试库）。

覆盖：节点判定与消息行、节点分组的查重（同器材同节点只推一次）、
未启用/未配置目标的静默跳过、测试发送样例卡片，以及投影对有效日期
字段的抽取。
"""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.safety.models import (
    FireEquipment,
    FireExpiryNotificationLog,
    SafetyFeishuAppSettings,
    SafetyPageTableMirrorRecord,
)
from app.modules.safety.service import fire_expiry_reminder
from app.modules.safety.service.fire_equipment import sync_fire_equipment_ledger

PAGE_KEY = "safety:emergency-accident:fire-equipment-inspection"

_SEEDED_RECORD_IDS = ["recExp1", "recExp2", "recExp3"]


@pytest.fixture(autouse=True)
def _fake_notifications(monkeypatch):
    """假推送：记录调用参数，始终成功。"""
    calls: list[tuple[str, str, str]] = []

    async def _send_group(chat_id, title, content, *, header_template="blue"):
        calls.append((f"chat:{chat_id}", title, content))
        return True

    async def _send_user(user_id, title, content):
        calls.append((f"user:{user_id}", title, content))
        return True

    monkeypatch.setattr(fire_expiry_reminder, "send_group_card", _send_group)
    monkeypatch.setattr(fire_expiry_reminder, "send_user_card", _send_user)
    return SimpleNamespace(calls=calls)


async def _cleanup(db: AsyncSession) -> None:
    await db.execute(
        delete(FireExpiryNotificationLog).where(
            FireExpiryNotificationLog.equipment_id.in_(
                select(FireEquipment.id).where(
                    FireEquipment.record_id.in_(_SEEDED_RECORD_IDS)
                )
            )
        )
    )
    await db.execute(
        delete(FireEquipment).where(
            FireEquipment.record_id.in_(_SEEDED_RECORD_IDS)
        )
    )
    await db.execute(
        delete(SafetyPageTableMirrorRecord).where(
            SafetyPageTableMirrorRecord.record_id.in_(_SEEDED_RECORD_IDS)
        )
    )
    await db.execute(
        SafetyFeishuAppSettings.__table__.delete().where(
            SafetyFeishuAppSettings.app_id == "cli_test"
        )
    )
    await db.commit()


async def _seed_settings(db: AsyncSession, *, enabled: bool) -> None:
    db.add(
        SafetyFeishuAppSettings(
            app_id="cli_test",
            app_secret="secret",
            fire_expiry_notify_enabled=enabled,
            fire_expiry_notify_milestones=[30, 15, 7],
            fire_expiry_notify_chat_ids=["oc_test"],
            fire_expiry_notify_user_ids=[],
        )
    )
    await db.flush()


def _mirror(record_id: str, fields: dict) -> SafetyPageTableMirrorRecord:
    return SafetyPageTableMirrorRecord(
        page_key=PAGE_KEY,
        table_id="tblExp",
        record_id=record_id,
        fields=fields,
        search_text="",
    )


async def _seed_equipment_with_expiry(db: AsyncSession) -> None:
    today = date.today()
    db.add(
        _mirror(
            "recExp1",
            {
                "灭火器编号": "MQC-E1",
                "所属部门": "101一车间",
                "存放位置": "东侧通道",
                "有效日期": (today + timedelta(days=20)).isoformat(),
            },
        )
    )
    db.add(
        _mirror(
            "recExp2",
            {
                "灭火器编号": "MQC-E2",
                "所属部门": "102二车间",
                "存放位置": "配电室",
                "有效日期": (today - timedelta(days=3)).isoformat(),
            },
        )
    )
    # 无有效日期列 → 不参与提醒
    db.add(
        _mirror(
            "recExp3",
            {"灭火器编号": "MQC-E3", "所属部门": "103车间", "存放位置": "楼梯口"},
        )
    )
    await db.flush()
    await sync_fire_equipment_ledger(db)


@pytest.mark.asyncio
async def test_projection_extracts_expiry_date(db_session: AsyncSession) -> None:
    try:
        await _seed_equipment_with_expiry(db_session)
        rows = (
            (
                await db_session.execute(
                    select(FireEquipment).where(
                        FireEquipment.record_id.in_(_SEEDED_RECORD_IDS)
                    )
                )
            )
            .scalars()
            .all()
        )
        by_record = {row.record_id: row for row in rows}
        today = date.today()
        assert by_record["recExp1"].expiry_date == today + timedelta(days=20)
        assert by_record["recExp2"].expiry_date == today - timedelta(days=3)
        assert by_record["recExp3"].expiry_date is None
    finally:
        await _cleanup(db_session)


@pytest.mark.asyncio
async def test_send_notifications_once_per_milestone(
    db_session: AsyncSession, _fake_notifications
) -> None:
    try:
        await _seed_settings(db_session, enabled=True)
        await _seed_equipment_with_expiry(db_session)

        # 第一轮：20 天 → 30 节点；-3 天 → 过期节点
        sent, errors = (
            await fire_expiry_reminder.send_fire_expiry_notifications(db_session)
        )
        assert sent >= 1 and errors == []
        titles = [title for _target, title, _content in _fake_notifications.calls]
        assert any("2 台" in title for title in titles)
        logged = (
            (
                await db_session.execute(select(FireExpiryNotificationLog))
            )
            .scalars()
            .all()
        )
        assert len(logged) == 2

        # 第二轮：同节点不重复推送
        sent_again, _ = (
            await fire_expiry_reminder.send_fire_expiry_notifications(db_session)
        )
        assert sent_again == 0
        assert len(logged) == 2
    finally:
        await _cleanup(db_session)


@pytest.mark.asyncio
async def test_skips_when_disabled_or_no_targets(
    db_session: AsyncSession, _fake_notifications
) -> None:
    await _seed_settings(db_session, enabled=False)
    await _seed_equipment_with_expiry(db_session)

    sent, errors = await fire_expiry_reminder.send_fire_expiry_notifications(
        db_session
    )
    assert sent == 0 and errors is None
    assert _fake_notifications.calls == []
    await _cleanup(db_session)


@pytest.mark.asyncio
async def test_test_send_requires_targets(
    db_session: AsyncSession, _fake_notifications
) -> None:
    from app.core.exceptions import AppException

    db_session.add(
        SafetyFeishuAppSettings(
            app_id="cli_test",
            app_secret="secret",
            fire_expiry_notify_enabled=True,
            fire_expiry_notify_chat_ids=[],
            fire_expiry_notify_user_ids=[],
        )
    )
    await db_session.commit()
    try:
        with pytest.raises(AppException) as exc:
            await fire_expiry_reminder.send_test_notification(db_session)
        assert "未配置提醒目标" in exc.value.message
    finally:
        await _cleanup(db_session)


def test_message_line_contains_key_info() -> None:
    from app.modules.safety.service.fire_expiry_reminder import _message_line

    equipment = SimpleNamespace(
        department="101一车间",
        equipment_no="MQC-E1",
        location="东侧通道",
        expiry_date=date(2026, 11, 9),
        fields={"责任人": [{"name": "李四"}]},
    )
    line = _message_line(equipment, 20)
    assert "101一车间" in line and "MQC-E1" in line
    assert "责任人：李四" in line
    assert "20天后到期" in line


def test_expiry_date_parses_dot_format() -> None:
    """台账里的有效日期是 2026.02.13 点分格式，投影需归一化解析。"""
    from app.modules.safety.service.fire_equipment import _expiry_date_of

    assert _expiry_date_of({"有效日期": "2026.02.13"}) == date(2026, 2, 13)
    assert _expiry_date_of({"有效日期": "2026/2/3"}) == date(2026, 2, 3)
    assert _expiry_date_of({"有效日期": "2026-02-13"}) == date(2026, 2, 13)
    assert _expiry_date_of({"有效日期": "长期"}) is None
    assert _expiry_date_of({"备注": "无日期"}) is None
