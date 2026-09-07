"""质量模块通知设置：服务读写、API、以及提醒/趋势通知消费配置的行为。"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.change_action_plan import ChangeActionPlan
from app.modules.quality.models.finished_trend_alert_notification import (
    FinishedTrendAlertNotification,
)
from app.modules.quality.service import change_action_plan as cap_service
from app.modules.quality.service import inspection_dashboard_calc as calc
from app.modules.quality.service import quality_notification_settings as ns

pytestmark = pytest.mark.anyio

_NOTIFICATION_SETTINGS_DDL = """
    CREATE TABLE IF NOT EXISTS quality.quality_notification_settings (
        notification_type VARCHAR(50) NOT NULL,
        notification_label VARCHAR(100) NOT NULL,
        is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        lead_days INTEGER NOT NULL DEFAULT 3,
        repeat_interval_days INTEGER NOT NULL DEFAULT 1,
        send_time VARCHAR(5) NOT NULL DEFAULT '09:00',
        recipients JSON NULL,
        sort_order INTEGER NOT NULL DEFAULT 0,
        id UUID PRIMARY KEY,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        created_by UUID NULL,
        updated_by UUID NULL,
        is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
        CONSTRAINT uq_quality_notification_settings_notification_type
            UNIQUE (notification_type)
    )
"""

_CHANGE_ACTION_PLANS_DDL = """
    CREATE TABLE IF NOT EXISTS quality.quality_change_action_plans (
        id UUID PRIMARY KEY,
        change_id UUID NULL,
        change_code VARCHAR(100) NOT NULL,
        project_name VARCHAR(255) NOT NULL,
        related_work TEXT NULL,
        owner_name VARCHAR(100) NULL,
        owner_user_id VARCHAR(100) NULL,
        director_name VARCHAR(100) NULL,
        director_user_id VARCHAR(100) NULL,
        deadline_date DATE NULL,
        status VARCHAR(100) NULL,
        delay_flag VARCHAR(100) NULL,
        delayed_deadline_date DATE NULL,
        feishu_record_id VARCHAR(100) NULL,
        sync_status VARCHAR(20) NOT NULL DEFAULT 'pending',
        sync_error TEXT NULL,
        last_synced_at TIMESTAMPTZ NULL,
        reminder_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        reminder_status VARCHAR(20) NOT NULL DEFAULT 'pending',
        last_reminded_at TIMESTAMPTZ NULL,
        reminder_confirmed_at TIMESTAMPTZ NULL,
        reminder_confirmed_by VARCHAR(100) NULL,
        reminder_message_id VARCHAR(100) NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        created_by UUID NULL,
        updated_by UUID NULL,
        is_deleted BOOLEAN NOT NULL DEFAULT FALSE
    )
