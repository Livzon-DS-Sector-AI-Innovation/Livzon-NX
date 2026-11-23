"""质量检验-物品管理 仪表盘统计与库存不足一键推送。

全部从本地镜像（inspection_items_mirror）读取，不再每次实时打飞书：
- 库存不足预警清单与计数（判定口径可配置：飞书"库存报警"列 / 本地阈值）；
- 月度出入库量聚合（按镜像行的业务日期列，缺日期回落镜像行 created_at）；
- 一键推送库存不足物料给可配置接收人（飞书个人卡片，模块凭证）。
"""

from __future__ import annotations

import logging
import uuid
from contextlib import aclosing
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.quality import feishu_notification
from app.modules.quality.models.inspection_items_mirror import (
    QualityItemsStockAlertNotification,
)
from app.modules.quality.repository import inspection_items_mirror as repo
from app.modules.quality.schemas.inspection_items_dashboard import (
    ItemsDashboardResponse,
    ItemsMonthlyPoint,
    ItemsStockAlertItem,
    PushLowStockResult,
)
from app.modules.quality.service.inspection_items_mirror import (
    ITEMS_DATE_SORT_FIELDS,
    PAGE_INBOUND,
    PAGE_INVENTORY,
    PAGE_OUTBOUND,
)
from app.modules.quality.service.person_directory import resolve_person_by_name
from app.modules.quality.service.quality_notification_settings import (
    ItemsStockAlertConfig,
    load_items_stock_alert_config,
)

logger = logging.getLogger(__name__)

# 库存报警"不足"匹配值（飞书列文案，命中任一即视为预警）
_STOCK_ALARM_LOW_VALUES = {"库存不足", "不足", "预警", "报警", "低"}
# 出入库页业务日期候选列名 / 数量候选列名
_INBOUND_DATE_KEYS = ["入库日期", "日期", "入库时间"]
_OUTBOUND_DATE_KEYS = ["领用日期", "出库日期", "日期", "领用时间"]
_INBOUND_QTY_KEYS = ["入库数量"]
_OUTBOUND_QTY_KEYS = ["领取数量", "出库数量"]
_PREVIEW_LIMIT = 10


def _to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    if isinstance(value, list) and value:
        return _to_number(value[0])
    return None


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return " ".join(_cell_text(v) for v in value).strip()
    if isinstance(value, dict):
        return str(value.get("text") or value.get("name") or "").strip()
    return str(value).strip()


def _is_low_stock(item: dict[str, Any], warning_source: str) -> bool:
    if warning_source == "local_threshold":
        current = _to_number(item.get("当前库存"))
        warning = _to_number(item.get("警戒库存"))
        if current is None or warning is None:
            return False
        return current <= warning
    alarm = _cell_text(item.get("库存报警")).lower()
    return any(token.lower() in alarm for token in _STOCK_ALARM_LOW_VALUES)


_ALERT_META_KEYS = {"record_id", "created_at", "updated_at", "__link_record_ids"}


def _build_alert_item(item: dict[str, Any]) -> ItemsStockAlertItem:
    fields = {
        key: value
        for key, value in item.items()
        if key not in _ALERT_META_KEYS and not str(key).startswith("__")
    }
    return ItemsStockAlertItem(
        record_id=str(item.get("record_id") or ""),
        name=_cell_text(item.get("物资名称")) or _cell_text(item.get("物资名（规格）")),
        specification=_cell_text(item.get("规格型号")) or None,
        location=_cell_text(item.get("存放位置")) or None,
        current_stock=_cell_text(item.get("当前库存")) or None,
        warning_stock=_cell_text(item.get("警戒库存")) or None,
        unit=_cell_text(item.get("单位")) or None,
        fields=fields,
    )


async def _read_inventory_alerts(
    db: AsyncSession, config: ItemsStockAlertConfig
) -> tuple[list[dict[str, Any]], int, bool, str | None]:
    snapshot = await repo.get_snapshot(db, PAGE_INVENTORY)
    if snapshot is None:
        return [], 0, False, None
    columns = [str(col["key"]) for col in (snapshot.columns or []) if col.get("key")]
    alarm_fields = {"库存报警", "当前库存", "警戒库存"} & set(columns)
    alerts: list[dict[str, Any]] = []
    total = 0
    async with aclosing(repo.iter_statistics_rows(db, snapshot.id)) as rows:
        async for record_id, created, updated, cells in rows:
            total += 1
            if _is_low_stock(
                {key: cells.get(key) for key in alarm_fields}, config.warning_source
            ):
                alerts.append(
                    {
                        "record_id": record_id,
                        "created_at": created.isoformat() if created else None,
                        "updated_at": cells.get("__last_modified")
                        or (updated.isoformat() if updated else None),
                        **{key: cells.get(key) for key in columns},
                    }
                )
    last_sync = snapshot.last_synced_at
    return alerts, total, True, last_sync.isoformat() if last_sync else None


