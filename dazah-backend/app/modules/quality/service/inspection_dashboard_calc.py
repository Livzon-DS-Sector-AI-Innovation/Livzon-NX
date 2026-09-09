"""Inspection Feishu pages service - dashboard calculation and alert logic.

Statistics, alert detection, notification sending, and dashboard data
assembly for the finished product trend dashboard.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid as uuid_module
from datetime import UTC, datetime
from statistics import StatisticsError, fmean, pstdev
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.core.exceptions import AppException
from app.core.jobs import submit_job
from app.modules.quality.feishu_notification import (
    send_user_card_with_message_id,
    upload_image,
)
from app.modules.quality.models.contacts import DepartmentContact
from app.modules.quality.models.finished_trend_ai_analysis import (
    FinishedTrendAIAnalysis,
)
from app.modules.quality.models.finished_trend_alert_notification import (
    FinishedTrendAlertNotification,
)
from app.modules.quality.models.oot_limit import OotLimitItem, OotLimitProduct
from app.modules.quality.schemas.inspection_dashboard import (
    InspectionDashboardAlert,
    InspectionDashboardChart,
    InspectionDashboardChartSummary,
    InspectionDashboardData,
    InspectionDashboardPoint,
    InspectionDashboardSpecLine,
    InspectionDashboardSummary,
    InspectionDashboardTrendAI,
    InspectionDashboardTrendAIOutlook,
    InspectionDashboardTrendAISignal,
    InspectionDashboardTrendAnomaly,
)
from app.modules.quality.service.inspection_dashboard_config import (
    FINISHED_DASHBOARD_BATCH_FIELD,
    FINISHED_DASHBOARD_PRODUCT_DEPARTMENT_ENTITY_CODE,
    FINISHED_DASHBOARD_RECIPIENT_OVERRIDES,
)
from app.modules.quality.service.inspection_helpers import (
    _field,
    _normalize,
    _search_entity_records_with_fallback,
)
from app.modules.quality.service.quality_feishu_pages import (
    _resolve_runtime_entity,
    _search_entity_records,
)
from app.modules.quality.service.quality_notification_settings import (
    load_inspection_trend_alert_config,
)
from app.modules.quality.service.trend_ai_analysis import run_trend_ai_analysis
from app.modules.quality.service.trend_anomaly_rules import detect_trend_anomalies
from app.modules.quality.service.trend_chart_render import render_trend_chart_png

logger = logging.getLogger(__name__)


def _parse_numeric_metric(value: Any) -> float | None:
    normalized = _normalize(value)
    if not normalized:
        return None
    cleaned = (
        normalized.replace("％", "%")
        .replace("，", ",")
        .replace("。", ".")
        .replace("≤", "")
        .replace("≥", "")
        .replace("<", "")
        .replace(">", "")
        .replace("ppm", "")
        .replace("PPM", "")
        .replace("%", "")
        .replace(",", "")
        .replace(" ", "")
    )
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _build_spec_lines(metric_config: dict[str, Any]) -> list[dict[str, float | str]]:
    return [
        {"label": str(item["label"]), "value": float(item["value"])}
        for item in metric_config["spec_lines"]
    ]


def _build_alert_spec_lines(
    metric_config: dict[str, Any],
) -> list[dict[str, float | str]]:
    return [
        {"label": str(item["label"]), "value": float(item["value"])}
        for item in metric_config.get("alert_spec_lines", [])
    ]


def _normalize_oot_item_name(value: str | None) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip()


def _split_limit_range_parts(limit_value: str) -> list[str]:
    normalized = str(limit_value or "").strip()
    if not normalized:
        return []
    normalized = normalized.replace("~", "～")
    if "～" in normalized:
        return [part.strip() for part in normalized.split("～") if part.strip()]
    parts = re.split(r"(?<=\d)\s*-\s*(?=\d)", normalized)
    return [part.strip() for part in parts if part.strip()]


def _parse_limit_spec_lines(
    limit_value: str | None,
    *,
    label_prefix: str,
) -> list[dict[str, float | str]]:
    normalized = str(limit_value or "").strip()
    if not normalized:
        return []

    compact = normalized.replace(" ", "")
    if any(token in compact for token in ("≤", "<=", "<")):
        value = _parse_numeric_metric(normalized)
        if value is None:
            return []
        return [{"label": f"{label_prefix}上限", "value": float(value)}]

    if any(token in compact for token in ("≥", ">=", ">")):
        value = _parse_numeric_metric(normalized)
        if value is None:
            return []
        return [{"label": f"{label_prefix}下限", "value": float(value)}]

    parts = _split_limit_range_parts(normalized)
    if len(parts) >= 2:
        lower_value = _parse_numeric_metric(parts[0])
        upper_value = _parse_numeric_metric(parts[1])
        lines: list[dict[str, float | str]] = []
        if lower_value is not None:
            lines.append({"label": f"{label_prefix}下限", "value": float(lower_value)})
        if upper_value is not None:
            lines.append({"label": f"{label_prefix}上限", "value": float(upper_value)})
        return lines

    return []


def _merge_spec_lines(
    base_lines: list[dict[str, float | str]],
    extra_lines: list[dict[str, float | str]],
) -> list[dict[str, float | str]]:
    merged: list[dict[str, float | str]] = []
    seen: set[tuple[str, float]] = set()
    for item in [*base_lines, *extra_lines]:
        label = str(item["label"])
        value = float(item["value"])
        key = (label, value)
        if key in seen:
            continue
        merged.append({"label": label, "value": value})
        seen.add(key)
    return merged


def _is_value_out_of_spec_lines(
    value: float,
    spec_lines: list[dict[str, float | str]],
) -> bool:
    for item in spec_lines:
        label = str(item.get("label") or "")
        line_value = float(item["value"])
        if "下限" in label and value < line_value:
            return True
        if "上限" in label and value > line_value:
            return True
    return False


async def _get_oot_limit_items_by_product_code(
    db: AsyncSession,
    product_code: str | None,
) -> dict[str, OotLimitItem]:
    if not product_code:
        return {}

    product_result = await db.execute(
        select(OotLimitProduct).where(
            OotLimitProduct.product_code == product_code,
            OotLimitProduct.is_deleted.is_(False),
        )
    )
    product = product_result.scalars().first()
    if product is None:
        return {}

    item_result = await db.execute(
        select(OotLimitItem).where(
            OotLimitItem.product_id == product.id,
            OotLimitItem.is_deleted.is_(False),
        )
    )
    return {
        _normalize_oot_item_name(item.item_name): item
        for item in item_result.scalars().all()
    }


def _extract_batch_product_code(batch_no: str | None) -> str | None:
    normalized = _normalize(batch_no)
    if not normalized:
        return None
    raw = normalized.strip()
    if not raw:
        return None
    raw_upper = raw.upper()

    # 霉酚酸批号按业务口径统一映射到产品代码 MC。
    if re.search(r"(?:^|[-_/ ])(?:US)?MC(?:[-_/ ]|$)", raw_upper):
        return "MC"

    for delimiter in ("-", "_", "/", " "):
        if delimiter in raw:
            prefix = raw.split(delimiter, 1)[0].strip()
            if prefix:
                return prefix.upper()
    alpha_match = re.match(r"([A-Za-z]+)", raw)
    if alpha_match:
        return alpha_match.group(1).upper()
    digit_match = re.search(r"\d", raw)
    if digit_match and digit_match.start() > 0:
        prefix = raw[: digit_match.start()].strip()
        if prefix:
            return prefix.upper()
    return raw.upper()


def _compute_metric_statistics(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {
            "sample_count": 0,
            "mean": None,
            "std_dev": None,
            "upper_control_limit": None,
            "lower_control_limit": None,
        }
    mean_value = fmean(values)
    if len(values) < 2:
        return {
            "sample_count": len(values),
            "mean": mean_value,
            "std_dev": None,
            "upper_control_limit": None,
            "lower_control_limit": None,
        }
    try:
        std_dev = pstdev(values)
    except StatisticsError:
        std_dev = 0.0
    return {
        "sample_count": len(values),
        "mean": mean_value,
        "std_dev": std_dev,
        "upper_control_limit": mean_value + (3 * std_dev),
        "lower_control_limit": mean_value - (3 * std_dev),
    }


async def _get_product_department_extraction_head(
    db: AsyncSession,
    product_code: str,
) -> str | None:
    _, entity = await _resolve_runtime_entity(
        db,
        FINISHED_DASHBOARD_PRODUCT_DEPARTMENT_ENTITY_CODE,
        direction="pull",
    )
    records = await _search_entity_records(
        db,
        FINISHED_DASHBOARD_PRODUCT_DEPARTMENT_ENTITY_CODE,
        field_names=["产品代码", "涉及提炼部门负责人"],
    )
    for record in records:
        fields = record.get("fields") or {}
        record_product_code = _normalize(_field(fields, entity, "产品代码"))
        if (record_product_code or "").upper() != product_code.upper():
            continue
        return _normalize(_field(fields, entity, "涉及提炼部门负责人"))
    return None


async def _resolve_recipient_by_name(
    db: AsyncSession,
    *,
    name: str,
    open_id: str | None = None,
    email: str | None = None,
) -> dict[str, str | None]:
    resolved_open_id = (open_id or "").strip() or None
    resolved_email = (email or "").strip() or None

    result = await db.execute(
        select(DepartmentContact).where(
            DepartmentContact.name == name,
            DepartmentContact.is_deleted.is_(False),
        )
    )
    contact = result.scalars().first()
    if contact:
        resolved_open_id = resolved_open_id or (contact.open_id or "").strip() or None
        resolved_email = (
            resolved_email or (contact.enterprise_email or "").strip() or None
        )

    result = await db.execute(
        select(DepartmentContact).where(
            DepartmentContact.department_head_name == name,
            DepartmentContact.is_deleted.is_(False),
        )
    )
    head_contact = result.scalars().first()
    if head_contact:
        resolved_open_id = (
            resolved_open_id
            or (head_contact.department_head_open_id or "").strip()
            or None
        )
        resolved_email = (
            resolved_email
            or (head_contact.department_head_enterprise_email or "").strip()
            or None
        )

    from app.modules.quality.service.department_contacts import (
        get_department_contact_list_from_feishu,
    )

    feishu_contacts = await get_department_contact_list_from_feishu(
        db,
        page=1,
        page_size=500,
    )
    for item in feishu_contacts.get("items", []):
        item_name = str(item.get("name") or "").strip()
        item_head_name = str(item.get("department_head_name") or "").strip()
        if item_name == name:
            resolved_open_id = (
                resolved_open_id or str(item.get("open_id") or "").strip() or None
            )
            resolved_email = (
                resolved_email
                or str(item.get("enterprise_email") or "").strip()
                or None
            )
            break
        if item_head_name == name:
            resolved_open_id = (
                resolved_open_id
                or str(item.get("department_head_open_id") or "").strip()
                or None
            )
            resolved_email = (
                resolved_email
                or str(item.get("department_head_enterprise_email") or "").strip()
                or None
            )
            break

    return {
        "name": name,
        "open_id": resolved_open_id,
        "email": resolved_email,
    }


async def _resolve_dashboard_recipients(
    db: AsyncSession,
    *,
    entity_code: str,
    batch_no: str,
    line_config: dict[str, Any] | None = None,
) -> list[dict[str, str | None]]:
    # 通知设置中该产品线配置了接收人时优先生效
    configured: list[Any] = (
        line_config.get("recipients") if isinstance(line_config, dict) else None
    ) or []
    if configured:
        recipients: list[dict[str, str | None]] = []
        for item in configured:
            recipients.append(
                await _resolve_recipient_by_name(
                    db,
                    name=str(item.get("name") or ""),
                    open_id=item.get("open_id"),
                    email=item.get("email"),
                )
            )
        return recipients

    override_configs = FINISHED_DASHBOARD_RECIPIENT_OVERRIDES.get(entity_code)
    if override_configs:
        recipients = []
        for item in override_configs:
            recipients.append(
                await _resolve_recipient_by_name(
                    db,
                    name=str(item["name"]),
                    open_id=item.get("open_id"),
                    email=item.get("email"),
                )
            )
        return recipients

    recipient = await _resolve_refining_recipient(db, batch_no)
    if recipient is None:
        return []
    return [recipient]


def _join_recipient_field(
    recipients: list[dict[str, str | None]],
    field_name: str,
    *,
    delimiter: str,
) -> str | None:
    values = [
        str(item.get(field_name) or "").strip()
        for item in recipients
        if str(item.get(field_name) or "").strip()
    ]
    if not values:
        return None
    return delimiter.join(dict.fromkeys(values))


async def _send_dashboard_alert_notifications(
    *,
    db: AsyncSession,
    sender_user_open_id: str | None,
    source_label: str,
    recipients: list[dict[str, str | None]],
    batch_no: str,
    metric_label: str,
    actual_value: float,
    upper_control_limit: float | None,
    lower_control_limit: float | None,
    spec_lines: list[dict[str, float | str]],
) -> dict[str, str | None]:
    sent_message_ids: list[str] = []
    failed_recipients: list[str] = []

    for recipient in recipients:
        name = str(recipient.get("name") or "").strip() or "未知对象"
        send_result = await _send_mpa_alert_notification(
            db=db,
            sender_user_open_id=sender_user_open_id,
            source_label=source_label,
            open_id=recipient.get("open_id"),
            email=recipient.get("email"),
            batch_no=batch_no,
            metric_label=metric_label,
            actual_value=actual_value,
            upper_control_limit=upper_control_limit,
            lower_control_limit=lower_control_limit,
            spec_lines=spec_lines,
        )
        if send_result["status"] == "sent" and send_result.get("message_id"):
            sent_message_ids.append(str(send_result["message_id"]))
            continue
        failed_recipients.append(name)

    if sent_message_ids and not failed_recipients:
        return {
            "status": "sent",
            "message_id": ",".join(sent_message_ids),
            "error": None,
        }
    if sent_message_ids and failed_recipients:
        return {
            "status": "partial",
            "message_id": ",".join(sent_message_ids),
            "error": f"以下通知对象发送失败：{'、'.join(failed_recipients)}",
        }
    return {
        "status": "failed",
        "message_id": None,
        "error": f"以下通知对象发送失败：{'、'.join(failed_recipients)}"
        if failed_recipients
        else "飞书通知发送失败",
    }


async def _resolve_refining_recipient(
    db: AsyncSession,
    batch_no: str,
) -> dict[str, str | None] | None:
    product_code = _extract_batch_product_code(batch_no)
    if not product_code:
        return None

    extraction_head = await _get_product_department_extraction_head(db, product_code)
    if not extraction_head:
        return None

    recipient: dict[str, str | None] | None = None

    result = await db.execute(
        select(DepartmentContact).where(
            DepartmentContact.name == extraction_head,
            DepartmentContact.is_deleted.is_(False),
        )
    )
    contact = result.scalars().first()
    if contact and (
        (contact.open_id or "").strip() or (contact.enterprise_email or "").strip()
    ):
        recipient = {
            "product_code": product_code,
            "name": extraction_head,
            "open_id": (contact.open_id or "").strip(),
            "email": (contact.enterprise_email or "").strip() or None,
        }
    else:
        result = await db.execute(
            select(DepartmentContact).where(
                DepartmentContact.department_head_name == extraction_head,
                DepartmentContact.is_deleted.is_(False),
            )
        )
        head_contact = result.scalars().first()
        if head_contact:
            recipient = {
                "product_code": product_code,
                "name": extraction_head,
                "open_id": (head_contact.department_head_open_id or "").strip() or None,
                "email": (head_contact.department_head_enterprise_email or "").strip()
                or None,
            }

    from app.modules.quality.service.department_contacts import (
        get_department_contact_list_from_feishu,
    )

    feishu_contacts = await get_department_contact_list_from_feishu(
        db,
        page=1,
        page_size=500,
    )
    for item in feishu_contacts.get("items", []):
        if str(item.get("name") or "").strip() == extraction_head:
            feishu_open_id = str(item.get("open_id") or "").strip() or None
            feishu_email = str(item.get("enterprise_email") or "").strip() or None
            if recipient is None:
                recipient = {
                    "product_code": product_code,
                    "name": extraction_head,
                    "open_id": feishu_open_id,
                    "email": feishu_email,
                }
            else:
                recipient["open_id"] = recipient.get("open_id") or feishu_open_id
                recipient["email"] = recipient.get("email") or feishu_email
            break
        if str(item.get("department_head_name") or "").strip() == extraction_head:
            feishu_open_id = (
                str(item.get("department_head_open_id") or "").strip() or None
            )
            feishu_email = (
                str(item.get("department_head_enterprise_email") or "").strip() or None
            )
            if recipient is None:
                recipient = {
                    "product_code": product_code,
                    "name": extraction_head,
                    "open_id": feishu_open_id,
                    "email": feishu_email,
                }
            else:
                recipient["open_id"] = recipient.get("open_id") or feishu_open_id
                recipient["email"] = recipient.get("email") or feishu_email
            break

    if recipient:
        return recipient

    return {
        "product_code": product_code,
        "name": extraction_head,
        "open_id": None,
        "email": None,
    }


async def _send_mpa_alert_notification(
    *,
    db: AsyncSession,
    sender_user_open_id: str | None = None,
    source_label: str = "霉酚酸趋势",
    open_id: str | None,
    email: str | None,
    batch_no: str,
    metric_label: str,
    actual_value: float,
    upper_control_limit: float | None,
    lower_control_limit: float | None,
    spec_lines: list[dict[str, float | str]] | None = None,
) -> dict[str, str | None]:
    spec_line_text = (
        " / ".join(
            f"{str(item['label'])} {float(item['value']):g}"
            for item in (spec_lines or [])
        )
        or "-"
    )
    content = (
        f"**产品系列：**{source_label}\n"
        f"**批号：**{batch_no}\n"
        f"**异常指标：**{metric_label}\n"
        f"**实际值：**{actual_value}\n"
        "**控制边界：**"
        f"{lower_control_limit if lower_control_limit is not None else '-'}"
        f" ~ {upper_control_limit if upper_control_limit is not None else '-'}\n"
        f"**限度线：**{spec_line_text}\n"
        f"请进入质量检验页面查看趋势仪表盘明细。"
    )
    message_id = None
    if (open_id or "").strip():
        message_id = await send_user_card_with_message_id(
            open_id=str(open_id),
            title=f"{source_label}趋势异常提醒",
            content=content,
        )
    if not message_id and (email or "").strip():
        message_id = await send_user_card_with_message_id(
            open_id=str(email),
            title=f"{source_label}趋势异常提醒",
            content=content,
            receive_id_type="email",
        )
    if not message_id:
        return {
            "status": "failed",
            "message_id": None,
            "error": "飞书通知发送失败",
        }
    return {
        "status": "sent",
        "message_id": message_id,
        "error": None,
    }


async def _get_existing_dashboard_notification(
    db: AsyncSession,
    entity_code: str,
    batch_no: str,
    metric_key: str,
) -> FinishedTrendAlertNotification | None:
    result = await db.execute(
        select(FinishedTrendAlertNotification).where(
            FinishedTrendAlertNotification.entity_code == entity_code,
            FinishedTrendAlertNotification.batch_no == batch_no,
            FinishedTrendAlertNotification.metric_key == metric_key,
            FinishedTrendAlertNotification.is_deleted.is_(False),
        )
    )
    return result.scalars().first()


async def _create_dashboard_notification(
    db: AsyncSession,
    *,
    entity_code: str,
    batch_no: str,
    metric_key: str,
    metric_label: str,
    actual_value: float,
    upper_control_limit: float | None,
    lower_control_limit: float | None,
    recipient_name: str | None = None,
    recipient_open_id: str | None = None,
    notification_status: str,
    feishu_message_id: str | None = None,
    notified_at: datetime | None = None,
) -> FinishedTrendAlertNotification:
    record = FinishedTrendAlertNotification(
        entity_code=entity_code,
        batch_no=batch_no,
        metric_key=metric_key,
        metric_label=metric_label,
        actual_value=actual_value,
        upper_control_limit=upper_control_limit,
        lower_control_limit=lower_control_limit,
        recipient_name=recipient_name,
        recipient_open_id=recipient_open_id,
        notification_status=notification_status,
        feishu_message_id=feishu_message_id,
        notified_at=notified_at,
    )
    db.add(record)
    try:
        await db.commit()
        result = await db.execute(
            select(FinishedTrendAlertNotification).where(
                FinishedTrendAlertNotification.id == record.id
            )
        )
        return result.scalar_one()
    except IntegrityError:
        # Concurrent dashboard requests can race on the unique key.
        await db.rollback()
        existing = await _get_existing_dashboard_notification(
            db, entity_code, batch_no, metric_key
        )
        if existing is not None:
            return existing
        raise


def _serialize_dashboard_alert(
    *,
    notification: FinishedTrendAlertNotification,
    mean: float | None,
    std_dev: float | None,
    spec_lines: list[dict[str, float | str]],
    notification_deduplicated: bool,
    notification_error: str | None = None,
) -> dict[str, Any]:
    return InspectionDashboardAlert(
        entity_code=notification.entity_code,
        batch_no=notification.batch_no,
        metric_key=notification.metric_key,
        metric_label=notification.metric_label,
        actual_value=notification.actual_value,
        mean=mean,
        std_dev=std_dev,
        upper_control_limit=notification.upper_control_limit,
        lower_control_limit=notification.lower_control_limit,
        spec_lines=[
            InspectionDashboardSpecLine.model_validate(item) for item in spec_lines
        ],
        recipient_name=notification.recipient_name,
        recipient_open_id=notification.recipient_open_id,
        notification_status=notification.notification_status,
        notification_sent=notification.notification_status in {"sent", "partial"},
        notification_deduplicated=notification_deduplicated,
        notification_error=notification_error,
        feishu_message_id=notification.feishu_message_id,
        notified_at=notification.notified_at.isoformat()
        if notification.notified_at
        else None,
    ).model_dump(mode="json")


async def _retry_incomplete_dashboard_notification(
    db: AsyncSession,
    *,
    sender_user_open_id: str | None = None,
    source_label: str,
    notification: FinishedTrendAlertNotification,
    metric_label: str,
    actual_value: float,
    upper_control_limit: float | None,
    lower_control_limit: float | None,
    mean: float | None,
    std_dev: float | None,
    spec_lines: list[dict[str, float | str]],
    line_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    recipients = await _resolve_dashboard_recipients(
        db,
        entity_code=notification.entity_code,
        batch_no=notification.batch_no,
        line_config=line_config,
    )
    if not recipients:
        return _serialize_dashboard_alert(
            notification=notification,
            mean=mean,
            std_dev=std_dev,
            spec_lines=spec_lines,
            notification_deduplicated=True,
            notification_error="未找到通知对象",
        )

    notification.metric_label = metric_label
    notification.actual_value = actual_value
    notification.upper_control_limit = upper_control_limit
    notification.lower_control_limit = lower_control_limit
    notification.recipient_name = _join_recipient_field(
        recipients, "name", delimiter="、"
    )
    notification.recipient_open_id = _join_recipient_field(
        recipients, "open_id", delimiter=","
    )

    if not any(
        recipient.get("open_id") or recipient.get("email") for recipient in recipients
    ):
        notification.notification_status = "missing_open_id"
        notification.feishu_message_id = None
        notification.notified_at = None
        await db.commit()
        result = await db.execute(
            select(FinishedTrendAlertNotification).where(
                FinishedTrendAlertNotification.id == notification.id
            )
        )
        notification = result.scalar_one()
        return _serialize_dashboard_alert(
            notification=notification,
            mean=mean,
            std_dev=std_dev,
            spec_lines=spec_lines,
            notification_deduplicated=False,
            notification_error="未找到通知对象 open_id 或邮箱",
        )

    send_result = await _send_dashboard_alert_notifications(
        db=db,
        sender_user_open_id=sender_user_open_id,
        source_label=source_label,
        recipients=recipients,
        batch_no=notification.batch_no,
        metric_label=metric_label,
        actual_value=actual_value,
        upper_control_limit=upper_control_limit,
        lower_control_limit=lower_control_limit,
        spec_lines=spec_lines,
    )
    notification.notification_status = str(send_result["status"])
    notification.feishu_message_id = send_result.get("message_id")
    notification.notified_at = (
        datetime.now(UTC) if send_result["status"] in {"sent", "partial"} else None
    )
    await db.commit()
    result = await db.execute(
        select(FinishedTrendAlertNotification).where(
            FinishedTrendAlertNotification.id == notification.id
        )
    )
    notification = result.scalar_one()
    return _serialize_dashboard_alert(
        notification=notification,
        mean=mean,
        std_dev=std_dev,
        spec_lines=spec_lines,
        notification_deduplicated=False,
        notification_error=send_result.get("error"),
    )


def _build_paused_dashboard_alert(
    *,
    entity_code: str,
    batch_no: str,
    metric_key: str,
    metric_label: str,
    actual_value: float,
    mean: float | None,
    std_dev: float | None,
    upper_control_limit: float | None,
    lower_control_limit: float | None,
    spec_lines: list[dict[str, float | str]],
    error: str,
) -> dict[str, Any]:
    """通知停用（全局或该产品线）时的告警展示：不发送、不落通知记录。"""
    return InspectionDashboardAlert(
        entity_code=entity_code,
        batch_no=batch_no,
        metric_key=metric_key,
        metric_label=metric_label,
        actual_value=actual_value,
        mean=mean,
        std_dev=std_dev,
        upper_control_limit=upper_control_limit,
        lower_control_limit=lower_control_limit,
        spec_lines=[
            InspectionDashboardSpecLine.model_validate(item) for item in spec_lines
        ],
        recipient_name=None,
        recipient_open_id=None,
        notification_status="paused",
        notification_sent=False,
        notification_deduplicated=False,
        notification_error=error,
        feishu_message_id=None,
        notified_at=None,
    ).model_dump(mode="json")


async def _materialize_dashboard_alert(
    db: AsyncSession,
    *,
    sender_user_open_id: str | None = None,
    source_label: str,
    entity_code: str,
    batch_no: str,
    metric_key: str,
    metric_label: str,
    actual_value: float,
    mean: float | None,
    std_dev: float | None,
    upper_control_limit: float | None,
    lower_control_limit: float | None,
    spec_lines: list[dict[str, float | str]],
) -> dict[str, Any]:
    trend_config = await load_inspection_trend_alert_config(db)
    line_config = trend_config.lines.get(entity_code)
    notifications_paused = not trend_config.is_enabled
    line_paused = bool(line_config and not line_config.get("enabled", True))

    existing = await _get_existing_dashboard_notification(
        db,
        entity_code,
        batch_no,
        metric_key,
    )
    if existing:
        if notifications_paused or line_paused:
            # 停用期间不补发（不重试），保持既有记录的展示状态
            return _serialize_dashboard_alert(
                notification=existing,
                mean=mean,
                std_dev=std_dev,
                spec_lines=spec_lines,
                notification_deduplicated=True,
            )
        if existing.notification_status in {"unmapped", "missing_open_id"}:
            return await _retry_incomplete_dashboard_notification(
                db,
                sender_user_open_id=sender_user_open_id,
                source_label=source_label,
                notification=existing,
                metric_label=metric_label,
                actual_value=actual_value,
                upper_control_limit=upper_control_limit,
                lower_control_limit=lower_control_limit,
                mean=mean,
                std_dev=std_dev,
                spec_lines=spec_lines,
                line_config=line_config,
            )
        return _serialize_dashboard_alert(
            notification=existing,
            mean=mean,
            std_dev=std_dev,
            spec_lines=spec_lines,
            notification_deduplicated=True,
        )

    if notifications_paused or line_paused:
        error = (
            "该产品线趋势异常提醒已停用"
            if line_paused
            else "趋势异常提醒通知已停用"
        )
        return _build_paused_dashboard_alert(
            entity_code=entity_code,
            batch_no=batch_no,
            metric_key=metric_key,
            metric_label=metric_label,
            actual_value=actual_value,
            mean=mean,
            std_dev=std_dev,
            upper_control_limit=upper_control_limit,
            lower_control_limit=lower_control_limit,
            spec_lines=spec_lines,
            error=error,
        )

    recipients = await _resolve_dashboard_recipients(
        db,
        entity_code=entity_code,
        batch_no=batch_no,
        line_config=line_config,
    )
    if not recipients:
        record = await _create_dashboard_notification(
            db,
            entity_code=entity_code,
            batch_no=batch_no,
            metric_key=metric_key,
            metric_label=metric_label,
            actual_value=actual_value,
            upper_control_limit=upper_control_limit,
            lower_control_limit=lower_control_limit,
            notification_status="unmapped",
        )
        return _serialize_dashboard_alert(
            notification=record,
            mean=mean,
            std_dev=std_dev,
            spec_lines=spec_lines,
            notification_deduplicated=False,
            notification_error="未找到通知对象",
        )

    recipient_name = _join_recipient_field(recipients, "name", delimiter="、")
    recipient_open_id = _join_recipient_field(recipients, "open_id", delimiter=",")

    if not any(
        recipient.get("open_id") or recipient.get("email") for recipient in recipients
    ):
        record = await _create_dashboard_notification(
            db,
            entity_code=entity_code,
            batch_no=batch_no,
            metric_key=metric_key,
            metric_label=metric_label,
            actual_value=actual_value,
            upper_control_limit=upper_control_limit,
            lower_control_limit=lower_control_limit,
            recipient_name=recipient_name,
            recipient_open_id=recipient_open_id,
            notification_status="missing_open_id",
        )
        return _serialize_dashboard_alert(
            notification=record,
            mean=mean,
            std_dev=std_dev,
            spec_lines=spec_lines,
            notification_deduplicated=False,
            notification_error="未找到通知对象 open_id 或邮箱",
        )

    send_result = await _send_dashboard_alert_notifications(
        db=db,
        sender_user_open_id=sender_user_open_id,
        source_label=source_label,
        recipients=recipients,
        batch_no=batch_no,
        metric_label=metric_label,
        actual_value=actual_value,
        upper_control_limit=upper_control_limit,
        lower_control_limit=lower_control_limit,
        spec_lines=spec_lines,
    )
    notified_at = (
        datetime.now(UTC) if send_result["status"] in {"sent", "partial"} else None
    )
    record = await _create_dashboard_notification(
        db,
        entity_code=entity_code,
        batch_no=batch_no,
        metric_key=metric_key,
        metric_label=metric_label,
        actual_value=actual_value,
        upper_control_limit=upper_control_limit,
        lower_control_limit=lower_control_limit,
        recipient_name=recipient_name,
        recipient_open_id=recipient_open_id,
        notification_status=str(send_result["status"]),
        feishu_message_id=send_result.get("message_id"),
        notified_at=notified_at,
    )
    return _serialize_dashboard_alert(
        notification=record,
        mean=mean,
        std_dev=std_dev,
        spec_lines=spec_lines,
        notification_deduplicated=False,
        notification_error=send_result.get("error"),
    )


# ─── 趋势规则 + AI 分析（编排：确定性判据先算，AI/渲染/推送后台化） ───

# 趋势 AI 后台任务整单超时保护（渲染 + 上传 + 一次 LLM + 推送），秒
_TREND_AI_TOTAL_TIMEOUT = 240
_TREND_AI_TERMINAL_STATUSES = {"sent", "partial", "failed", "unmapped", "ai_failed"}
# AI 按月固定：整体分析行的规则类型与周期键（trend_end_batch 孈YYYY-MM）
TREND_OVERALL_RULE = "monthly_overall"


def _trend_period() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


def _build_trend_deep_link(
    frontend_group: str | None,
    entity_code: str,
    *,
    highlight_batch: str | None = None,
) -> str | None:
    if not frontend_group:
        return None
    base_url = get_settings().FRONTEND_URL.rstrip("/")
    link = f"{base_url}/quality/inspection/finished/{frontend_group}"
    params = [f"entity_code={entity_code}"]
    if highlight_batch:
        params.append(f"highlight_batch={highlight_batch}")
    return f"{link}?{'&'.join(params)}"


async def _get_existing_trend_ai(
    db: AsyncSession,
    *,
    entity_code: str,
    metric_key: str,
    rule_type: str,
    trend_end_batch: str,
) -> FinishedTrendAIAnalysis | None:
    result = await db.execute(
        select(FinishedTrendAIAnalysis).where(
            FinishedTrendAIAnalysis.entity_code == entity_code,
            FinishedTrendAIAnalysis.metric_key == metric_key,
            FinishedTrendAIAnalysis.rule_type == rule_type,
            FinishedTrendAIAnalysis.trend_end_batch == trend_end_batch,
            FinishedTrendAIAnalysis.is_deleted.is_(False),
        )
    )
    return result.scalars().first()


def _trend_ai_row_to_chart_model(
    rows: list[FinishedTrendAIAnalysis],
) -> InspectionDashboardTrendAI | None:
    """把一个指标的已完成 AI 记录合并为展示模型（供前端高亮 + 折叠区）。"""
    completed = [row for row in rows if isinstance(row.ai_summary, dict)]
    if not completed:
        return None
    signals: list[dict[str, Any]] = []
    highlights: set[str] = set()
    summaries: list[str] = []
    readings: list[str] = []
    recommendations: list[str] = []
    worst_direction = "flat"
    worst_batches: int | None = None
    worst_risk = ""
    confidence_order = {"low": 0, "medium": 1, "high": 2}
    best_confidence = "low"
    for row in completed:
        summary = row.ai_summary or {}
        highlights.update(str(b) for b in (row.affected_batches or []))
        highlights.update(
            str(s.get("batch_no"))
            for s in (summary.get("signals") or [])
            if s.get("batch_no")
        )
        for s in summary.get("signals") or []:
            if isinstance(s, dict):
                signals.append(s)
        if summary.get("summary"):
            summaries.append(str(summary["summary"]))
        if summary.get("trend_reading"):
            readings.append(str(summary["trend_reading"]))
        if summary.get("recommendation"):
            recommendations.append(str(summary["recommendation"]))
        outlook = summary.get("outlook") or {}
        if isinstance(outlook, dict):
            if outlook.get("direction") in {"up", "down"}:
                worst_direction = str(outlook["direction"])
            btl = outlook.get("batches_to_limit")
            if isinstance(btl, int):
                worst_batches = (
                    btl if worst_batches is None else min(worst_batches, btl)
                )
            if outlook.get("risk"):
                worst_risk = str(outlook["risk"])
        conf = str(summary.get("confidence") or "low")
        if confidence_order.get(conf, 0) > confidence_order.get(best_confidence, 0):
            best_confidence = conf
    return InspectionDashboardTrendAI(
        summary="；".join(summaries)[:120],
        trend_reading="；".join(readings)[:600],
        signals=[
            InspectionDashboardTrendAISignal.model_validate(s) for s in signals[:20]
        ],
        outlook=InspectionDashboardTrendAIOutlook(
            direction=worst_direction,
            batches_to_limit=worst_batches,
            risk=worst_risk[:160],
        ),
        recommendation="；".join(recommendations)[:200],
        confidence=best_confidence,
        highlight_batches=sorted(highlights),
        # 分析周期（YYYY-MM）与完成时间：AI 每月固定一次，期间结论不变
        period=completed[0].trend_end_batch,
        analyzed_at=(
            completed[0].updated_at.isoformat() if completed[0].updated_at else None
        ),
    )


def _build_trend_ai_markdown(
    *,
    source_label: str,
    metric_label: str,
    anomaly: FinishedTrendAIAnalysis,
) -> str:
    lines = [
        f"**产品系列：**{source_label}",
        f"**检测指标：**{metric_label}",
        f"**趋势判据：**{anomaly.description or anomaly.rule_type}",
        f"**触发区间：**{anomaly.trend_start_batch or '-'} ~ {anomaly.trend_end_batch}",
    ]
    summary = anomaly.ai_summary or {}
    if summary.get("summary"):
        lines.append(f"**AI 研判：**{summary['summary']}")
    outlook = summary.get("outlook") or {}
    btl = outlook.get("batches_to_limit") if isinstance(outlook, dict) else None
    if btl is not None:
        lines.append(f"**趋势外推：**按当前方向预计约 {btl} 批后逼近限度线")
    if summary.get("recommendation"):
        lines.append(f"**建议：**{summary['recommendation']}")
    lines.append("点开下方按钮查看完整趋势仪表盘与 AI 分析。")
    return "\n".join(lines)


async def _send_trend_ai_card(
    db: AsyncSession,
    *,
    sender_user_open_id: str | None,
    anomaly: FinishedTrendAIAnalysis,
    payload: dict[str, Any],
    image_key: str | None,
) -> dict[str, str | None]:
    line_config = (await load_inspection_trend_alert_config(db)).lines.get(
        anomaly.entity_code
    )
    recipients = await _resolve_dashboard_recipients(
        db,
        entity_code=anomaly.entity_code,
        batch_no=anomaly.trend_end_batch,
        line_config=line_config,
    )
    if not recipients:
        return {"status": "unmapped", "message_id": None, "error": "未找到通知对象"}
    if not any(
        r.get("open_id") or r.get("email") for r in recipients
    ):
        return {
            "status": "missing_open_id",
            "message_id": None,
            "error": "通知对象缺少 open_id/邮箱",
        }

    content = _build_trend_ai_markdown(
        source_label=payload.get("source_label") or anomaly.source_label or "",
        metric_label=anomaly.metric_label,
        anomaly=anomaly,
    )
    elements: list[dict[str, Any]] = []
    if image_key:
        elements.append(
            {"tag": "img", "image_key": image_key, "alt": {"content": "趋势图"}}
        )
    deep_link = _build_trend_deep_link(
        payload.get("frontend_group"),
        anomaly.entity_code,
        highlight_batch=anomaly.trend_end_batch,
    )
    if deep_link:
        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "查看趋势与 AI 分析"},
                        "type": "primary",
                        "url": deep_link,
                    }
                ],
            }
        )

    sent_ids: list[str] = []
    failed_names: list[str] = []
    title = f"{payload.get('source_label') or anomaly.source_label or ''}趋势异常提醒"
    for recipient in recipients:
        name = str(recipient.get("name") or "").strip() or "未知对象"
        message_id = None
        if (recipient.get("open_id") or "").strip():
            message_id = await send_user_card_with_message_id(
                open_id=str(recipient["open_id"]),
                title=title,
                content=content,
                elements=elements or None,
            )
        if not message_id and (recipient.get("email") or "").strip():
            message_id = await send_user_card_with_message_id(
                open_id=str(recipient["email"]),
                title=title,
                content=content,
                elements=elements or None,
                receive_id_type="email",
            )
        if message_id:
            sent_ids.append(message_id)
        else:
            failed_names.append(name)

    if sent_ids and not failed_names:
        return {"status": "sent", "message_id": ",".join(sent_ids), "error": None}
    if sent_ids:
        return {
            "status": "partial",
            "message_id": ",".join(sent_ids),
            "error": f"以下通知对象发送失败：{'、'.join(failed_names)}",
        }
    return {
        "status": "failed",
        "message_id": None,
        "error": f"以下通知对象发送失败：{'、'.join(failed_names)}"
        if failed_names
        else "飞书通知发送失败",
    }


async def _run_trend_ai_job(
    *,
    analysis_id: uuid_module.UUID,
    sender_user_open_id: str | None,
) -> dict[str, str]:
    """后台任务：渲染趋势图 → 上传 → AI 解读 → 飞书推送 → 幂等回写。"""
    async with async_session_factory() as db:
        anomaly = await db.get(FinishedTrendAIAnalysis, analysis_id)
        if anomaly is None:
            return {"status": "skipped"}
        if anomaly.notification_status in _TREND_AI_TERMINAL_STATUSES:
            # 幂等保护：已终态记录不重复推送/计费
            return {"status": "already"}
        payload = anomaly.payload or {}
        try:
            await asyncio.wait_for(
                _execute_trend_ai_job(
                    db, anomaly, payload, sender_user_open_id
                ),
                timeout=_TREND_AI_TOTAL_TIMEOUT,
            )
            await db.commit()
            return {"status": anomaly.notification_status}
        except TimeoutError:
            anomaly.notification_status = "failed"
            anomaly.ai_summary = None
            await db.commit()
            return {"status": "timeout"}
        except Exception as exc:  # noqa: BLE001 —— job 边界兜底
            logger.exception("trend ai job %s failed", analysis_id)
            anomaly.notification_status = "failed"
            await db.commit()
            return {"status": "failed", "error": type(exc).__name__}


async def _execute_trend_ai_job(
    db: AsyncSession,
    anomaly: FinishedTrendAIAnalysis,
    payload: dict[str, Any],
    sender_user_open_id: str | None,
) -> None:
    # 1. AI 分析（无论是否推送都执行，供页面回看）；整体分析带上当月全部判据命中
    job_anomalies = list(payload.get("anomalies") or [])
    if not job_anomalies:
        job_anomalies = [
            {
                "rule_type": anomaly.rule_type,
                "severity": anomaly.severity,
                "description": anomaly.description,
                "evidence": anomaly.evidence or {},
                "trend_start_batch": anomaly.trend_start_batch,
                "trend_end_batch": anomaly.trend_end_batch,
            }
        ]
    ai_result = await run_trend_ai_analysis(
        source_label=str(payload.get("source_label") or anomaly.source_label or ""),
        metric_label=anomaly.metric_label,
        points=list(payload.get("points") or []),
        mean=payload.get("mean"),
        std_dev=payload.get("std_dev"),
        upper_control_limit=payload.get("upper_control_limit"),
        lower_control_limit=payload.get("lower_control_limit"),
        spec_lines=list(payload.get("spec_lines") or []),
        anomalies=job_anomalies,
    )
    if ai_result["status"] == "completed":
        summary = dict(ai_result["ai_summary"] or {})
        summary["affected_batches"] = list(anomaly.affected_batches or [])
        anomaly.ai_summary = summary
        anomaly.model_name = ai_result.get("model_name")
    else:
        anomaly.ai_summary = None
        anomaly.model_name = ai_result.get("model_name")

    # 2. 通知开关检查（全局 + 产品线）
    trend_config = await load_inspection_trend_alert_config(db)
    line_config = trend_config.lines.get(anomaly.entity_code)
    line_paused = bool(line_config and not line_config.get("enabled", True))
    if not trend_config.is_enabled or line_paused:
        anomaly.notification_status = "paused"
        return

    # 3. 渲染趋势图 + 上传（失败降级为无图仍发送）
    image_key: str | None = None
    png = render_trend_chart_png(
        metric_label=anomaly.metric_label,
        source_label=str(payload.get("source_label") or anomaly.source_label or ""),
        categories=list(payload.get("categories") or []),
        actual_series=list(payload.get("actual_series") or []),
        mean=payload.get("mean"),
        upper_control_limit=payload.get("upper_control_limit"),
        lower_control_limit=payload.get("lower_control_limit"),
        spec_lines=list(payload.get("spec_lines") or []),
        highlight_batches=list(anomaly.affected_batches or []),
    )
    if png:
        image_key = await upload_image(png, file_name="trend_anomaly.png")
    anomaly.feishu_image_key = image_key

    # 4. 推送
    send_result = await _send_trend_ai_card(
        db,
        sender_user_open_id=sender_user_open_id,
        anomaly=anomaly,
        payload=payload,
        image_key=image_key,
    )
    anomaly.notification_status = str(send_result["status"])
    anomaly.feishu_message_id = send_result.get("message_id")
    if send_result["status"] in {"sent", "partial"}:
        anomaly.notified_at = datetime.now(UTC)


async def _submit_trend_ai_job(
    anomaly: FinishedTrendAIAnalysis,
    *,
    sender_user_open_id: str | None,
) -> None:
    job_id = f"quality:trend-ai:{uuid_module.uuid4().hex[:12]}"
    anomaly.job_id = job_id
    await submit_job(
        _run_trend_ai_job,
        task_id=job_id,
        ttl=600,
        status_extra={"component": "quality.trend_ai"},
        analysis_id=anomaly.id,
        sender_user_open_id=sender_user_open_id,
    )


async def _process_metric_trend(
    db: AsyncSession,
    *,
    sender_user_open_id: str | None,
    source_label: str,
    entity_code: str,
    frontend_group: str | None,
    metric_key: str,
    metric_label: str,
    points: list[dict[str, Any]],
    mean: float | None,
    std_dev: float | None,
    upper_control_limit: float | None,
    lower_control_limit: float | None,
    spec_lines: list[dict[str, float | str]],
) -> tuple[list[dict[str, Any]], InspectionDashboardTrendAI | None, str]:
    """对单指标跑确定性趋势规则，并按「每月一次」维护整体 AI 分析。

    - 规则命中每次打开都实时重算（确定性、零成本），随响应返回供图表展示；
    - AI 结论按 (entity, metric, 月份) 固定：当月已有分析记录就直接用缓存，
      页面刷新不重复触发；当月首次出现命中、或上月 AI 失败时才提交后台任务；
    - 无任何命中则不做 AI。
    返回 (序列化的 trend_anomalies, 整体 trend_ai 展示模型, trend_ai_status)。
    """
    anomalies = detect_trend_anomalies(
        points,
        mean=mean,
        std_dev=std_dev,
        upper_control_limit=upper_control_limit,
        lower_control_limit=lower_control_limit,
        spec_lines=spec_lines,
    )
    serialized = [
        InspectionDashboardTrendAnomaly(
            rule_type=anomaly.rule_type,
            severity=anomaly.severity,
            start_batch=anomaly.start_batch,
            end_batch=anomaly.end_batch,
            description=anomaly.description,
            evidence=anomaly.evidence,
            affected_batches=list(anomaly.affected_batches),
        ).model_dump(mode="json")
        for anomaly in anomalies
    ]
    if not anomalies:
        return serialized, None, "none"

    period = _trend_period()
    snapshot = {
        "points": points,
        "categories": [str(p["batch_no"]) for p in points],
        "actual_series": [float(p["value"]) for p in points],
        "mean": mean,
        "std_dev": std_dev,
        "upper_control_limit": upper_control_limit,
        "lower_control_limit": lower_control_limit,
        "spec_lines": spec_lines,
        "source_label": source_label,
        "frontend_group": frontend_group,
        # 整体分析：把当月全部判据命中一起交给 AI
        "anomalies": serialized,
    }
    affected = sorted({b for a in anomalies for b in a.affected_batches})
    severity_order = {"high": 0, "medium": 1, "low": 2}
    top_severity = min(
        (str(a["severity"]) for a in serialized),
        key=lambda s: severity_order.get(s, 3),
        default="medium",
    )

    row = await _get_existing_trend_ai(
        db,
        entity_code=entity_code,
        metric_key=metric_key,
        rule_type=TREND_OVERALL_RULE,
        trend_end_batch=period,
    )
    if row is None:
        record = FinishedTrendAIAnalysis(
            entity_code=entity_code,
            source_label=source_label,
            frontend_group=frontend_group,
            metric_key=metric_key,
            metric_label=metric_label,
            rule_type=TREND_OVERALL_RULE,
            severity=top_severity,
            trend_start_batch=serialized[0]["start_batch"] or "",
            trend_end_batch=period,
            description=f"月度整体趋势分析（{period}，命中 {len(serialized)} 项判据）",
            evidence={"period": period, "anomalies": serialized},
            payload=snapshot,
            affected_batches=affected,
            notification_status="pending",
        )
        db.add(record)
        try:
            await db.commit()
        except IntegrityError:
            # 并发打开竞态：复用已存在记录，不重复提交
            await db.rollback()
            row = await _get_existing_trend_ai(
                db,
                entity_code=entity_code,
                metric_key=metric_key,
                rule_type=TREND_OVERALL_RULE,
                trend_end_batch=period,
            )
            if row is None:
                raise
        else:
            await _submit_trend_ai_job(
                record, sender_user_open_id=sender_user_open_id
            )
            await db.commit()
            row = record
    elif row.ai_summary is None and row.notification_status == "ai_failed":
        # 当月 AI 失败：打开页面自动重试，直至成功；成功后当月固定不再触发
        await _submit_trend_ai_job(row, sender_user_open_id=sender_user_open_id)
        await db.commit()

    merged = _trend_ai_row_to_chart_model([row])
    if merged is not None:
        return serialized, merged, "completed"
    if row.notification_status == "ai_failed":
        return serialized, None, "failed"
    if row.notification_status == "paused":
        return serialized, None, "paused"
    return serialized, None, "pending"


async def reanalyze_trend_ai(
    db: AsyncSession,
    *,
    entity_code: str,
    metric_key: str,
    sender_user_open_id: str | None = None,
) -> dict[str, str]:
    """手动「再次分析」：作废当月整体分析记录并立即重跑（AI + 推送）。

    页面刷新不会走到这里——只有前端显式调用才触发。
    """
    period = _trend_period()
    row = await _get_existing_trend_ai(
        db,
        entity_code=entity_code,
        metric_key=metric_key,
        rule_type=TREND_OVERALL_RULE,
        trend_end_batch=period,
    )
    if row is None:
        raise AppException(
            message=f"当月（{period}）尚无该指标的趋势 AI 分析记录", status_code=404
        )
    payload = row.payload or {}
    row.is_deleted = True
    await db.commit()
    record = FinishedTrendAIAnalysis(
        entity_code=row.entity_code,
        source_label=row.source_label,
        frontend_group=row.frontend_group,
        metric_key=row.metric_key,
        metric_label=row.metric_label,
        rule_type=TREND_OVERALL_RULE,
        severity=row.severity,
        trend_start_batch=row.trend_start_batch,
        trend_end_batch=period,
        description=row.description,
        evidence=row.evidence,
        payload=payload,
        affected_batches=row.affected_batches,
        notification_status="pending",
    )
    db.add(record)
    await db.commit()
    await _submit_trend_ai_job(record, sender_user_open_id=sender_user_open_id)
    await db.commit()
    return {"job_id": record.job_id or "", "period": period}


async def _get_finished_dashboard_data(
    db: AsyncSession,
    *,
    sender_user_open_id: str | None = None,
    source_entity_code: str,
    source_label: str,
    metric_configs: tuple[dict[str, Any], ...],
    oot_product_code: str | None = None,
    frontend_group: str | None = None,
    enable_trend_ai: bool = False,
) -> dict[str, Any]:
    try:
        await _resolve_runtime_entity(db, source_entity_code, direction="pull")
    except AppException:
        return InspectionDashboardData(
            source_entity_code=source_entity_code,
            source_label=source_label,
            charts=[],
            alerts=[],
            summary=InspectionDashboardSummary(
                source_entity_code=source_entity_code,
                source_label=source_label,
                total_records=0,
                valid_record_count=0,
                skipped_value_count=0,
                alert_batch_count=0,
                alert_metric_count=0,
                first_notification_sent_count=0,
                deduplicated_notification_count=0,
                failed_notification_count=0,
                unmapped_notification_count=0,
            ),
            configured=False,
        ).model_dump(mode="json")

    field_names = [
        FINISHED_DASHBOARD_BATCH_FIELD,
        *[str(item["metric_key"]) for item in metric_configs],
    ]
    records = await _search_entity_records_with_fallback(
        db,
        source_entity_code,
        field_names=field_names,
    )

    total_records = len(records)
    valid_record_count = 0
    skipped_value_count = 0
    charts: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []
    trend_alert_metric_count = 0
    trend_ai_pending_count = 0
    trend_ai_completed_count = 0
    oot_limit_items = await _get_oot_limit_items_by_product_code(db, oot_product_code)

    for metric_config in metric_configs:
        metric_key = str(metric_config["metric_key"])
        standard_spec_lines = _build_spec_lines(metric_config)
        oot_spec_lines: list[dict[str, float | str]] = []
        oot_item_name = _normalize_oot_item_name(metric_config.get("oot_item_name"))
        oot_limit_item = oot_limit_items.get(oot_item_name) if oot_item_name else None
        if oot_limit_item is not None:
            oot_spec_lines = _parse_limit_spec_lines(
                oot_limit_item.oot_limit_value,
                label_prefix="OOT",
            )
        spec_lines = _merge_spec_lines(standard_spec_lines, oot_spec_lines)
        alert_spec_lines = _merge_spec_lines(
            _build_alert_spec_lines(metric_config),
            oot_spec_lines,
        )
        points: list[dict[str, Any]] = []

        for record in records:
            fields = record.get("fields") or {}
            batch_no = _normalize(fields.get(FINISHED_DASHBOARD_BATCH_FIELD))
            if not batch_no:
                continue
            actual_value = _parse_numeric_metric(fields.get(metric_key))
            if actual_value is None:
                if fields.get(metric_key) not in (None, "", []):
                    skipped_value_count += 1
                continue
            points.append({"batch_no": batch_no, "value": actual_value})

        if points:
            valid_record_count = max(
                valid_record_count,
                len({point["batch_no"] for point in points}),
            )

        values = [float(point["value"]) for point in points]
        stats = _compute_metric_statistics(values)
        categories = [str(point["batch_no"]) for point in points]
        actual_series = [float(point["value"]) for point in points]
        mean_value = stats["mean"]
        upper_control_limit = stats["upper_control_limit"]
        lower_control_limit = stats["lower_control_limit"]
        mean_series = (
            [mean_value for _ in categories]
            if mean_value is not None
            else [None for _ in categories]
        )
        upper_sigma_series = (
            [upper_control_limit for _ in categories]
            if upper_control_limit is not None
            else [None for _ in categories]
        )
        lower_sigma_series = (
            [lower_control_limit for _ in categories]
            if lower_control_limit is not None
            else [None for _ in categories]
        )

        for point in points:
            point_value = float(point["value"])
            out_of_control_limit = False
            if upper_control_limit is not None and lower_control_limit is not None:
                out_of_control_limit = not (
                    lower_control_limit <= point_value <= upper_control_limit
                )
            out_of_oot_limit = _is_value_out_of_spec_lines(
                point_value, alert_spec_lines
            )
            if not out_of_control_limit and not out_of_oot_limit:
                continue
            try:
                alert = await _materialize_dashboard_alert(
                    db,
                    sender_user_open_id=sender_user_open_id,
                    source_label=source_label,
                    entity_code=source_entity_code,
                    batch_no=str(point["batch_no"]),
                    metric_key=metric_key,
                    metric_label=str(metric_config["metric_label"]),
                    actual_value=point_value,
                    mean=mean_value,
                    std_dev=stats["std_dev"],
                    upper_control_limit=upper_control_limit,
                    lower_control_limit=lower_control_limit,
                    spec_lines=spec_lines if out_of_oot_limit else standard_spec_lines,
                )
                alerts.append(alert)
            except Exception as e:
                logger.warning(
                    "Failed to materialize dashboard alert for "
                    f"{source_entity_code}/{metric_key}: {e}"
                )
                # Alert materialization failed (e.g. feishu auth), skip this alert

        # ── 趋势规则 + AI 分析（确定性判据先算，AI/推送后台化，不阻塞首屏） ──
        trend_anomalies: list[dict[str, Any]] = []
        trend_ai_model: InspectionDashboardTrendAI | None = None
        trend_ai_status = "none"
        if enable_trend_ai:
            try:
                (
                    trend_anomalies,
                    trend_ai_model,
                    trend_ai_status,
                ) = await _process_metric_trend(
                    db,
                    sender_user_open_id=sender_user_open_id,
                    source_label=source_label,
                    entity_code=source_entity_code,
                    frontend_group=frontend_group,
                    metric_key=metric_key,
                    metric_label=str(metric_config["metric_label"]),
                    points=points,
                    mean=mean_value,
                    std_dev=stats["std_dev"],
                    upper_control_limit=upper_control_limit,
                    lower_control_limit=lower_control_limit,
                    spec_lines=spec_lines,
                )
                trend_alert_metric_count += len(trend_anomalies)
                if trend_ai_status == "pending":
                    trend_ai_pending_count += 1
                elif trend_ai_status == "completed":
                    trend_ai_completed_count += 1
            except Exception as exc:  # noqa: BLE001 —— 趋势分析失败降级，不影响图表
                logger.warning(
                    f"Trend analysis failed {source_entity_code}/{metric_key}: {exc}"
                )

        chart = InspectionDashboardChart(
            metric_key=metric_key,
            metric_label=str(metric_config["metric_label"]),
            categories=categories,
            actual_series=actual_series,
            mean_series=mean_series,
            upper_sigma_series=upper_sigma_series,
            lower_sigma_series=lower_sigma_series,
            spec_lines=[
                InspectionDashboardSpecLine.model_validate(item) for item in spec_lines
            ],
            points=[
                InspectionDashboardPoint(
                    batch_no=str(point["batch_no"]),
                    value=float(point["value"]),
                )
                for point in points
            ],
            summary=InspectionDashboardChartSummary(
                sample_count=int(stats["sample_count"] or 0),
                mean=mean_value,
                std_dev=stats["std_dev"],
                upper_control_limit=upper_control_limit,
                lower_control_limit=lower_control_limit,
            ),
            trend_anomalies=[
                InspectionDashboardTrendAnomaly.model_validate(item)
                for item in trend_anomalies
            ],
            trend_ai=trend_ai_model,
            trend_ai_status=trend_ai_status,
        )
        charts.append(chart.model_dump(mode="json"))

    summary = InspectionDashboardSummary(
        source_entity_code=source_entity_code,
        source_label=source_label,
        total_records=total_records,
        valid_record_count=valid_record_count,
        skipped_value_count=skipped_value_count,
        alert_batch_count=len({item["batch_no"] for item in alerts}),
        alert_metric_count=len(alerts),
        first_notification_sent_count=sum(
            1
            for item in alerts
            if item["notification_status"] in {"sent", "partial"}
            and not item["notification_deduplicated"]
        ),
        deduplicated_notification_count=sum(
            1 for item in alerts if item["notification_deduplicated"]
        ),
        failed_notification_count=sum(
            1 for item in alerts if item["notification_status"] in {"failed", "partial"}
        ),
        unmapped_notification_count=sum(
            1
            for item in alerts
            if item["notification_status"] in {"unmapped", "missing_open_id"}
        ),
        trend_alert_metric_count=trend_alert_metric_count,
        trend_ai_pending_count=trend_ai_pending_count,
        trend_ai_completed_count=trend_ai_completed_count,
    )
    return InspectionDashboardData(
        source_entity_code=source_entity_code,
        source_label=source_label,
        charts=charts,
        alerts=alerts,
        summary=summary,
        configured=True,
    ).model_dump(mode="json")


# Re-export public dashboard entry functions for backward compatibility.
# This import is placed at the bottom to avoid circular imports:
# inspection_dashboard_entry imports _get_finished_dashboard_data from this module,
# and this module re-exports the entry functions that wrap it.