"""

_SETTING_TYPES = ("change_action_plan_due", "inspection_trend_alert")


@pytest.fixture(autouse=True)
async def _notification_settings_tables(
    db_session: AsyncSession,
) -> AsyncIterator[Any]:
    await db_session.execute(text("CREATE SCHEMA IF NOT EXISTS quality"))
    await db_session.execute(text(_NOTIFICATION_SETTINGS_DDL))
    await db_session.execute(text(_CHANGE_ACTION_PLANS_DDL))
    await db_session.execute(
        text("DELETE FROM quality.quality_notification_settings")
    )
    await db_session.execute(
        text("DELETE FROM quality.quality_change_action_plans")
    )
    await db_session.commit()
    yield
    await db_session.execute(
        text("DELETE FROM quality.quality_notification_settings")
    )
    await db_session.execute(
        text("DELETE FROM quality.quality_change_action_plans")
    )
    await db_session.commit()


async def _insert_setting_row(
    db_session: AsyncSession,
    *,
    notification_type: str,
    is_enabled: bool = True,
    recipients: str = "{}",
    lead_days: int = 3,
    repeat_interval_days: int = 1,
    send_time: str = "00:00",
) -> None:
    await db_session.execute(
        text(
            """
            INSERT INTO quality.quality_notification_settings (
                notification_type, notification_label, is_enabled,
                lead_days, repeat_interval_days, send_time, recipients, sort_order, id
            ) VALUES (
                :notification_type, :label, :is_enabled,
                :lead_days, :repeat_interval_days, :send_time,
                CAST(:recipients AS json), 1, :id
            )
            """
        ),
        {
            "notification_type": notification_type,
            "label": ns.QUALITY_NOTIFICATION_LABELS[notification_type],
            "is_enabled": is_enabled,
            "lead_days": lead_days,
            "repeat_interval_days": repeat_interval_days,
            "send_time": send_time,
            "recipients": recipients,
            "id": str(uuid.uuid4()),
        },
    )
    await db_session.commit()


# ── 基础函数 ────────────────────────────────────────────────


def test_is_past_send_time_uses_shanghai_clock() -> None:
    assert cap_service._is_past_send_time(
        "09:00", now=datetime(2026, 9, 7, 8, 59, tzinfo=ZoneInfo("Asia/Shanghai"))
    ) is False
    assert cap_service._is_past_send_time(
        "09:00", now=datetime(2026, 9, 7, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    ) is True
    assert cap_service._is_past_send_time("bad", now=None) is True


# ── API：列表种子 + 更新 ────────────────────────────────────


async def test_list_notification_settings_seeds_defaults(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    response = await client.get("/api/v1/quality/notification-settings")
    assert response.status_code == 200
    data = response.json()["data"]
    assert [item["notification_type"] for item in data] == list(_SETTING_TYPES)

    change_item = data[0]
    assert change_item["is_enabled"] is True
    assert change_item["lead_days"] == 3
    assert change_item["repeat_interval_days"] == 1
    assert change_item["send_time"] == "09:00"

    inspection_item = data[1]
    lines = {line["entity_code"]: line for line in inspection_item["inspection_lines"]}
    assert len(lines) == 15
    assert [item["name"] for item in lines["qc_finished_internal"]["recipients"]] == [
        "陈连平",
        "席晓",
    ]
    assert lines["qc_finished_pure_water"]["recipients"] == []


async def test_update_change_action_plan_due_roundtrip(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    put_response = await client.put(
        "/api/v1/quality/notification-settings/change_action_plan_due",
        json={
            "is_enabled": True,
            "lead_days": 7,
            "repeat_interval_days": 2,
            "send_time": "14:30",
            "fallback_recipients": [
                {"open_id": "ou_backup", "name": "兜底接收人"},
            ],
        },
    )
    assert put_response.status_code == 200
    body = put_response.json()["data"]
    assert body["lead_days"] == 7
    assert body["fallback_recipients"][0]["open_id"] == "ou_backup"

    config = await ns.load_change_action_plan_due_config(db_session)
    assert config.is_enabled is True
    assert config.lead_days == 7
    assert config.repeat_interval_days == 2
    assert config.send_time == "14:30"
    assert config.fallback_recipients[0]["open_id"] == "ou_backup"


async def test_update_rejects_unknown_type_and_line(
    client: AsyncClient,
) -> None:
    unknown = await client.put(
        "/api/v1/quality/notification-settings/no_such_type",
        json={"is_enabled": False},
    )
    assert unknown.status_code == 404

    bad_line = await client.put(
        "/api/v1/quality/notification-settings/inspection_trend_alert",
        json={
            "is_enabled": True,
            "inspection_lines": [
                {"entity_code": "qc_finished_internal", "enabled": False},
                {"entity_code": "not_a_line", "enabled": True},
            ],
        },
    )
    assert bad_line.status_code == 404


async def test_update_inspection_lines_roundtrip(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    put_response = await client.put(
        "/api/v1/quality/notification-settings/inspection_trend_alert",
        json={
            "is_enabled": True,
            "inspection_lines": [
                {
                    "entity_code": "qc_finished_internal",
                    "enabled": False,
                    "recipients": [],
                },
                {
                    "entity_code": "qc_finished_pure_water",
                    "enabled": True,
                    "recipients": [{"open_id": "ou_water", "name": "水质员"}],
                },
            ],
        },
    )
    assert put_response.status_code == 200

    config = await ns.load_inspection_trend_alert_config(db_session)
    assert config.is_enabled is True
    assert config.lines["qc_finished_internal"]["enabled"] is False
    assert config.lines["qc_finished_internal"]["recipients"] == []
    assert config.lines["qc_finished_pure_water"]["recipients"][0]["open_id"] == (
        "ou_water"
    )
    # 未提交配置的产品线保持默认启用、无接收人（走系统默认解析）
    assert config.lines["qc_finished_mvt"] == {"enabled": True, "recipients": []}


# ── 变更计划到期提醒消费配置 ────────────────────────────────


async def _insert_plan(db_session: AsyncSession, **overrides: Any) -> uuid.UUID:
    plan_id = uuid.uuid4()
    values: dict[str, Any] = {
        "id": str(plan_id),
        "change_code": "BG-NOTIF",
        "project_name": "通知设置测试计划",
        "deadline_date": None,
        "status": "进行中",
        "reminder_enabled": True,
    }
    values.update(overrides)
    deadline = values.get("deadline_date")
    if isinstance(deadline, str):
        deadline = date.fromisoformat(deadline)
    last_reminded_at = values.get("last_reminded_at")
    if isinstance(last_reminded_at, str):
        last_reminded_at = datetime.fromisoformat(last_reminded_at)
    await db_session.execute(
        text(
            """
            INSERT INTO quality.quality_change_action_plans (
                id, change_code, project_name, deadline_date, status,
                reminder_enabled, owner_user_id, director_user_id,
                last_reminded_at
            ) VALUES (
                :id, :change_code, :project_name, :deadline_date, :status,
                :reminder_enabled, :owner_user_id, :director_user_id,
                :last_reminded_at
            )
            """
        ),
        {
            **values,
            "deadline_date": deadline,
            "owner_user_id": values.get("owner_user_id"),
            "director_user_id": values.get("director_user_id"),
            "last_reminded_at": last_reminded_at,
        },
    )
    return plan_id


async def test_find_due_respects_enabled_and_windows(
    db_session: AsyncSession,
) -> None:
    today = datetime.now(UTC).date()
    await _insert_setting_row(
        db_session,
        notification_type="change_action_plan_due",
        is_enabled=True,
        lead_days=7,
        repeat_interval_days=2,
        send_time="00:00",
    )

    due_id = await _insert_plan(
        db_session, deadline_date=(today + timedelta(days=5)).isoformat()
    )
    await _insert_plan(
        db_session, deadline_date=(today + timedelta(days=10)).isoformat()
    )  # 7 天窗口之外
    await _insert_plan(
        db_session,
        deadline_date=(today + timedelta(days=5)).isoformat(),
        last_reminded_at=(
            datetime.now(UTC) - timedelta(days=1)
        ).isoformat(),  # 间隔 2 天内已提醒
    )
    await _insert_plan(db_session, reminder_enabled=False)  # 单条停用
    await _insert_plan(db_session, status="已完成")  # 已完成

    due_items = await cap_service.find_due_change_action_plan_reminders(
        db_session, today=today
    )
    assert [item.id for item in due_items] == [due_id]


async def test_find_due_returns_empty_when_notification_disabled(
    db_session: AsyncSession,
) -> None:
    today = datetime.now(UTC).date()
    await _insert_setting_row(
        db_session,
        notification_type="change_action_plan_due",
        is_enabled=False,
    )
    await _insert_plan(
        db_session, deadline_date=(today + timedelta(days=1)).isoformat()
    )
    due_items = await cap_service.find_due_change_action_plan_reminders(
        db_session, today=today
    )
    assert due_items == []


async def test_find_due_skips_before_send_time(
    db_session: AsyncSession,
) -> None:
    today = datetime.now(UTC).date()
    now_shanghai = datetime.now(ZoneInfo("Asia/Shanghai"))
    future = now_shanghai + timedelta(minutes=90)
    if future.date() != now_shanghai.date():
        pytest.skip("接近午夜，无法构造当天未来发送时间")
    await _insert_setting_row(
        db_session,
        notification_type="change_action_plan_due",
        is_enabled=True,
        send_time=future.strftime("%H:%M"),
    )
    await _insert_plan(
        db_session, deadline_date=(today + timedelta(days=1)).isoformat()
    )
    due_items = await cap_service.find_due_change_action_plan_reminders(
        db_session,
        today=today,
    )
    assert due_items == []

    # 手动批量执行忽略发送时间窗
    manual_items = await cap_service.run_change_action_plan_reminders(db_session)
    assert manual_items.scanned == 1


async def test_send_uses_fallback_recipients_when_no_owner(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _insert_setting_row(
        db_session,
        notification_type="change_action_plan_due",
        is_enabled=True,
        recipients=(
            '{"fallback_recipients": '
            '[{"open_id": "ou_a", "name": "甲"}, {"open_id": "ou_b", "name": "乙"}]}'
        ),
    )
    plan = ChangeActionPlan(
        id=uuid.uuid4(),
        change_code="BG-FALLBACK",
        project_name="无负责人计划",
        deadline_date=date.today() + timedelta(days=1),
        status="进行中",
        reminder_enabled=True,
    )
    db_session.add(plan)
    await db_session.commit()

    sent_targets: list[str] = []

    async def _fake_send(open_id: str, **kwargs: Any) -> str | None:
        sent_targets.append(open_id)
        return f"msg_{len(sent_targets)}"

    monkeypatch.setattr(cap_service, "send_user_card_with_message_id", _fake_send)

    result = await cap_service.send_change_action_plan_reminder(db_session, plan)
    assert result == "msg_1"
    assert sent_targets == ["ou_a", "ou_b"]

    await db_session.commit()
    refreshed = await db_session.get(ChangeActionPlan, plan.id)
    assert refreshed is not None
    assert refreshed.reminder_status == "reminded"
    assert refreshed.reminder_message_id == "msg_1"


# ── 检验趋势异常提醒消费配置 ────────────────────────────────


async def test_resolve_recipients_prefers_line_config(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolve_by_name = AsyncMock(
        side_effect=lambda db, *, name, open_id=None, email=None: {
            "name": name,
            "open_id": open_id,
            "email": email,
        }
    )
    monkeypatch.setattr(calc, "_resolve_recipient_by_name", resolve_by_name)

    recipients = await calc._resolve_dashboard_recipients(
        db_session,
        entity_code="qc_finished_internal",
        batch_no="B-001",
        line_config={
            "enabled": True,
            "recipients": [{"open_id": "ou_x", "name": "配置人"}],
        },
    )
    assert recipients == [{"name": "配置人", "open_id": "ou_x", "email": None}]
    resolve_by_name.assert_awaited_once()


async def test_resolve_recipients_falls_back_to_overrides(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolve_by_name = AsyncMock(
        side_effect=lambda db, *, name, open_id=None, email=None: {
            "name": name,
            "open_id": open_id,
            "email": email,
        }
    )
    monkeypatch.setattr(calc, "_resolve_recipient_by_name", resolve_by_name)

    recipients = await calc._resolve_dashboard_recipients(
        db_session,
        entity_code="qc_finished_internal",
        batch_no="B-001",
        line_config={"enabled": True, "recipients": []},
    )
    assert [item["name"] for item in recipients] == ["陈连平", "席晓"]


def _make_notification(status: str = "sent") -> FinishedTrendAlertNotification:
    return FinishedTrendAlertNotification(
        entity_code="qc_finished_internal",
        batch_no="B-PAUSE",
        metric_key="k",
        metric_label="指标",
        actual_value=1.0,
        upper_control_limit=0.8,
        lower_control_limit=0.2,
        notification_status=status,
    )


async def test_materialize_paused_when_notification_disabled(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _insert_setting_row(
        db_session,
        notification_type="inspection_trend_alert",
        is_enabled=False,
    )
    monkeypatch.setattr(
        calc,
        "_get_existing_dashboard_notification",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        calc,
        "_resolve_dashboard_recipients",
        AsyncMock(side_effect=AssertionError("停用后不应解析接收人")),
    )

    result = await calc._materialize_dashboard_alert(
        db_session,
        source_label="霉酚酸（内控）",
        entity_code="qc_finished_internal",
        batch_no="B-PAUSE",
        metric_key="k",
        metric_label="指标",
        actual_value=1.0,
        mean=0.5,
        std_dev=0.1,
        upper_control_limit=0.8,
        lower_control_limit=0.2,
        spec_lines=[{"label": "标准上限", "value": 0.8}],
    )
    assert result["notification_status"] == "paused"
    assert "已停用" in str(result["notification_error"])


async def test_materialize_paused_when_line_disabled(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _insert_setting_row(
        db_session,
        notification_type="inspection_trend_alert",
        is_enabled=True,
        recipients=(
            '{"lines": {"qc_finished_internal": '
            '{"enabled": false, "recipients": []}}}'
        ),
    )
    monkeypatch.setattr(
        calc,
        "_get_existing_dashboard_notification",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        calc,
        "_resolve_dashboard_recipients",
        AsyncMock(side_effect=AssertionError("产品线停用后不应解析接收人")),
    )

    result = await calc._materialize_dashboard_alert(
        db_session,
        source_label="霉酚酸（内控）",
        entity_code="qc_finished_internal",
        batch_no="B-PAUSE-LINE",
        metric_key="k",
        metric_label="指标",
        actual_value=1.0,
        mean=0.5,
        std_dev=0.1,
        upper_control_limit=0.8,
        lower_control_limit=0.2,
        spec_lines=[],
    )
    assert result["notification_status"] == "paused"


async def test_materialize_uses_configured_line_recipients(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _insert_setting_row(
        db_session,
        notification_type="inspection_trend_alert",
        is_enabled=True,
        recipients=(
            '{"lines": {"qc_finished_internal": {"enabled": true, '
            '"recipients": [{"open_id": "ou_line", "name": "线路配置人"}]}}}'
        ),
    )
    monkeypatch.setattr(
        calc,
        "_get_existing_dashboard_notification",
        AsyncMock(return_value=None),
    )
    resolve_by_name = AsyncMock(
        return_value={"name": "线路配置人", "open_id": "ou_line", "email": None}
    )
    monkeypatch.setattr(calc, "_resolve_recipient_by_name", resolve_by_name)
    send_notifications = AsyncMock(
        return_value={"status": "sent", "message_id": "m1", "error": None}
    )
    monkeypatch.setattr(calc, "_send_dashboard_alert_notifications", send_notifications)

    notification = _make_notification("unmapped")
    create_notification = AsyncMock(return_value=notification)
    monkeypatch.setattr(calc, "_create_dashboard_notification", create_notification)
    monkeypatch.setattr(
        calc,
        "_serialize_dashboard_alert",
        lambda *, notification, **kwargs: {"notification_status": notification.notification_status},  # noqa: E501
    )

    result = await calc._materialize_dashboard_alert(
        db_session,
        source_label="霉酚酸（内控）",
        entity_code="qc_finished_internal",
        batch_no="B-CONFIG",
        metric_key="k",
        metric_label="指标",
        actual_value=1.0,
        mean=0.5,
        std_dev=0.1,
        upper_control_limit=0.8,
        lower_control_limit=0.2,
        spec_lines=[],
    )
    assert result == {"notification_status": "unmapped"}
    resolve_by_name.assert_awaited_once_with(
        db_session, name="线路配置人", open_id="ou_line", email=None
    )