async def find_low_stock_items(
    db: AsyncSession, config: ItemsStockAlertConfig
) -> list[dict[str, Any]]:
    """返回库存不足物料原始行（含 record_id）。"""
    alerts, _, _, _ = await _read_inventory_alerts(db, config)
    return alerts


def _pick_cell_value(row: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return row.get(key)
    return None


def _row_month(row: dict[str, Any], date_keys: list[str]) -> int | None:
    raw = _pick_cell_value(row, date_keys)
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    # 毫秒时间戳可能被归一化成纯数字字符串（飞书日期列经 GET /records 回读）
    if isinstance(raw, str) and raw.strip().isdigit():
        raw = float(raw.strip())
    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(float(raw) / 1000, tz=UTC).month
        except (ValueError, OSError):
            pass
    elif isinstance(raw, str) and raw:
        try:
            return datetime.fromisoformat(raw[:10]).month
        except ValueError:
            pass
    created = row.get("created_at")
    if isinstance(created, str):
        try:
            return datetime.fromisoformat(created).month
        except ValueError:
            return None
    return None


async def _monthly_quantity(
    db: AsyncSession, page_key: str, date_keys: list[str], quantity_keys: list[str]
) -> dict[int, float]:
    totals = dict.fromkeys(range(1, 13), 0.0)
    snapshot = await repo.get_snapshot(db, page_key)
    if snapshot is None:
        return totals
    columns = {str(col["key"]) for col in (snapshot.columns or []) if col.get("key")}
    fields = [key for key in (*date_keys, *quantity_keys) if key in columns]
    sort_field = ITEMS_DATE_SORT_FIELDS.get(page_key)
    async with aclosing(
        repo.iter_statistics_rows(
            db,
            snapshot.id,
            sort_field=sort_field if sort_field in columns else None,
            project_fields=fields,
        )
    ) as rows:
        async for _, created, _, cells in rows:
            cells["created_at"] = created.isoformat() if created else None
            month = _row_month(cells, date_keys)
            quantity = _to_number(_pick_cell_value(cells, quantity_keys))
            if month and quantity is not None:
                totals[month] += quantity
    return totals


async def get_items_dashboard(db: AsyncSession) -> ItemsDashboardResponse:
    """物品管理仪表盘：库存预警 + 月度出入库量。"""
    config = await load_items_stock_alert_config(db)
    low_rows, total, configured, last_sync = await _read_inventory_alerts(db, config)
    inbound = await _monthly_quantity(
        db, PAGE_INBOUND, _INBOUND_DATE_KEYS, _INBOUND_QTY_KEYS
    )
    outbound = await _monthly_quantity(
        db, PAGE_OUTBOUND, _OUTBOUND_DATE_KEYS, _OUTBOUND_QTY_KEYS
    )
    monthly = [
        ItemsMonthlyPoint(month=month, inbound=inbound[month], outbound=outbound[month])
        for month in range(1, 13)
    ]

    return ItemsDashboardResponse(
        configured=configured,
        total_items=total,
        alert_count=len(low_rows),
        warning_source=config.warning_source,
        low_stock_items=[_build_alert_item(item) for item in low_rows],
        year=datetime.now(UTC).year,
        monthly=monthly,
        last_sync_time=last_sync,
    )


def _render_template(template: str, default: str, replacements: dict[str, str]) -> str:
    text = (template or "").strip() or default
    for key, value in replacements.items():
        text = text.replace("{" + key + "}", value)
    return text


def _build_alert_content(
    low_items: list[ItemsStockAlertItem], config: ItemsStockAlertConfig, date_text: str
) -> tuple[str, str]:
    count = len(low_items)
    title = _render_template(
        config.header_template,
        "物品库存不足预警",
        {"date": date_text, "count": str(count)},
    )
    lines = [title, ""]
    for item in low_items[:_PREVIEW_LIMIT]:
        spec = f"（{item.specification}）" if item.specification else ""
        current = item.current_stock or "-"
        warning = item.warning_stock or "-"
        stock = f"当前 {current}{item.unit or ''} / 警戒 {warning}"
        lines.append(f"- {item.name or '未命名'}{spec}：{stock}")
    if count > _PREVIEW_LIMIT:
        lines.append(f"…其余 {count - _PREVIEW_LIMIT} 种请到系统查看。")
    footer = _render_template(
        config.footer_template, "", {"date": date_text, "count": str(count)}
    )
    if footer:
        lines.append("")
        lines.append(footer)
    return title, "\n".join(lines)


def _build_deep_link(config: ItemsStockAlertConfig) -> str:
    base = get_settings().FRONTEND_URL.rstrip("/")
    link = f"{base}/quality/inspection/items/inventory"
    if config.warning_source == "feishu":
        link = f"{link}?filter_库存报警=库存不足"
    return link


async def _resolve_recipients(
    db: AsyncSession, config: ItemsStockAlertConfig
) -> list[tuple[str, str, str]]:
    """解析接收人为 (receive_id, receive_id_type, name)。"""
    resolved: list[tuple[str, str, str]] = []
    for item in config.recipients:
        open_id = (item.get("open_id") or "").strip()
        name = (item.get("name") or "").strip()
        if not open_id and name:
            person = await resolve_person_by_name(db, name)
            if person:
                open_id = str(person.get("open_id") or "").strip()
        if open_id:
            resolved.append((open_id, "open_id", name or open_id))
    return resolved


async def push_low_stock_alert(
    db: AsyncSession,
    *,
    test: bool = False,
    period_key: str | None = None,
    actor_user_open_id: str | None = None,
) -> PushLowStockResult:
    """一键推送库存不足物料到可配置接收人。

    test=True 走测试推送（不写幂等表、不影响真实去重）。
    真实推送按 (物料, 接收人, period_key) 幂等去重。
    """
    config = await load_items_stock_alert_config(db)
    low_rows = await find_low_stock_items(db, config)
    low_items = [_build_alert_item(it) for it in low_rows]
    if not low_items:
        return PushLowStockResult(status="no_data", item_count=0)

    date_text = datetime.now(UTC).strftime("%Y-%m-%d")
    title, content = _build_alert_content(low_items, config, date_text)
    link = _build_deep_link(config)
    elements = [
        {
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "查看库存台账"},
                    "type": "primary",
                    "url": link,
                }
            ],
        }
    ]

    recipients = await _resolve_recipients(db, config)
    if not recipients:
        return PushLowStockResult(
            status="unmapped", item_count=len(low_items), message="未配置有效接收人"
        )

    period = period_key or (date_text if not test else f"test:{uuid.uuid4().hex[:8]}")
    sent = skipped = failed = 0
    for receive_id, receive_id_type, name in recipients:
        if not test:
            pending = await _pending_items_for_recipient(
                db, receive_id, period, low_items
            )
            if not pending:
                skipped += 1
                continue
        else:
            pending = low_items
        message_id = await feishu_notification.send_user_card_with_message_id(
            receive_id,
            title,
            content,
            elements=elements,
            receive_id_type=receive_id_type,
        )
        if message_id:
            sent += 1
            if not test:
                await _record_notifications(
                    db, receive_id, name, period, pending, message_id
                )
        else:
            failed += 1
    await db.commit()

    status = "sent" if sent and not failed else ("partial" if sent else "failed")
    return PushLowStockResult(
        status=status,
        sent=sent,
        skipped=skipped,
        failed=failed,
        item_count=len(low_items),
    )


async def _pending_items_for_recipient(
    db: AsyncSession,
    receive_id: str,
    period: str,
    low_items: list[ItemsStockAlertItem],
) -> list[ItemsStockAlertItem]:
    notified_ids = set(
        (
            await db.execute(
                select(QualityItemsStockAlertNotification.source_record_id).where(
                    QualityItemsStockAlertNotification.recipient_open_id == receive_id,
                    QualityItemsStockAlertNotification.period_key == period,
                    QualityItemsStockAlertNotification.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    return [item for item in low_items if item.record_id not in notified_ids]


async def _record_notifications(
    db: AsyncSession,
    receive_id: str,
    name: str,
    period: str,
    items: list[ItemsStockAlertItem],
    message_id: str,
) -> None:
    for item in items:
        db.add(
            QualityItemsStockAlertNotification(
                page_key=PAGE_INVENTORY,
                source_record_id=item.record_id,
                recipient_open_id=receive_id,
                recipient_name=name,
                period_key=period,
                item_name=item.name,
                feishu_message_id=message_id,
                notification_status="sent",
            )
        )
    await db.flush()
