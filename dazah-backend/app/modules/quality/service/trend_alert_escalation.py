"""成品/纯化水异常升级推送：到点复检，仍异常则升级推送各部门负责人。

首波告警（超 均值±3σ / OOT 限度线）成功通知后入队（calc 侧）；本模块在
escalate_at 到期后复检：重拉该产品线当前数据、按首报同源口径（均值±3σ /
限度线）判定该批次是否仍异常——仍异常则推送 提炼部门负责人 + 该产品QA；
已恢复或通知停用则取消。重试有上限，防死循环。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.finished_trend_alert_escalation import (
    QualityTrendAlertEscalation,
)
from app.modules.quality.service import inspection_dashboard_calc as calc
from app.modules.quality.service.quality_notification_settings import (
    load_inspection_trend_alert_escalation_config,
)

logger = logging.getLogger(__name__)

MAX_ESCALATION_RETRIES = 3
_ESCALATION_BATCH_LIMIT = 20


async def find_due_trend_alert_escalations(
    db: AsyncSession,
) -> list[QualityTrendAlertEscalation]:
    """取到期待复检的升级队列（跳过被其他实例锁定的行）。"""
    now = datetime.now(UTC)
    result = await db.execute(
        select(QualityTrendAlertEscalation)
        .where(
            QualityTrendAlertEscalation.status == "pending",
            QualityTrendAlertEscalation.escalate_at.is_not(None),
            QualityTrendAlertEscalation.escalate_at <= now,
            QualityTrendAlertEscalation.is_deleted.is_(False),
        )
        .order_by(QualityTrendAlertEscalation.escalate_at.asc())
        .limit(_ESCALATION_BATCH_LIMIT)
        .with_for_update(skip_locked=True)
    )
    return list(result.scalars().all())


async def process_trend_alert_escalation(
    db: AsyncSession, item: QualityTrendAlertEscalation
) -> None:
    """复检单条升级队列；失败重试至上限后标 failed（引擎按轮继续扫余量）。"""
    try:
        await _process(db, item)
    except Exception as exc:  # noqa: BLE001 —— 复检失败重试，不丢队列
        item.retry_count = (item.retry_count or 0) + 1
        item.last_error = type(exc).__name__
        if item.retry_count >= MAX_ESCALATION_RETRIES:
            item.status = "failed"
        await db.commit()
        if item.status != "failed":
            raise


async def _process(db: AsyncSession, item: QualityTrendAlertEscalation) -> None:
    trend_config = await calc.load_inspection_trend_alert_config(db)
    line_config = trend_config.lines.get(item.entity_code) or {}
    if not trend_config.is_enabled or not line_config.get("enabled", True):
        item.status = "cancelled"
        await db.commit()
        return
    escalation_config = await load_inspection_trend_alert_escalation_config(db)
    if not escalation_config.is_enabled:
        item.status = "cancelled"
        await db.commit()
        return

    current_value, values = await _fetch_current_and_series(db, item)
    if current_value is None or len(values) < 3:
        # 批次已不在数据里（删除/回退）或样本不足：无需升级
        item.status = "cancelled"
        await db.commit()
        return

    stats = calc._compute_metric_statistics(values)
    payload = item.payload or {}
    spec_lines = list(payload.get("spec_lines") or [])
    still_out = False
    upper = stats.get("upper_control_limit")
    lower = stats.get("lower_control_limit")
    if upper is not None and lower is not None:
        still_out = not (lower <= current_value <= upper)
    if not still_out and calc._is_value_out_of_spec_lines(current_value, spec_lines):
        still_out = True
    if not still_out:
        item.status = "cancelled"
        await db.commit()
        return

    recipients = await _resolve_escalation_recipients(
        db, item, trend_config.lines.get(item.entity_code)
    )
    if not any(
        r.get("open_id") or r.get("email") for r in recipients
    ):
        item.status = "failed"
        item.last_error = "未找到升级通知对象"
        await db.commit()
        return

    send_result = await calc._send_dashboard_alert_notifications(
        db=db,
        sender_user_open_id=None,
        source_label=f"{item.source_label or '趋势'}（升级提醒）",
        recipients=recipients,
        batch_no=item.batch_no,
        metric_label=item.metric_label,
        actual_value=current_value,
        upper_control_limit=upper,
        lower_control_limit=lower,
        spec_lines=spec_lines,
    )
    if send_result["status"] in {"sent", "partial"}:
        item.status = "escalated"
        item.escalated_at = datetime.now(UTC)
        item.escalated_message_id = send_result.get("message_id")
        item.last_error = None
    else:
        item.retry_count = (item.retry_count or 0) + 1
        item.last_error = str(send_result.get("error") or "升级推送失败")
        if item.retry_count >= MAX_ESCALATION_RETRIES:
            item.status = "failed"
    await db.commit()


async def _fetch_current_and_series(
    db: AsyncSession, item: QualityTrendAlertEscalation
) -> tuple[float | None, list[float]]:
    """重拉该产品线当前数据：返回 (该批次现值, 全部有效值序列)。"""
    records = await calc._search_entity_records_with_fallback(
        db,
        item.entity_code,
        field_names=[calc.FINISHED_DASHBOARD_BATCH_FIELD, item.metric_key],
    )
    current_value: float | None = None
    values: list[float] = []
    for record in records:
        fields = record.get("fields") or {}
        batch_no = calc._normalize(fields.get(calc.FINISHED_DASHBOARD_BATCH_FIELD))
        if not batch_no:
            continue
        value = calc._parse_numeric_metric(fields.get(item.metric_key))
        if value is None:
            continue
        values.append(value)
        if batch_no == item.batch_no:
            current_value = value
    return current_value, values


async def _resolve_escalation_recipients(
    db: AsyncSession,
    item: QualityTrendAlertEscalation,
    line_config: dict[str, Any] | None,
) -> list[dict[str, str | None]]:
    """升级收件人 = 提炼部门负责人（按批号）+ 该产品QA；同名/同 open_id 去重。"""
    recipients: list[dict[str, str | None]] = []
    seen: set[str] = set()

    head = await calc._resolve_refining_recipient(db, item.batch_no)
    if head is not None:
        recipients.append(head)
        seen.add(str(head.get("open_id") or head.get("name") or "").strip())

    for qa in (line_config or {}).get("qa_recipients") or []:
        name = str(qa.get("name") or "")
        open_id = str(qa.get("open_id") or "").strip()
        key = open_id or name
        if not key or key in seen:
            continue
        seen.add(key)
        if open_id:
            recipients.append(
                {
                    "name": name,
                    "open_id": open_id,
                    "email": str(qa.get("email") or "").strip() or None,
                }
            )
        else:
            recipients.append(await calc._resolve_recipient_by_name(db, name=name))
    return recipients
