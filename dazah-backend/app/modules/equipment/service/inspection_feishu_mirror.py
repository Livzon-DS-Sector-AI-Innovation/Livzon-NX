"""设备巡检飞书多维表格镜像同步服务。

岗位人员在飞书多维表格录入巡检记录，本服务把三张表
（今日巡检 / 设备历史巡检记录 / 设备档案表）镜像到平台
本地库，页面只读展示。同步策略：
- 增量：按飞书记录 last_modified_time 降序翻页，取到水位
  之前的记录即停；水位存 sync_state。
- 全量：翻页拉全表，UPSERT 并删除飞书侧已删除的行（软删）。
- 容错：排序被飞书拒绝时增量回退全量翻页 + 客户端水位过滤；
  飞书不可达抛 AppException，由调用方（调度器/手动同步）记录
  失败状态，不影响已有数据展示。
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.equipment.models.inspection_feishu_mirror import (
    EquipmentInspectionFeishuDevice,
    EquipmentInspectionFeishuRecord,
    EquipmentInspectionFeishuSyncState,
)
from app.modules.equipment.service.inspection_feishu_config import (
    InspectionFeishuEffectiveConfig,
    get_effective_config,
)
from app.platform.integrations.feishu.bitable import BitableClient

logger = logging.getLogger(__name__)

_CST = timezone(timedelta(hours=8))

SOURCE_TODAY = "today"
SOURCE_HISTORY = "history"
SOURCE_DEVICES = "devices"

# 检查项关键字 → 镜像列（上午/下午前缀区分）
_ITEM_COLUMN_KEYS: dict[str, str] = {
    "清洁": "clean",
    "润滑": "lubrication",
    "紧固": "fastening",
    "密封": "sealing",
    "震动": "vibration",
    "异声": "sound",
    "外表": "surface",  # 兼容今日表错别字列「外表吴克坚变色…」
}

_CHECK_VALUES = {"√", "×"}

# 镜像列宽（与 ORM 模型一致）；飞书自由文本超宽时截断，原文保留在 raw_fields
_EQUIPMENT_NAME_MAX = 200
_EQUIPMENT_NO_MAX = 100
_PROCESS_STATUS_MAX = 20


def _truncate(value: str | None, limit: int) -> str | None:
    if value is None or len(value) <= limit:
        return value
    return value[:limit]


def _table_id(config: InspectionFeishuEffectiveConfig, table_key: str) -> str:
    mapping = {
        SOURCE_TODAY: config.today_table_id,
        SOURCE_HISTORY: config.history_table_id,
        SOURCE_DEVICES: config.device_table_id,
    }
    table_id = mapping.get(table_key, "")
    if not table_id:
        raise AppException(message=f"巡检镜像表 {table_key} 未配置表格 ID")
    return table_id


def _build_client(config: InspectionFeishuEffectiveConfig) -> BitableClient:
    return BitableClient(
        app_token=config.app_token,
        app_id=config.app_id,
        app_secret=config.app_secret,
    )


# ── 飞书字段值规范化 ─────────────────────────────────────────────


def _text_value(value: Any) -> str | None:
    """富文本段列表 / 普通值 → 纯文本。"""
    if value is None:
        return None
    if isinstance(value, list):
        parts = [
            (seg or {}).get("text", "") if isinstance(seg, dict) else str(seg)
            for seg in value
        ]
        joined = "".join(parts).strip()
        return joined or None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return str(value).strip() or None


def _date_value(value: Any) -> date | None:
    """毫秒时间戳 / ISO 字符串 → date。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=_CST).date()
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _datetime_value(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=_CST)
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _match_check_column(field_name: str) -> tuple[str, str] | None:
    """「上午清洁」类列名 → (am/pm, 列 key)。按关键字匹配，兼容错别字列。"""
    prefix = None
    if "上午" in field_name:
        prefix = "am"
    elif "下午" in field_name:
        prefix = "pm"
    if prefix is None:
        return None
    for keyword, column_key in _ITEM_COLUMN_KEYS.items():
        if keyword in field_name:
            return prefix, column_key
    return None


