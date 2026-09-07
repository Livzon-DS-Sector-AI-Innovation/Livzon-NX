"""质量模块通知设置服务。

通知类型目前有两个（均为飞书个人卡片通知）：
- change_action_plan_due：变更计划到期提醒（定时 + 手动）
- inspection_trend_alert：成品检验趋势异常提醒（打开趋势仪表盘时事件触发）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.modules.quality.models.notification_settings import QualityNotificationSetting
from app.modules.quality.schemas.notification_settings import (
    InspectionLineNotificationPayload,
    QualityNotificationRecipientItem,
    QualityNotificationSettingItem,
    UpdateQualityNotificationSettingRequest,
)
from app.modules.quality.service.inspection_dashboard_config import (
    FINISHED_DASHBOARD_LINE_CATALOG,
    FINISHED_DASHBOARD_RECIPIENT_OVERRIDES,
    get_finished_dashboard_line_labels,
)

logger = logging.getLogger(__name__)

QUALITY_NOTIFICATION_CHANGE_ACTION_PLAN_DUE = "change_action_plan_due"
QUALITY_NOTIFICATION_INSPECTION_TREND_ALERT = "inspection_trend_alert"

QUALITY_NOTIFICATION_LABELS: dict[str, str] = {
    QUALITY_NOTIFICATION_CHANGE_ACTION_PLAN_DUE: "变更计划到期提醒",
    QUALITY_NOTIFICATION_INSPECTION_TREND_ALERT: "成品检验趋势异常提醒",
}

DEFAULT_LEAD_DAYS = 3
DEFAULT_REPEAT_INTERVAL_DAYS = 1
DEFAULT_SEND_TIME = "09:00"

_VALID_NOTIFICATION_TYPES = set(QUALITY_NOTIFICATION_LABELS)


@dataclass
class ChangeActionPlanDueConfig:
    is_enabled: bool = True
    lead_days: int = DEFAULT_LEAD_DAYS
    repeat_interval_days: int = DEFAULT_REPEAT_INTERVAL_DAYS
    send_time: str = DEFAULT_SEND_TIME
    fallback_recipients: list[dict[str, str | None]] = field(default_factory=list)


@dataclass
class InspectionTrendAlertConfig:
    is_enabled: bool = True
    # entity_code -> {"enabled": bool, "recipients": [{"open_id", "name"}]}
    lines: dict[str, dict[str, Any]] = field(default_factory=dict)


def _normalize_recipient_item(item: Any) -> dict[str, str | None] | None:
    if not isinstance(item, dict):
        return None
    open_id = str(item.get("open_id") or "").strip() or None
    name = str(item.get("name") or "").strip()
    if not open_id and not name:
        return None
    return {"open_id": open_id, "name": name}


def _normalize_recipient_items(items: Any) -> list[dict[str, str | None]]:
    if not isinstance(items, list):
        return []
    normalized: list[dict[str, str | None]] = []
    for item in items:
        normalized_item = _normalize_recipient_item(item)
        if normalized_item:
            normalized.append(normalized_item)
    return normalized


def _default_change_action_plan_recipients() -> dict[str, Any]:
    return {"fallback_recipients": []}


def _default_inspection_recipients() -> dict[str, Any]:
    lines: dict[str, dict[str, Any]] = {}
    for entity_code, _label in FINISHED_DASHBOARD_LINE_CATALOG:
        overrides = FINISHED_DASHBOARD_RECIPIENT_OVERRIDES.get(entity_code) or ()
        lines[entity_code] = {
            "enabled": True,
            "recipients": [{"name": str(item["name"])} for item in overrides],
        }
    return {"lines": lines}


def _seed_rows() -> list[QualityNotificationSetting]:
    return [
        QualityNotificationSetting(
            notification_type=QUALITY_NOTIFICATION_CHANGE_ACTION_PLAN_DUE,
            notification_label=QUALITY_NOTIFICATION_LABELS[
                QUALITY_NOTIFICATION_CHANGE_ACTION_PLAN_DUE
            ],
            is_enabled=True,
            lead_days=DEFAULT_LEAD_DAYS,
            repeat_interval_days=DEFAULT_REPEAT_INTERVAL_DAYS,
            send_time=DEFAULT_SEND_TIME,
            recipients=_default_change_action_plan_recipients(),
            sort_order=1,
        ),
        QualityNotificationSetting(
            notification_type=QUALITY_NOTIFICATION_INSPECTION_TREND_ALERT,
            notification_label=QUALITY_NOTIFICATION_LABELS[
                QUALITY_NOTIFICATION_INSPECTION_TREND_ALERT
            ],
            is_enabled=True,
            lead_days=DEFAULT_LEAD_DAYS,
            repeat_interval_days=DEFAULT_REPEAT_INTERVAL_DAYS,
            send_time=DEFAULT_SEND_TIME,
            recipients=_default_inspection_recipients(),
            sort_order=2,
        ),
    ]


async def _get_setting_model(
    db: AsyncSession,
    notification_type: str,
) -> QualityNotificationSetting | None:
    """读取设置行；表尚未迁移（旧库直跑提醒主流程）时按缺省配置处理。

    用 SAVEPOINT 包裹探测查询：表不存在时只回滚保存点，不污染主事务。
    """
    try:
        async with db.begin_nested():
            result = await db.execute(
                select(QualityNotificationSetting).where(
                    QualityNotificationSetting.notification_type
                    == notification_type,
                    QualityNotificationSetting.is_deleted.is_(False),
                )
            )
            model = result.scalars().first()
    except (SQLAlchemyError, AttributeError) as exc:
        logger.warning(
            "质量通知设置表不可用（未迁移？），%s 按默认配置处理：%s",
            notification_type,
            type(exc).__name__,
        )
        return None
    return model


async def ensure_quality_notification_settings(db: AsyncSession) -> None:
    """确保两个已知通知类型的设置行存在（幂等）。"""
    result = await db.execute(
        select(QualityNotificationSetting.notification_type).where(
            QualityNotificationSetting.is_deleted.is_(False)
        )
    )
    existing_types = set(result.scalars().all())
    missing = [
        row
        for row in _seed_rows()
        if row.notification_type not in existing_types
    ]
    if not missing:
        return
    for row in missing:
        db.add(row)
    await db.commit()
    logger.info(
        "质量通知设置缺失行已补种：%s",
        [row.notification_type for row in missing],
    )


def _serialize_fallback_recipients(
    recipients: Any,
) -> list[QualityNotificationRecipientItem]:
    return [
        QualityNotificationRecipientItem.model_validate(item)
        for item in _normalize_recipient_items(
            recipients.get("fallback_recipients")
            if isinstance(recipients, dict)
            else None
        )
    ]


def _serialize_inspection_lines(
    recipients: Any,
) -> list[InspectionLineNotificationPayload]:
    stored_lines = (
        recipients.get("lines") if isinstance(recipients, dict) else None
    ) or {}
    labels = get_finished_dashboard_line_labels()
    items: list[InspectionLineNotificationPayload] = []
    for entity_code, entity_label in labels.items():
        stored = stored_lines.get(entity_code)
        stored = stored if isinstance(stored, dict) else {}
        items.append(
            InspectionLineNotificationPayload(
                entity_code=entity_code,
                entity_label=entity_label,
                enabled=bool(stored.get("enabled", True)),
                recipients=[
                    QualityNotificationRecipientItem.model_validate(item)
                    for item in _normalize_recipient_items(stored.get("recipients"))
                ],
            )
        )
    return items


def _serialize_setting(
    model: QualityNotificationSetting,
) -> QualityNotificationSettingItem:
    return QualityNotificationSettingItem(
        notification_type=model.notification_type,
        notification_label=model.notification_label,
        is_enabled=bool(model.is_enabled),
        lead_days=int(model.lead_days or DEFAULT_LEAD_DAYS),
        repeat_interval_days=int(model.repeat_interval_days or 1),
        send_time=str(model.send_time or DEFAULT_SEND_TIME),
        fallback_recipients=_serialize_fallback_recipients(model.recipients),
        inspection_lines=_serialize_inspection_lines(model.recipients),
    )


async def list_quality_notification_settings(
    db: AsyncSession,
) -> list[QualityNotificationSettingItem]:
    await ensure_quality_notification_settings(db)
    result = await db.execute(
        select(QualityNotificationSetting)
        .where(QualityNotificationSetting.is_deleted.is_(False))
        .order_by(QualityNotificationSetting.sort_order.asc())
    )
    return [_serialize_setting(model) for model in result.scalars().all()]


async def update_quality_notification_setting(
    db: AsyncSession,
    notification_type: str,
    data: UpdateQualityNotificationSettingRequest,
) -> QualityNotificationSettingItem:
    if notification_type not in _VALID_NOTIFICATION_TYPES:
        raise NotFoundException(resource="通知类型", resource_id=notification_type)

    await ensure_quality_notification_settings(db)
    model = await _get_setting_model(db, notification_type)
    if model is None:
        raise NotFoundException(resource="通知设置", resource_id=notification_type)

    model.is_enabled = bool(data.is_enabled)

    if notification_type == QUALITY_NOTIFICATION_CHANGE_ACTION_PLAN_DUE:
        if data.lead_days is not None:
            model.lead_days = data.lead_days
        if data.repeat_interval_days is not None:
            model.repeat_interval_days = data.repeat_interval_days
        if data.send_time is not None:
            model.send_time = data.send_time
        if data.fallback_recipients is not None:
            model.recipients = {
                "fallback_recipients": [
                    item.model_dump(exclude_none=True)
                    for item in data.fallback_recipients
                ],
            }
    else:
        if data.inspection_lines is not None:
            labels = get_finished_dashboard_line_labels()
            lines: dict[str, dict[str, Any]] = {}
            for line in data.inspection_lines:
                if line.entity_code not in labels:
                    raise NotFoundException(
                        resource="产品线", resource_id=line.entity_code
                    )
                lines[line.entity_code] = {
                    "enabled": bool(line.enabled),
                    "recipients": [
                        item.model_dump(exclude_none=True) for item in line.recipients
                    ],
                }
            model.recipients = {"lines": lines}

    await db.commit()
    await db.refresh(model)
    return _serialize_setting(model)


async def load_change_action_plan_due_config(
    db: AsyncSession,
) -> ChangeActionPlanDueConfig:
    """读取变更计划到期提醒配置；缺行时按当前线上行为返回默认值。"""
    model = await _get_setting_model(db, QUALITY_NOTIFICATION_CHANGE_ACTION_PLAN_DUE)
    if model is None:
        return ChangeActionPlanDueConfig()
    recipients = model.recipients if isinstance(model.recipients, dict) else {}
    return ChangeActionPlanDueConfig(
        is_enabled=bool(model.is_enabled),
        lead_days=int(model.lead_days or DEFAULT_LEAD_DAYS),
        repeat_interval_days=int(model.repeat_interval_days or 1),
        send_time=str(model.send_time or DEFAULT_SEND_TIME),
        fallback_recipients=_normalize_recipient_items(
            recipients.get("fallback_recipients")
        ),
    )


async def load_inspection_trend_alert_config(
    db: AsyncSession,
) -> InspectionTrendAlertConfig:
    """读取成品检验趋势异常提醒配置；缺行时按当前线上行为返回默认值。"""
    model = await _get_setting_model(db, QUALITY_NOTIFICATION_INSPECTION_TREND_ALERT)
    if model is None:
        return InspectionTrendAlertConfig(
            lines=_default_inspection_recipients()["lines"]
        )
    recipients = model.recipients if isinstance(model.recipients, dict) else {}
    stored_lines = recipients.get("lines") or {}
    lines: dict[str, dict[str, Any]] = {}
    for entity_code, _label in FINISHED_DASHBOARD_LINE_CATALOG:
        stored = stored_lines.get(entity_code)
        stored = stored if isinstance(stored, dict) else {}
        lines[entity_code] = {
            "enabled": bool(stored.get("enabled", True)),
            "recipients": _normalize_recipient_items(stored.get("recipients")),
        }
    return InspectionTrendAlertConfig(is_enabled=bool(model.is_enabled), lines=lines)
