"""设备巡检飞书多维表格镜像同步服务。

岗位人员在飞书多维表格录入巡检记录，本服务把每个车间配置的三张表
（今日巡检 / 设备历史巡检记录 / 设备档案表）镜像到平台本地库
（按 workshop_code 隔离），页面只读展示。同步策略：
- 增量：按飞书记录 last_modified_time 降序翻页，取到水位
  之前的记录即停；水位存 sync_state（每车间每表一行）。
- 全量：翻页拉全表，UPSERT 并删除飞书侧已删除的行（软删）。
- 容错：排序被飞书拒绝时增量回退全量翻页 + 客户端水位过滤；
  飞书不可达抛 AppException，由调用方（调度器/手动同步）记录
  失败状态，不影响已有数据展示。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
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
    list_enabled_workshops,
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

# 多设备合并填写的原始行被飞书侧拆分后的处理状态；拆分产物已逐设备成行，
# 今日口径不展示这类原始行
_STATUS_SPLIT = "已拆分"


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
            record_page = await client.search_records_page(
                table_id,
                page_size=500,
                automatic_fields=True,
                timeout=60.0,
                page_token=page_token,
            )
            items = record_page["items"]
            has_more = record_page["has_more"]
            page_token = record_page["page_token"]

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
    db: AsyncSession, workshop_code: str, table_key: str
) -> EquipmentInspectionFeishuSyncState:
    state = (
        await db.execute(
            select(EquipmentInspectionFeishuSyncState).where(
                EquipmentInspectionFeishuSyncState.workshop_code == workshop_code,
                EquipmentInspectionFeishuSyncState.table_key == table_key,
                EquipmentInspectionFeishuSyncState.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if state is None:
        state = EquipmentInspectionFeishuSyncState(
            workshop_code=workshop_code, table_key=table_key, total_rows=0
        )
        db.add(state)
        await db.flush()
    return state


async def _upsert_record(
    db: AsyncSession, workshop_code: str, source: str, item: dict[str, Any]
) -> None:
    record_id = str(item.get("record_id") or "")
    if not record_id:
        return
    fields = item.get("fields") or {}
    values = normalize_record_fields(fields)
    existing = (
        await db.execute(
            select(EquipmentInspectionFeishuRecord).where(
                EquipmentInspectionFeishuRecord.workshop_code == workshop_code,
                EquipmentInspectionFeishuRecord.source == source,
                EquipmentInspectionFeishuRecord.record_id == record_id,
                EquipmentInspectionFeishuRecord.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    modified = _datetime_value(item.get("last_modified_time"))
    column_values = {
        "workshop_code": workshop_code,
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


async def _ensure_ledger_registration(db: AsyncSession, device: Any) -> None:
    """镜像设备自动注册进设备台账（按编号去重、幂等）。

    台账是出码与报修的唯一依据；飞书巡检表新增设备后经此自动入账，
    无需等待首次报修或人工导入。注册失败只记日志，不中断同步。
    """
    if not (device.equipment_name or device.equipment_no):
        return
    from app.modules.equipment.service.work_order_feishu import (
        _register_mirror_equipment,
    )

    try:
        await _register_mirror_equipment(db, device)
    except Exception:
        logger.exception(
            "镜像设备自动注册台账失败: %s",
            device.equipment_no or device.equipment_name or device.record_id,
        )


async def _upsert_device(
    db: AsyncSession, workshop_code: str, item: dict[str, Any]
) -> None:
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
                EquipmentInspectionFeishuDevice.workshop_code == workshop_code,
                EquipmentInspectionFeishuDevice.record_id == record_id,
                EquipmentInspectionFeishuDevice.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.equipment_name = name
        existing.equipment_no = no
        existing.last_modified_at = modified
        device_obj: Any = existing
    else:
        device_obj = EquipmentInspectionFeishuDevice(
            workshop_code=workshop_code,
            record_id=record_id,
            equipment_name=name,
            equipment_no=no,
            last_modified_at=modified,
        )
        db.add(device_obj)
    # 新增/变更设备自动注册进台账（幂等，失败不影响同步）
    await _ensure_ledger_registration(db, device_obj)


async def sync_table(
    db: AsyncSession,
    workshop_code: str,
    table_key: str,
    *,
    incremental: bool = True,
    config: InspectionFeishuEffectiveConfig | None = None,
) -> dict[str, Any]:
    """同步一个车间的一张镜像表。返回 {synced, total}；失败抛 AppException。"""
    if config is None:
        config = await get_effective_config(db, workshop_code)
    if not config.enabled:
        raise AppException(message="巡检飞书镜像同步未配置（缺少应用凭据或表格 ID）")

    table_id = _table_id(config, table_key)
    client = _build_client(config)
    state = await _get_state(db, workshop_code, table_key)

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
        hint = ""
        if "WrongTableId" in str(error) or "1254004" in str(error):
            hint = (
                "（Table ID 无效：vew 开头是视图 ID，应为 tbl 开头；"
                "在配置中重新保存可自动解析）"
            )
        raise AppException(message=f"飞书多维表格访问失败：{error}{hint}") from error

    synced = 0
    if table_key == SOURCE_DEVICES:
        for item in records:
            await _upsert_device(db, workshop_code, item)
            synced += 1
    else:
        for item in records:
            await _upsert_record(db, workshop_code, table_key, item)
            synced += 1

    if not incremental:
        # 全量对账：删除飞书侧已删的行（限定本车间本来源，不影响其他）
        keep_ids = {str(item.get("record_id")) for item in records}
        if table_key == SOURCE_DEVICES:
            model: type[EquipmentInspectionFeishuDevice] | type[
                EquipmentInspectionFeishuRecord
            ] = EquipmentInspectionFeishuDevice
            scope = [
                EquipmentInspectionFeishuDevice.workshop_code == workshop_code,
                EquipmentInspectionFeishuDevice.is_deleted == False,  # noqa: E712
            ]
        else:
            model = EquipmentInspectionFeishuRecord
            scope = [
                EquipmentInspectionFeishuRecord.workshop_code == workshop_code,
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
    if table_key != SOURCE_DEVICES:
        count_stmt = (
            select(func.count(EquipmentInspectionFeishuRecord.id))
            .where(EquipmentInspectionFeishuRecord.workshop_code == workshop_code)
            .where(EquipmentInspectionFeishuRecord.source == table_key)
            .where(EquipmentInspectionFeishuRecord.is_deleted == False)  # noqa: E712
        )
    else:
        count_stmt = select(func.count(EquipmentInspectionFeishuDevice.id)).where(
            EquipmentInspectionFeishuDevice.workshop_code == workshop_code,
            EquipmentInspectionFeishuDevice.is_deleted == False,  # noqa: E712
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
    db: AsyncSession, workshop_code: str, *, incremental: bool = True
) -> dict[str, dict[str, Any]]:
    """同步一个车间三张表；单表失败不影响其余表，结果按表返回。"""
    config = await get_effective_config(db, workshop_code)
    results: dict[str, dict[str, Any]] = {}
    for table_key in (SOURCE_TODAY, SOURCE_HISTORY, SOURCE_DEVICES):
        try:
            results[table_key] = await sync_table(
                db, workshop_code, table_key,
                incremental=incremental, config=config,
            )
        except AppException as error:
            state = await _get_state(db, workshop_code, table_key)
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
                "inspection feishu mirror sync aborted at %s/%s",
                workshop_code, table_key,
            )
            await db.rollback()
            for key in (SOURCE_TODAY, SOURCE_HISTORY, SOURCE_DEVICES):
                state = await _get_state(db, workshop_code, key)
                state.last_run_at = datetime.now(UTC)
                state.last_status = "failed"
                state.last_message = message
                results[key] = {"error": message}
            return results
    return results


async def get_sync_states(
    db: AsyncSession, workshop_code: str
) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(EquipmentInspectionFeishuSyncState).where(
                EquipmentInspectionFeishuSyncState.workshop_code == workshop_code,
                EquipmentInspectionFeishuSyncState.is_deleted == False,  # noqa: E712
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


def _cst_today(now: datetime | None = None) -> date:
    """“今日”按北京时间取日期：巡检记录 record_date 同步时即按 CST 解析，
    服务器本地时区（容器为 UTC）在 CST 00:00–08:00 会落后一天。"""
    return (now or datetime.now(_CST)).astimezone(_CST).date()


def _today_display_order(record: EquipmentInspectionFeishuRecord) -> tuple[int, str]:
    """今日列表排序：有编号设备按编号升序在前，无编号（含名称粘连的汇总行）排后。"""
    no = (record.equipment_no or "").strip().lower()
    if no:
        return (0, no)
    return (1, (record.equipment_name or "").strip().lower())


async def _list_today_records(
    db: AsyncSession,
    *,
    workshop_code: str | None,
    date_from: date | None,
    date_to: date | None,
    keyword: str | None,
    abnormal_only: bool,
    page: int,
    page_size: int,
) -> tuple[list[EquipmentInspectionFeishuRecord], int]:
    """今日巡检列表：只取有效记录行，每台设备保留最新一条。

    同设备一天可能有多条有效提交，飞书分组/引用还会产生关联行；页面按
    设备呈现当日快照，先按筛选条件过滤再去重，保证“只看异常”等仍可用。
    """
    conditions = [
        EquipmentInspectionFeishuRecord.is_deleted == False,  # noqa: E712
        EquipmentInspectionFeishuRecord.record_date == _cst_today(),
    ]
    if workshop_code:
        conditions.append(
            EquipmentInspectionFeishuRecord.workshop_code == workshop_code
        )
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
    rows = (
        await db.execute(
            select(EquipmentInspectionFeishuRecord)
            .where(*conditions)
            .order_by(
                EquipmentInspectionFeishuRecord.last_modified_at.desc().nulls_last(),
                EquipmentInspectionFeishuRecord.record_id.desc(),
            )
        )
    ).scalars().all()
    latest: dict[str, EquipmentInspectionFeishuRecord] = {}
    for record in _valid_today_rows(rows):
        key = _device_key(record.equipment_no, record.equipment_name)
        if key == _NAME_KEY_PREFIX:
            # 无编号也无名称的行按记录自身保留，避免互相覆盖
            key = record.record_id
        if key not in latest:
            latest[key] = record
    items = sorted(latest.values(), key=_today_display_order)
    total = len(items)
    start = (page - 1) * page_size
    return items[start : start + page_size], total


async def list_records(
    db: AsyncSession,
    *,
    workshop_code: str | None = None,
    source: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    keyword: str | None = None,
    abnormal_only: bool = False,
    process_status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[EquipmentInspectionFeishuRecord], int]:
    if source == SOURCE_TODAY:
        # 今日口径：仅当天（CST）+ 有效行按设备去重（每设备最新一条）
        return await _list_today_records(
            db,
            workshop_code=workshop_code,
            date_from=date_from,
            date_to=date_to,
            keyword=keyword,
            abnormal_only=abnormal_only,
            page=page,
            page_size=page_size,
        )
    conditions = [EquipmentInspectionFeishuRecord.is_deleted == False]  # noqa: E712
    # workshop 缺省 = 跨车间查询（设备详情抽屉按设备编号聚合各车间记录）
    if workshop_code:
        conditions.append(
            EquipmentInspectionFeishuRecord.workshop_code == workshop_code
        )
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
    else:
        # 多设备合并填写的原始行（处理状态=已拆分，已被逐设备行取代）不参与
        # 巡检记录/跨车间聚合展示；未启用该字段的表（NULL）不受影响
        conditions.append(
            EquipmentInspectionFeishuRecord.process_status.is_distinct_from(
                _STATUS_SPLIT
            )
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


# 上午/下午检查项列：任一列有值即视为该时段已巡
_AM_COLUMNS = (
    "am_clean", "am_lubrication", "am_fastening", "am_sealing",
    "am_vibration", "am_sound", "am_surface",
)
_PM_COLUMNS = (
    "pm_clean", "pm_lubrication", "pm_fastening", "pm_sealing",
    "pm_vibration", "pm_sound", "pm_surface",
)
_NAME_KEY_PREFIX = "N:"


def _device_key(equipment_no: str | None, equipment_name: str | None) -> str:
    """设备匹配键：优先编号；无编号回退名称（加前缀避免与编号撞键）。"""
    no = (equipment_no or "").strip()
    if no:
        return no
    return _NAME_KEY_PREFIX + (equipment_name or "").strip()


def _valid_today_rows(
    records: Sequence[EquipmentInspectionFeishuRecord],
) -> list[EquipmentInspectionFeishuRecord]:
    """今日表的有效记录行：排除飞书分组/引用产生的关联行（无处理状态）和
    多设备合并填写后被拆分的原始行（处理状态=已拆分，已被逐设备行取代）。

    表未启用“处理状态”字段时没有任何行带该值，回退为全部行有效，
    兼容历史表和未配置该字段的旧车间表。
    """
    rows = list(records)
    if not any((r.process_status or "").strip() for r in rows):
        return rows
    return [
        r
        for r in rows
        if (value := (r.process_status or "").strip())
        and value != _STATUS_SPLIT
    ]


def _period_filled(
    record: EquipmentInspectionFeishuRecord, columns: tuple[str, ...]
) -> bool:
    return any((getattr(record, col) or "").strip() for col in columns)


async def _today_device_progress(
    db: AsyncSession, workshop_code: str
) -> dict[str, dict[str, Any]]:
    """今日有效记录按设备聚合：status（已巡/异常）与上午、下午是否有勾。

    匹配键优先设备编号；飞书巡检表部分设备无编号（如尾气塔、泵类），
    其记录行同样无编号，只能按名称匹配。名称粘连的汇总行匹配不到
    设备，天然被排除。
    """
    today = _cst_today()
    rows = (
        await db.execute(
            select(EquipmentInspectionFeishuRecord)
            .where(
                EquipmentInspectionFeishuRecord.workshop_code == workshop_code,
                EquipmentInspectionFeishuRecord.record_date == today,
                EquipmentInspectionFeishuRecord.is_deleted == False,  # noqa: E712
            )
            .order_by(
                EquipmentInspectionFeishuRecord.last_modified_at.desc().nulls_last(),
                EquipmentInspectionFeishuRecord.record_id.desc(),
            )
        )
    ).scalars().all()
    progress: dict[str, dict[str, Any]] = {}
    for record in _valid_today_rows(rows):
        key = _device_key(record.equipment_no, record.equipment_name)
        if key == _NAME_KEY_PREFIX:
            continue
        entry = progress.setdefault(
            key, {"status": "inspected", "am": False, "pm": False}
        )
        if record.has_abnormal:
            entry["status"] = "abnormal"
        entry["am"] = entry["am"] or _period_filled(record, _AM_COLUMNS)
        entry["pm"] = entry["pm"] or _period_filled(record, _PM_COLUMNS)
    return progress


async def _last_inspected_dates(
    db: AsyncSession, workshop_code: str
) -> dict[str, date]:
    """每台设备（编号/名称回退键）在镜像里的最近一次巡检日期。"""
    key_expr = func.coalesce(
        func.nullif(func.btrim(EquipmentInspectionFeishuRecord.equipment_no), ""),
        func.concat(
            _NAME_KEY_PREFIX,
            func.coalesce(
                func.btrim(EquipmentInspectionFeishuRecord.equipment_name), ""
            ),
        ),
    )
    rows = (
        await db.execute(
            select(
                key_expr, func.max(EquipmentInspectionFeishuRecord.record_date)
            ).where(
                EquipmentInspectionFeishuRecord.workshop_code == workshop_code,
                EquipmentInspectionFeishuRecord.is_deleted == False,  # noqa: E712
                EquipmentInspectionFeishuRecord.record_date.isnot(None),
            ).group_by(key_expr)
        )
    ).all()
    return {key: last for key, last in rows}


async def list_devices(
    db: AsyncSession, workshop_code: str, *, keyword: str | None = None
) -> dict[str, Any]:
    """巡检设备清单 + 台账信息（按编号关联，互不修改）。

    返回 {"date": 今日口径日期, "items": [...]}；每台设备带 today_status
    与 last_inspected_date（镜像里最近一次巡检日期，从未巡检为 None）。
    """
    conditions = [
        EquipmentInspectionFeishuDevice.workshop_code == workshop_code,
        EquipmentInspectionFeishuDevice.is_deleted == False,  # noqa: E712
    ]
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

    # 今日状态：已巡（有记录）/ 异常（含 ×）/ 未巡；无编号设备按名称匹配
    progress = await _today_device_progress(db, workshop_code)
    last_dates = await _last_inspected_dates(db, workshop_code)

    return {
        "date": _cst_today(),
        "items": [
            {
                "record_id": device.record_id,
                "equipment_name": device.equipment_name,
                "equipment_no": device.equipment_no,
                "model": ledger_map.get(device.equipment_no, {}).get("model"),
                "location_name": ledger_map.get(device.equipment_no, {}).get(
                    "location_name"
                ),
                "in_ledger": device.equipment_no in ledger_nos,
                "today_status": progress.get(
                    _device_key(device.equipment_no, device.equipment_name), {}
                ).get("status", "pending"),
                "last_inspected_date": last_dates.get(
                    _device_key(device.equipment_no, device.equipment_name)
                ),
            }
            for device in devices
        ],
    }


async def today_summary(db: AsyncSession, workshop_code: str) -> dict[str, Any]:
    """今日进度：应巡（档案表）/ 已巡 / 异常 / 上午、下午完成数。

    无编号设备按名称匹配记录；已巡、异常与上下午细分都基于有效记录行。
    """
    devices = (
        await db.execute(
            select(
                EquipmentInspectionFeishuDevice.equipment_no,
                EquipmentInspectionFeishuDevice.equipment_name,
            ).where(
                EquipmentInspectionFeishuDevice.workshop_code == workshop_code,
                EquipmentInspectionFeishuDevice.is_deleted == False,  # noqa: E712
            )
        )
    ).all()
    progress = await _today_device_progress(db, workshop_code)
    inspected = 0
    abnormal = 0
    am_done = 0
    pm_done = 0
    for equipment_no, equipment_name in devices:
        entry = progress.get(_device_key(equipment_no, equipment_name))
        if not entry:
            continue
        inspected += 1
        if entry["status"] == "abnormal":
            abnormal += 1
        if entry["am"]:
            am_done += 1
        if entry["pm"]:
            pm_done += 1
    return {
        "date": _cst_today(),
        "total_devices": len(devices),
        "inspected": inspected,
        "abnormal": abnormal,
        "am_inspected": am_done,
        "pm_inspected": pm_done,
    }


async def today_summaries_all(db: AsyncSession) -> list[dict[str, Any]]:
    """各已启用镜像车间的今日巡检进度汇总（设备汇总页）。"""
    summaries: list[dict[str, Any]] = []
    for workshop_code in await list_enabled_workshops(db):
        summary = await today_summary(db, workshop_code)
        summaries.append({"workshop_code": workshop_code, **summary})
    return summaries