def normalize_record_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """飞书记录 fields → 巡检记录镜像列。

    识别列：日期 / 设备名称 / 设备编号 / 上午下午 7 项 /
    其他异常情况 / 处理状态；其余列保留在 raw_fields。
    """
    normalized: dict[str, Any] = {}
    check_values: dict[str, str | None] = {}
    for field_name, value in (fields or {}).items():
        if field_name == "日期":
            normalized["record_date"] = _date_value(value)
        elif field_name == "设备名称":
            normalized["equipment_name"] = _truncate(
                _text_value(value), _EQUIPMENT_NAME_MAX
            )
        elif field_name == "设备编号":
            normalized["equipment_no"] = _truncate(
                _text_value(value), _EQUIPMENT_NO_MAX
            )
        elif "异常情况" in field_name:
            normalized["anomaly_note"] = _text_value(value)
        elif field_name == "处理状态":
            normalized["process_status"] = _truncate(
                _text_value(value), _PROCESS_STATUS_MAX
            )
        else:
            matched = _match_check_column(field_name)
            if matched is not None:
                prefix, column_key = matched
                cell = value if isinstance(value, str) else _text_value(value)
                # 未知选项 ID（如残留 optQYbBdcd）视为未填
                check_values[f"{prefix}_{column_key}"] = (
                    cell if cell in _CHECK_VALUES else None
                )
    normalized.update(check_values)
    normalized["has_abnormal"] = any(v == "×" for v in check_values.values())
    return normalized


# ── 同步执行 ─────────────────────────────────────────────────────


async def _fetch_pages(
    client: BitableClient,
    table_id: str,
    *,
    sort_by_modified: bool,
    stop_before_ms: int | None = None,
) -> list[dict[str, Any]]:
    """翻页拉取记录。

    sort_by_modified=True 时按 last_modified_time 降序，
    stop_before_ms 水位之前的页到达即停（增量）；
    排序被飞书拒绝由调用方回退全量。
    """
    records: list[dict[str, Any]] = []
    page_token: str | None = None
    while True:
        if sort_by_modified:
            # records/search 支持自定义 sort，需走原始请求
            page = await client.client.request(
                "POST",
                f"/bitable/v1/apps/{client.app_token}/tables/{table_id}/records/search",
                params={
                    "page_size": 500,
                    "field_name_type": "name",
                    "automatic_fields": True,
                    **({"page_token": page_token} if page_token else {}),
                },
                json={"sort": [{"field_name": "last_modified_time", "desc": True}]},
                timeout=60.0,
            )
            items = [i for i in (page.get("items") or []) if isinstance(i, dict)]
            has_more = bool(page.get("has_more"))
            page_token = page.get("page_token")
        else:
            page = await client.search_records_page(
                table_id,
                page_size=500,
                automatic_fields=True,
                timeout=60.0,
                page_token=page_token,
            )
            items = page["items"]
            has_more = page["has_more"]
            page_token = page["page_token"]

        if stop_before_ms is not None:
            reached = False
            for item in items:
                modified = (item or {}).get("last_modified_time")
                if isinstance(modified, (int, float)) and modified < stop_before_ms:
                    reached = True
                    break
                records.append(item)
            if reached or not has_more:
                break
        else:
            records.extend(items)
            if not has_more:
                break
    return records


