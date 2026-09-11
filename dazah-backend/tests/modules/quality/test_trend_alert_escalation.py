"""成品/纯化水异常升级推送流程测试：入队、复检升级、恢复取消。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.finished_trend_alert_escalation import (
    QualityTrendAlertEscalation,
)
from app.modules.quality.service import inspection_dashboard_calc as calc
from app.modules.quality.service import trend_alert_escalation as esc
from app.modules.quality.service.quality_notification_settings import (
    InspectionTrendAlertConfig,
    InspectionTrendAlertEscalationConfig,
)


async def _ensure_table(db: AsyncSession) -> None:
    await db.run_sync(
        lambda sync_db: QualityTrendAlertEscalation.__table__.create(
            sync_db.connection(), checkfirst=True
        )
    )


async def _purge(db: AsyncSession) -> None:
    await db.execute(text("DELETE FROM quality.quality_trend_alert_escalations"))


def _enabled_trend_config() -> InspectionTrendAlertConfig:
    return InspectionTrendAlertConfig(
        is_enabled=True,
        lines={
            "qc_finished_internal": {
                "enabled": True,
                "recipients": [{"open_id": "ou_zqz", "name": "张起智"}],
                "qa_recipients": [
                    {"open_id": "ou_qa1", "name": "QA员", "email": "qa@livzon.cn"}
                ],
            }
        },
    )


def _enabled_escalation_config() -> InspectionTrendAlertEscalationConfig:
    return InspectionTrendAlertEscalationConfig(
        is_enabled=True,
        first_recipients=[{"name": "李文昊"}],
        escalation_hours=2,
    )


@pytest.mark.anyio
async def test_materialize_enqueues_escalation_after_send(
    db_session: AsyncSession, monkeypatch
) -> None:
    await _ensure_table(db_session)
    await _purge(db_session)
    monkeypatch.setattr(
        calc, "_get_existing_dashboard_notification", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        calc,
        "load_inspection_trend_alert_config",
        AsyncMock(return_value=_enabled_trend_config()),
    )
    monkeypatch.setattr(
        calc,
        "load_inspection_trend_alert_escalation_config",
        AsyncMock(return_value=_enabled_escalation_config()),
    )
    resolve_by_name = AsyncMock(
        side_effect=lambda db, name, open_id=None, email=None: {
            "name": name,
            "open_id": open_id or f"ou_{name}",
            "email": None,
        }
    )
    monkeypatch.setattr(calc, "_resolve_recipient_by_name", resolve_by_name)
    send_notifications = AsyncMock(
        return_value={"status": "sent", "message_id": "m1", "error": None}
    )
    monkeypatch.setattr(
        calc, "_send_dashboard_alert_notifications", send_notifications
    )
    monkeypatch.setattr(
        calc,
        "_create_dashboard_notification",
        AsyncMock(
            return_value=SimpleNamespace(notification_status="sent")
        ),
    )
    monkeypatch.setattr(
        calc,
        "_serialize_dashboard_alert",
        lambda *, notification, **kwargs: {
            "notification_status": notification.notification_status
        },
    )

    await calc._materialize_dashboard_alert(
        db_session,
        source_label="霉酚酸（内控）",
        entity_code="qc_finished_internal",
        batch_no="B-ESC",
        metric_key="k",
        metric_label="指标",
        actual_value=5.0,
        mean=0.5,
        std_dev=0.1,
        upper_control_limit=0.8,
        lower_control_limit=0.2,
        spec_lines=[],
    )
    await db_session.commit()

    # 首波 = 产品线收件人（张起智）+ 产品QA（QA员）+ 首推人（李文昊，
    # 姓名解析补 open_id）
    recipients = send_notifications.await_args.kwargs["recipients"]
    names = [r["name"] for r in recipients]
    assert names == ["张起智", "QA员", "李文昊"]

    rows = (
        await db_session.execute(
            text(
                "SELECT status, batch_no FROM quality.quality_trend_alert_escalations"
            )
        )
    ).fetchall()
    assert rows == [("pending", "B-ESC")]


@pytest.mark.anyio
async def test_process_escalation_still_out_sends_to_leaders(
    db_session: AsyncSession, monkeypatch
) -> None:
    await _ensure_table(db_session)
    await _purge(db_session)
    item = QualityTrendAlertEscalation(
        entity_code="qc_finished_internal",
        source_label="霉酚酸（内控）",
        batch_no="B1",
        metric_key="k",
        metric_label="指标",
        payload={
            "spec_lines": [{"label": "标准上限", "value": 10.0}],
            "escalation_hours": 2,
        },
        status="pending",
        escalate_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db_session.add(item)
    await db_session.commit()

    # 复检数据：B1 仍显著高于其余批次（超 mean±3σ）
    records = [
        {"fields": {"批号": f"B{i}", "k": 1.0}} for i in range(10)
    ] + [{"fields": {"批号": "B1", "k": 5.0}}]
    monkeypatch.setattr(
        calc,
        "_search_entity_records_with_fallback",
        AsyncMock(return_value=records),
    )
    monkeypatch.setattr(
        calc,
        "_resolve_refining_recipient",
        AsyncMock(
            return_value={"name": "提炼负责人", "open_id": "ou_head", "email": None}
        ),
    )
    monkeypatch.setattr(
        calc,
        "load_inspection_trend_alert_config",
        AsyncMock(return_value=_enabled_trend_config()),
    )
    monkeypatch.setattr(
        calc,
        "load_inspection_trend_alert_escalation_config",
        AsyncMock(return_value=_enabled_escalation_config()),
    )
    send_notifications = AsyncMock(
        return_value={"status": "sent", "message_id": "m2", "error": None}
    )
    monkeypatch.setattr(
        calc, "_send_dashboard_alert_notifications", send_notifications
    )

    await esc.process_trend_alert_escalation(db_session, item)
    await db_session.commit()

    await db_session.refresh(item)
    assert item.status == "escalated"
    assert item.escalated_message_id == "m2"
    recipients = send_notifications.await_args.kwargs["recipients"]
    names = [r["name"] for r in recipients]
    assert "提炼负责人" in names
    assert "QA员" in names  # 该产品QA 参与升级推送


@pytest.mark.anyio
async def test_process_escalation_recovered_cancels(
    db_session: AsyncSession, monkeypatch
) -> None:
    await _ensure_table(db_session)
    await _purge(db_session)
    item = QualityTrendAlertEscalation(
        entity_code="qc_finished_internal",
        source_label="霉酚酸（内控）",
        batch_no="B1",
        metric_key="k",
        metric_label="指标",
        payload={"spec_lines": [], "escalation_hours": 2},
        status="pending",
        escalate_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db_session.add(item)
    await db_session.commit()

    # 复检数据全部回落到正常（无超限）
    records = [{"fields": {"批号": f"B{i}", "k": 1.0}} for i in range(11)]
    monkeypatch.setattr(
        calc,
        "_search_entity_records_with_fallback",
        AsyncMock(return_value=records),
    )
    send_notifications = AsyncMock()
    monkeypatch.setattr(
        calc, "_send_dashboard_alert_notifications", send_notifications
    )

    await esc.process_trend_alert_escalation(db_session, item)
    await db_session.commit()

    await db_session.refresh(item)
    assert item.status == "cancelled"
    send_notifications.assert_not_awaited()

@pytest.mark.anyio
async def test_find_due_returns_pending_rows_only_once(
    db_session: AsyncSession,
) -> None:
    """到期 pending 行进入队列（带行锁查询可执行）。"""
    await _ensure_table(db_session)
    await _purge(db_session)
    item = QualityTrendAlertEscalation(
        entity_code="qc_finished_internal",
        source_label="霉酚酸（内控）",
        batch_no="B1",
        metric_key="k",
        metric_label="指标",
        payload={"spec_lines": [], "escalation_hours": 2},
        status="pending",
        escalate_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db_session.add(item)
    await db_session.commit()

    due = await esc.find_due_trend_alert_escalations(db_session)
    assert [row.id for row in due] == [item.id]


@pytest.mark.anyio
async def test_process_escalation_cancels_when_trend_disabled(
    db_session: AsyncSession, monkeypatch
) -> None:
    await _ensure_table(db_session)
    await _purge(db_session)
    item = QualityTrendAlertEscalation(
        entity_code="qc_finished_internal",
        source_label="霉酚酸（内控）",
        batch_no="B1",
        metric_key="k",
        metric_label="指标",
        payload={"spec_lines": [], "escalation_hours": 2},
        status="pending",
        escalate_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db_session.add(item)
    await db_session.commit()
    monkeypatch.setattr(
        calc,
        "load_inspection_trend_alert_config",
        AsyncMock(
            return_value=InspectionTrendAlertConfig(is_enabled=False)
        ),
    )

    await esc.process_trend_alert_escalation(db_session, item)
    await db_session.commit()
    await db_session.refresh(item)
    assert item.status == "cancelled"


@pytest.mark.anyio
async def test_process_escalation_cancels_when_escalation_disabled(
    db_session: AsyncSession, monkeypatch
) -> None:
    await _ensure_table(db_session)
    await _purge(db_session)
    item = QualityTrendAlertEscalation(
        entity_code="qc_finished_internal",
        source_label="霉酚酸（内控）",
        batch_no="B1",
        metric_key="k",
        metric_label="指标",
        payload={"spec_lines": [], "escalation_hours": 2},
        status="pending",
        escalate_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db_session.add(item)
    await db_session.commit()
    monkeypatch.setattr(
        calc,
        "load_inspection_trend_alert_config",
        AsyncMock(return_value=_enabled_trend_config()),
    )
    monkeypatch.setattr(
        calc,
        "load_inspection_trend_alert_escalation_config",
        AsyncMock(
            return_value=InspectionTrendAlertEscalationConfig(is_enabled=False)
        ),
    )

    await esc.process_trend_alert_escalation(db_session, item)
    await db_session.commit()
    await db_session.refresh(item)
    assert item.status == "cancelled"


@pytest.mark.anyio
async def test_process_escalation_cancels_when_series_insufficient(
    db_session: AsyncSession, monkeypatch
) -> None:
    """样本不足（<3）无法复检统计：直接取消而非失败。"""
    await _ensure_table(db_session)
    await _purge(db_session)
    item = QualityTrendAlertEscalation(
        entity_code="qc_finished_internal",
        source_label="霉酚酸（内控）",
        batch_no="B1",
        metric_key="k",
        metric_label="指标",
        payload={"spec_lines": [], "escalation_hours": 2},
        status="pending",
        escalate_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db_session.add(item)
    await db_session.commit()
    monkeypatch.setattr(
        calc,
        "_search_entity_records_with_fallback",
        AsyncMock(return_value=[{"fields": {"批号": "B1", "k": 5.0}}]),
    )
    monkeypatch.setattr(
        calc,
        "load_inspection_trend_alert_config",
        AsyncMock(return_value=_enabled_trend_config()),
    )
    monkeypatch.setattr(
        calc,
        "load_inspection_trend_alert_escalation_config",
        AsyncMock(return_value=_enabled_escalation_config()),
    )

    await esc.process_trend_alert_escalation(db_session, item)
    await db_session.commit()
    await db_session.refresh(item)
    assert item.status == "cancelled"


@pytest.mark.anyio
async def test_process_escalation_retries_then_marks_failed(
    db_session: AsyncSession, monkeypatch
) -> None:
    """复检异常重试至上限后标记 failed，不再抛出。"""
    await _ensure_table(db_session)
    await _purge(db_session)
    item = QualityTrendAlertEscalation(
        entity_code="qc_finished_internal",
        source_label="霉酚酸（内控）",
        batch_no="B1",
        metric_key="k",
        metric_label="指标",
        payload={"spec_lines": [], "escalation_hours": 2},
        status="pending",
        escalate_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db_session.add(item)
    await db_session.commit()
    monkeypatch.setattr(
        esc, "_process", AsyncMock(side_effect=RuntimeError("boom"))
    )

    with pytest.raises(RuntimeError):
        await esc.process_trend_alert_escalation(db_session, item)
    await db_session.commit()
    await db_session.refresh(item)
    assert item.status == "pending"
    assert item.retry_count == 1

    with pytest.raises(RuntimeError):
        await esc.process_trend_alert_escalation(db_session, item)
    await db_session.commit()

    # 第三次达到上限：标记 failed 且不再抛出
    await esc.process_trend_alert_escalation(db_session, item)
    await db_session.commit()

    await db_session.refresh(item)
    assert item.status == "failed"
    assert item.retry_count == 3
    assert item.last_error == "RuntimeError"