async def _get_state(
    db: AsyncSession, table_key: str
) -> EquipmentInspectionFeishuSyncState:
    state = (
        await db.execute(
            select(EquipmentInspectionFeishuSyncState).where(
                EquipmentInspectionFeishuSyncState.table_key == table_key,
                EquipmentInspectionFeishuSyncState.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if state is None:
        state = EquipmentInspectionFeishuSyncState(table_key=table_key, total_rows=0)
        db.add(state)
        await db.flush()
    return state


async def _upsert_record(
    db: AsyncSession, source: str, item: dict[str, Any]
) -> None:
    record_id = str(item.get("record_id") or "")
    if not record_id:
        return
    fields = item.get("fields") or {}
    values = normalize_record_fields(fields)
    existing = (
        await db.execute(
            select(EquipmentInspectionFeishuRecord).where(
                EquipmentInspectionFeishuRecord.source == source,
                EquipmentInspectionFeishuRecord.record_id == record_id,
                EquipmentInspectionFeishuRecord.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    modified = _datetime_value(item.get("last_modified_time"))
    column_values = {
        "record_id": record_id,
        "record_date": values.get("record_date"),
        "equipment_name": values.get("equipment_name"),
        "equipment_no": values.get("equipment_no"),
        "anomaly_note": values.get("anomaly_note"),
        "process_status": values.get("process_status"),
        "has_abnormal": bool(values.get("has_abnormal")),
        "raw_fields": fields,
        "last_modified_at": modified,
        **{
            key: values.get(key)
            for key in (
                "am_clean", "am_lubrication", "am_fastening", "am_sealing",
                "am_vibration", "am_sound", "am_surface",
                "pm_clean", "pm_lubrication", "pm_fastening", "pm_sealing",
                "pm_vibration", "pm_sound", "pm_surface",
            )
        },
    }
    if existing is not None:
        for key, value in column_values.items():
            setattr(existing, key, value)
    else:
        db.add(
            EquipmentInspectionFeishuRecord(source=source, **column_values)
        )


async def _upsert_device(db: AsyncSession, item: dict[str, Any]) -> None:
    record_id = str(item.get("record_id") or "")
    if not record_id:
        return
    fields = item.get("fields") or {}
    name = _truncate(_text_value(fields.get("设备名称")), _EQUIPMENT_NAME_MAX)
    no = _truncate(_text_value(fields.get("设备编号")), _EQUIPMENT_NO_MAX)
    modified = _datetime_value(item.get("last_modified_time"))
    existing = (
        await db.execute(
            select(EquipmentInspectionFeishuDevice).where(
                EquipmentInspectionFeishuDevice.record_id == record_id,
                EquipmentInspectionFeishuDevice.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.equipment_name = name
        existing.equipment_no = no
        existing.last_modified_at = modified
    else:
        db.add(
            EquipmentInspectionFeishuDevice(
                record_id=record_id,
                equipment_name=name,
                equipment_no=no,
                last_modified_at=modified,
            )
        )


async def sync_table(
    db: AsyncSession,
    table_key: str,
    *,
    incremental: bool = True,
    config: InspectionFeishuEffectiveConfig | None = None,
) -> dict[str, Any]:
    """同步一张镜像表。返回 {synced, total}；失败抛 AppException。"""
    if config is None:
        config = await get_effective_config(db)
    if not config.enabled:
        raise AppException(message="巡检飞书镜像同步未配置（缺少应用凭据或表格 ID）")

    table_id = _table_id(config, table_key)
    client = _build_client(config)
    state = await _get_state(db, table_key)

    stop_before_ms: int | None = None
    if incremental and state.last_synced_at is not None:
        # 水位回退 60 秒容错（飞书修改时间粒度/时钟偏差）
        watermark = state.last_synced_at - timedelta(seconds=60)
        stop_before_ms = int(watermark.timestamp() * 1000)

    try:
        if stop_before_ms is not None:
            try:
                records = await _fetch_pages(
                    client, table_id, sort_by_modified=True,
                    stop_before_ms=stop_before_ms,
                )
            except Exception:  # noqa: BLE001
                # last_modified_time 排序被飞书拒绝（InvalidSort）等 →
                # 回退全量翻页 + 客户端水位过滤
                records = [
                    item
                    for item in await _fetch_pages(
                        client, table_id, sort_by_modified=False
                    )
                    if (_datetime_value(item.get("last_modified_time"))
                        or datetime.min.replace(tzinfo=UTC)) >= watermark
                ]
        else:
            records = await _fetch_pages(client, table_id, sort_by_modified=False)
    except AppException:
        raise
    except Exception as error:  # noqa: BLE001
        raise AppException(message=f"飞书多维表格访问失败：{error}") from error

    synced = 0
    if table_key == SOURCE_DEVICES:
        for item in records:
            await _upsert_device(db, item)
            synced += 1
    else:
        for item in records:
            await _upsert_record(db, table_key, item)
            synced += 1

    if not incremental:
        # 全量对账：删除飞书侧已删的行（限定本 source，不影响其他来源）
        keep_ids = {str(item.get("record_id")) for item in records}
        if table_key == SOURCE_DEVICES:
            model: type[EquipmentInspectionFeishuDevice] | type[
                EquipmentInspectionFeishuRecord
            ] = EquipmentInspectionFeishuDevice
            scope = [
                EquipmentInspectionFeishuDevice.is_deleted == False,  # noqa: E712
            ]
        else:
            model = EquipmentInspectionFeishuRecord
            scope = [
                EquipmentInspectionFeishuRecord.source == table_key,
                EquipmentInspectionFeishuRecord.is_deleted == False,  # noqa: E712
            ]
        locals_rows = (
            await db.execute(select(model.record_id).where(*scope))
        ).scalars().all()
        stale_ids = [local_id for local_id in locals_rows if local_id not in keep_ids]
        for local_id in stale_ids:
            await db.execute(delete(model).where(model.record_id == local_id))

    now = datetime.now(UTC)
    count_model = (
        EquipmentInspectionFeishuDevice
        if table_key == SOURCE_DEVICES
        else EquipmentInspectionFeishuRecord
    )
    if table_key != SOURCE_DEVICES:
        count_stmt = (
            select(func.count(count_model.id))
            .where(count_model.source == table_key)
            .where(count_model.is_deleted == False)  # noqa: E712
        )
    else:
        count_stmt = select(func.count(count_model.id)).where(
            count_model.is_deleted == False  # noqa: E712
        )
    total = (await db.execute(count_stmt)).scalar_one()
    state.total_rows = int(total)
    state.last_run_at = now
    state.last_status = "success"
    state.last_message = None
    if records:
        newest = max(
            (_datetime_value(item.get("last_modified_time")) for item in records),
            key=lambda dt: dt or datetime.min.replace(tzinfo=UTC),
        )
        if newest is not None:
            state.last_synced_at = max(
                newest, state.last_synced_at or datetime.min.replace(tzinfo=UTC)
            )
    await db.flush()
    logger.info("inspection feishu mirror synced: %s +%d total=%d",
                table_key, synced, total)
    return {"synced": synced, "total": int(total)}


async def sync_all(
    db: AsyncSession, *, incremental: bool = True
) -> dict[str, dict[str, Any]]:
    """同步三张表；单表失败不影响其余表，结果按表返回。"""
    config = await get_effective_config(db)
    results: dict[str, dict[str, Any]] = {}
    for table_key in (SOURCE_TODAY, SOURCE_HISTORY, SOURCE_DEVICES):
        try:
            results[table_key] = await sync_table(
                db, table_key, incremental=incremental, config=config
            )
        except AppException as error:
            state = await _get_state(db, table_key)
            state.last_run_at = datetime.now(UTC)
            state.last_status = "failed"
            state.last_message = error.message
            await db.flush()
            results[table_key] = {"error": error.message}
        except Exception as error:  # noqa: BLE001
            # 数据库级错误会中止当前事务：回滚整轮保证结果与库一致，
            # 三张表统一记失败等待下次同步重试，避免上升为接口 500。
            message = (
                f"同步中断已回滚：{type(error).__name__}: {str(error)[:200]}"
            )
            logger.exception(
                "inspection feishu mirror sync aborted at %s", table_key
            )
            await db.rollback()
            for key in (SOURCE_TODAY, SOURCE_HISTORY, SOURCE_DEVICES):
                state = await _get_state(db, key)
                state.last_run_at = datetime.now(UTC)
                state.last_status = "failed"
                state.last_message = message
                results[key] = {"error": message}
            return results
    return results


async def get_sync_states(db: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(EquipmentInspectionFeishuSyncState).where(
                EquipmentInspectionFeishuSyncState.is_deleted == False  # noqa: E712
            )
        )
    ).scalars().all()
    return [
        {
            "table_key": row.table_key,
            "total_rows": row.total_rows,
            "last_synced_at": row.last_synced_at,
            "last_run_at": row.last_run_at,
            "last_status": row.last_status,
            "last_message": row.last_message,
        }
        for row in rows
    ]


# ── 查询（页面只读展示） ─────────────────────────────────────────


async def list_records(
    db: AsyncSession,
    *,
    source: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    keyword: str | None = None,
    abnormal_only: bool = False,
    process_status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[EquipmentInspectionFeishuRecord], int]:
    conditions = [EquipmentInspectionFeishuRecord.is_deleted == False]  # noqa: E712
    if source:
        conditions.append(EquipmentInspectionFeishuRecord.source == source)
    if date_from:
        conditions.append(EquipmentInspectionFeishuRecord.record_date >= date_from)
    if date_to:
        conditions.append(EquipmentInspectionFeishuRecord.record_date <= date_to)
    if keyword:
        like = f"%{keyword.strip()}%"
        conditions.append(
            func.coalesce(EquipmentInspectionFeishuRecord.equipment_name, "").like(like)
            | func.coalesce(EquipmentInspectionFeishuRecord.equipment_no, "").like(like)
        )
    if abnormal_only:
        conditions.append(EquipmentInspectionFeishuRecord.has_abnormal.is_(True))
    if process_status:
        conditions.append(
            EquipmentInspectionFeishuRecord.process_status == process_status
        )

    total = (
        await db.execute(
            select(func.count(EquipmentInspectionFeishuRecord.id)).where(*conditions)
        )
    ).scalar_one()
    rows = (
        await db.execute(
            select(EquipmentInspectionFeishuRecord)
            .where(*conditions)
            .order_by(
                EquipmentInspectionFeishuRecord.record_date.desc(),
                EquipmentInspectionFeishuRecord.equipment_no.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return list(rows), int(total)


async def list_devices(
    db: AsyncSession, *, keyword: str | None = None
) -> list[dict[str, Any]]:
    """巡检设备清单 + 台账信息（按编号关联，互不修改）。"""
    conditions = [EquipmentInspectionFeishuDevice.is_deleted == False]  # noqa: E712
    if keyword:
        like = f"%{keyword.strip()}%"
        conditions.append(
            func.coalesce(EquipmentInspectionFeishuDevice.equipment_name, "").like(like)
            | func.coalesce(EquipmentInspectionFeishuDevice.equipment_no, "").like(like)
        )
    devices = (
        await db.execute(
            select(EquipmentInspectionFeishuDevice)
            .where(*conditions)
            .order_by(EquipmentInspectionFeishuDevice.equipment_no.asc())
        )
    ).scalars().all()

    from app.modules.equipment.models.equipment import Equipment

    ledger_nos = {
        no
        for (no,) in (
            await db.execute(
                select(Equipment.equipment_no).where(Equipment.is_deleted == False)  # noqa: E712
            )
        ).all()
    }
    ledger_rows = (
        await db.execute(
            select(
                Equipment.equipment_no,
                Equipment.model,
                Equipment.location_id,
            ).where(Equipment.is_deleted == False)  # noqa: E712
        )
    ).all()
    location_names: dict[Any, str] = {}
    if ledger_rows:
        from app.modules.equipment.models.equipment import Location as LedgerLocation

        loc_rows = (
            await db.execute(
                select(LedgerLocation.id, LedgerLocation.name).where(
                    LedgerLocation.is_deleted == False  # noqa: E712
                )
            )
        ).all()
        location_names = {loc_id: name for loc_id, name in loc_rows}
    ledger_map = {
        no: {"model": model, "location_name": location_names.get(loc_id)}
        for no, model, loc_id in ledger_rows
    }

    # 今日状态：已巡（有记录）/ 异常（含 ×）/ 未巡
    today = date.today()
    today_rows = (
        await db.execute(
            select(
                EquipmentInspectionFeishuRecord.equipment_no,
                EquipmentInspectionFeishuRecord.has_abnormal,
            ).where(
                EquipmentInspectionFeishuRecord.record_date == today,
                EquipmentInspectionFeishuRecord.is_deleted == False,  # noqa: E712
            )
        )
    ).all()
    today_status: dict[str, str] = {}
    for no, abnormal in today_rows:
        if no:
            current = today_status.get(no, "inspected")
            if abnormal or current == "abnormal":
                today_status[no] = "abnormal"
            else:
                today_status[no] = "inspected"

    return [
        {
            "record_id": device.record_id,
            "equipment_name": device.equipment_name,
            "equipment_no": device.equipment_no,
            "model": ledger_map.get(device.equipment_no, {}).get("model"),
            "location_name": ledger_map.get(device.equipment_no, {}).get(
                "location_name"
            ),
            "in_ledger": device.equipment_no in ledger_nos,
            "today_status": today_status.get(device.equipment_no, "pending"),
        }
        for device in devices
    ]


async def today_summary(db: AsyncSession) -> dict[str, Any]:
    """今日进度：应巡（档案表）/ 已巡 / 异常。"""
    total_devices = (
        await db.execute(
            select(func.count(EquipmentInspectionFeishuDevice.id)).where(
                EquipmentInspectionFeishuDevice.is_deleted == False  # noqa: E712
            )
        )
    ).scalar_one()
    today = date.today()
    rows = (
        await db.execute(
            select(
                EquipmentInspectionFeishuRecord.equipment_no,
                EquipmentInspectionFeishuRecord.has_abnormal,
            ).where(
                EquipmentInspectionFeishuRecord.record_date == today,
                EquipmentInspectionFeishuRecord.is_deleted == False,  # noqa: E712
            )
        )
    ).all()
    inspected: set[str] = set()
    abnormal: set[str] = set()
    for no, has_abnormal in rows:
        if no:
            inspected.add(no)
            if has_abnormal:
                abnormal.add(no)
    return {
        "date": today,
        "total_devices": int(total_devices),
        "inspected": len(inspected),
        "abnormal": len(abnormal),
    }
