"""质量检验-仪器管理 飞书子表 -> 本地镜像回拉与读取。

照搬物品管理镜像（inspection_items_mirror）模式，存储复用通用快照/行表
quality.quality_items_page_snapshots / quality.quality_items_page_rows
（page_key = 仪器实体编码，如 qc_instr_equipment；cells 以飞书中文列名为键，
值为前端 renderFeishuValue 可直接渲染的结构）：
- 全量轮：GET /records 翻页拉全表 + 列元数据，写 snapshot.columns，upsert
  全部行并对账软删远端消失的行；
- 增量轮：records/search 单页双路（业务日期降序 + last_modified_time 降序），
  按上次同步水线过滤；不做删除对账（更早的历史修改与删除由每日全量兜底）；
- 读取：列表镜像优先，飞书不可达/未同步时由上层降级实时读。

列结构完全取自飞书字段元数据（含名称/类型/选项/只读），因此飞书表后续新增
列（例如新的附件列）无需改代码即可出现在页面上；附件列的值保留
[{name,url,file_token,type,size}]，页面附件预览走后端代理端点。

凭证与实体配置由质量模块 runtime 解析后显式传给平台 BitableClient，符合
app/platform/integrations/feishu 平台边界。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.quality.models.feishu_settings import QualityFeishuEntitySetting
from app.modules.quality.models.inspection_items_mirror import (
    QualityItemsPageRow,
)
from app.modules.quality.repository import inspection_items_mirror as repo
from app.modules.quality.service import quality_feishu_sync as feishu_sync_service
from app.modules.quality.service.inspection_helpers import _smart_normalize_value
from app.modules.quality.service.quality_feishu_pages import _resolve_runtime_entity
from app.platform.integrations.feishu.bitable import BitableClient

logger = logging.getLogger(__name__)

# 仪器管理全部飞书子表（= 本地镜像页键）；两张 Base：设备台账 5 表 + QC 校验计划 3 表
INSTRUMENT_MIRROR_ENTITIES: tuple[str, ...] = (
    "qc_instr_equipment",
    "qc_instr_maintenance",
    "qc_instr_repair",
    "qc_instr_contracts",
    "qc_instr_plans",
    "qc_instr_calibration",
    "qc_instr_cal_plan",
    "qc_instr_cal_external",
)

INSTRUMENT_PAGE_TITLES: dict[str, str] = {
    "qc_instr_equipment": "设备数据管理",
    "qc_instr_maintenance": "设备维护保养记录",
    "qc_instr_repair": "设备维修记录",
    "qc_instr_contracts": "设备维保合同",
    "qc_instr_plans": "QC检测仪器维护保养周期表",
    "qc_instr_calibration": "内校汇总",
    "qc_instr_cal_plan": "内部校验计划",
    "qc_instr_cal_external": "外部校准、检定",
}

# 增量业务日期排序字段（表内最贴近"新增即最新"的日期列）；
# 无日期列的页只走 last_modified_time 路。飞书不支持按 last_modified_time
# 排序/过滤，故用业务日期降序页 + last_modified 降序页双路取并集。
INSTRUMENT_DATE_SORT_FIELDS: dict[str, str] = {
    "qc_instr_equipment": "入厂日期",
    "qc_instr_maintenance": "完成日期",
    "qc_instr_repair": "维修时间",
    "qc_instr_contracts": "购买维保合同时间",
    "qc_instr_calibration": "校验时间",
    "qc_instr_cal_plan": "计划校验时间",
    "qc_instr_cal_external": "检定日期",
}

# 只读列 ui_type（仅标记可编辑性，仍作为只读列展示）—— 与 inspection_feishu_crud 一致
_READ_ONLY_UI_TYPES = {
    "Attachment",
    "Lookup",
    "Formula",
    "CreatedTime",
    "ModifiedTime",
    "CreatedUser",
    "ModifiedUser",
    "Button",
    "AutoNumber",
}

# 飞书「按钮」列既无值也不可编辑，不进入镜像列（避免页面上出现空列）; 3001 = 按钮
_HIDDEN_UI_TYPES = {"Button"}
_BUTTON_FIELD_TYPE = 3001

# 内部保留键前缀（不进入 cells 的业务列）
_INTERNAL_PREFIX = "__"


# ── 归一化 ────────────────────────────────────────────────────────────


def _extract_select_options(field: dict[str, Any]) -> list[dict[str, str]]:
    """抽取选项 id→name 列表。

    普通单选/多选在 property.options；公式/查找返回的选项列在
    property.type.ui_property.options（值回读为选项 id，需映射回文字）。
    """
    prop = field.get("property")
    if not isinstance(prop, dict):
        return []
    candidates: list[Any] = []
    opts = prop.get("options")
    if isinstance(opts, list):
        candidates = opts
    inner = prop.get("type")
    if isinstance(inner, dict):
        ui_prop = inner.get("ui_property")
        if isinstance(ui_prop, dict) and isinstance(ui_prop.get("options"), list):
            candidates = ui_prop["options"]
    result: list[dict[str, str]] = []
    for opt in candidates:
        if isinstance(opt, dict) and opt.get("id"):
            result.append({"id": str(opt["id"]), "name": str(opt.get("name") or "")})
    return result


def _is_hidden_field(field: dict[str, Any]) -> bool:
    ui_type = str(field.get("ui_type") or "")
    if ui_type in _HIDDEN_UI_TYPES:
        return True
    return field.get("type") == _BUTTON_FIELD_TYPE


def _build_columns(field_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """飞书 list_fields -> 列结构（含全列 + 选项映射，供前端动态展示全部列）。"""
    columns: list[dict[str, Any]] = []
    for field in field_items:
        field_name = str(field.get("field_name") or "").strip()
        if not field_name or _is_hidden_field(field):
            continue
        ui_type = str(field.get("ui_type") or field.get("type") or "")
        options = _extract_select_options(field)
        column: dict[str, Any] = {
            "key": field_name,
            "title": field_name,
            "ui_type": ui_type,
            "field_type": field.get("type"),
            "is_primary": bool(field.get("is_primary")),
            "editable": ui_type not in _READ_ONLY_UI_TYPES,
        }
        # 公式列的结果类型（如公式返回日期/进度），供前端按类型渲染
        prop = field.get("property")
        if isinstance(prop, dict) and isinstance(prop.get("type"), dict):
            result_ui_type = str(prop["type"].get("ui_type") or "")
            if result_ui_type:
                column["result_ui_type"] = result_ui_type
        if options:
            column["options"] = options
        columns.append(column)
    return columns


def _resolve_option_value(value: Any, options: list[dict[str, str]]) -> Any:
    """把单选/多选的选项 id（或公式返回的选项 id）映射为选项名。"""
    if not options:
        return value
    id_to_name = {opt["id"]: opt["name"] for opt in options if opt.get("id")}
    if isinstance(value, str):
        return id_to_name.get(value, value)
    if isinstance(value, list):
        return "、".join(
            id_to_name.get(str(v), str(v)) for v in value if v not in (None, "")
        )
    return value


def _normalize_record_cells(
    record: dict[str, Any],
    columns: list[dict[str, Any]],
) -> dict[str, Any]:
    """把飞书记录整行归一化成 cells（中文列名 -> 前端可渲染结构）。"""
    fields = record.get("fields") or {}
    cells: dict[str, Any] = {}
    for column in columns:
        key = column["key"]
        raw = fields.get(key)
        options = column.get("options")
        resolved = _resolve_option_value(raw, options) if options else raw
        cells[key] = _smart_normalize_value(resolved)
    # 飞书记录修改时间（ISO），前端 updated_at 数据源
    modified_dt = feishu_sync_service._get_record_modified_at(record)
    if modified_dt is not None:
        cells[f"{_INTERNAL_PREFIX}last_modified"] = modified_dt.isoformat()
    return cells


def _build_search_text(cells: dict[str, Any]) -> str:
    parts: list[str] = []
    for value in cells.values():
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, (int, float)):
            parts.append(str(value))
        elif isinstance(value, list):
            parts.extend(str(v) for v in value if isinstance(v, (str, int, float)))
    return " ".join(parts).lower()


# ── 飞书拉取 ──────────────────────────────────────────────────────────


async def _fetch_or_fail(
    fetchable: Awaitable[list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    try:
        return await fetchable
    except AppException:
        raise
    except Exception as exc:
        raise AppException(
            message="从飞书拉取仪器数据失败：无法连接飞书或访问该多维表格，"
            "请检查网络及质量模块飞书应用对该 Base 的协作者权限",
            status_code=503,
        ) from exc


async def _fetch_full_records(
    client: BitableClient, table_id: str
) -> list[dict[str, Any]]:
    """全量翻页：GET /records（records/search 无 filter 翻页失效，见模块文档）。"""
    records: list[dict[str, Any]] = []
    page_token = ""
    for _page_index in range(200):
        params: dict[str, Any] = {
            "page_size": 500,
            "field_name_type": "name",
            "automatic_fields": True,
        }
        if page_token:
            params["page_token"] = page_token
        data = await client.client.request(
            "GET",
            f"/bitable/v1/apps/{client.app_token}/tables/{table_id}/records",
            params=params,
            timeout=60.0,
        )
        records.extend(
            item for item in (data.get("items") or []) if isinstance(item, dict)
        )
        if not data.get("has_more"):
            return records
        remote_total = data.get("total") or 0
        if remote_total and len(records) >= remote_total:
            return records[: int(remote_total)]
        page_token = str(data.get("page_token") or "")
        if not page_token:
            return records
    return records


async def _search_sorted_page(
    client: BitableClient, table_id: str, sort_field: str
) -> list[dict[str, Any]]:
    data = await client.client.request(
        "POST",
        f"/bitable/v1/apps/{client.app_token}/tables/{table_id}/records/search",
        params={
            "page_size": 500,
            "field_name_type": "name",
            "automatic_fields": True,
        },
        json={"sort": [{"field_name": sort_field, "desc": True}]},
        timeout=60.0,
    )
    return [item for item in (data.get("items") or []) if isinstance(item, dict)]


def _record_is_new(
    record: dict[str, Any], sort_field: str | None, day_ms: float, ms: float
) -> bool:
    fields = record.get("fields") or {}
    if sort_field:
        date_value = fields.get(sort_field)
        if isinstance(date_value, (int, float)) and date_value >= day_ms:
            return True
    modified_ms = record.get("last_modified_time")
    if isinstance(modified_ms, (int, float)) and modified_ms >= ms:
        return True
    return False


async def _fetch_incremental_records(
    client: BitableClient,
    table_id: str,
    *,
    sort_field: str | None,
    last_synced_at: datetime,
) -> list[dict[str, Any]]:
    """真增量：records/search 单页双路（业务日期降序 + last_modified_time 降序）。

    无 filter 翻页失效，故每路各取一页（不翻页），客户端按水位过滤后按 record_id
    去重。路一（业务日期）仅在该页配了日期排序字段时启用；无日期字段只走
    last_modified 路。日期路排序被拒必抛错（上层回退全量），last_modified 路容错跳过。
    """
    last_synced_ms = last_synced_at.timestamp() * 1000
    # 业务日期为当天零点毫秒：水线用上次同步当天零点，否则当天新数据永远拉不到
    day_start = datetime.combine(
        last_synced_at.date(), datetime.min.time(), tzinfo=last_synced_at.tzinfo
    )
    last_synced_day_ms = day_start.timestamp() * 1000

    routes: list[str] = []
    if sort_field:
        routes.append(sort_field)
    routes.append("last_modified_time")

    merged: dict[str, dict[str, Any]] = {}
    for route_index, sort_name in enumerate(routes):
        try:
            page = await _search_sorted_page(client, table_id, sort_name)
        except Exception:
            if route_index == 0 and sort_field:
                raise
            logger.debug(
                "instrument incremental sort %s unsupported: %s", sort_name, table_id
            )
            continue
        for record in page:
            if not _record_is_new(
                record, sort_field, last_synced_day_ms, last_synced_ms
            ):
                continue
            record_id = str(record.get("record_id") or "")
            if record_id:
                merged[record_id] = record
    return list(merged.values())


def _record_modified_ms(record: dict[str, Any]) -> float | None:
    modified = record.get("last_modified_time")
    return float(modified) if isinstance(modified, (int, float)) else None


def _is_record_newer(record: dict[str, Any], watermark_ms: float) -> bool:
    if not watermark_ms:
        return True
    modified = _record_modified_ms(record)
    if modified is None:
        return True
    return modified >= watermark_ms


async def _fetch_field_items(
    client: BitableClient, table_id: str
) -> list[dict[str, Any]]:
    try:
        return await client.list_fields(table_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("instrument mirror list_fields failed for %s: %s", table_id, exc)
        return []


# ── 同步编排 ──────────────────────────────────────────────────────────


async def _mark_sync_status(
    db: AsyncSession,
    entity_code: str,
    *,
    ok: bool,
    error: str | None = None,
) -> None:
    """把同步结果写回实体配置行（质量设置-飞书设置「最近状态」列的数据源）。"""
    model = (
        await db.execute(
            select(QualityFeishuEntitySetting).where(
                QualityFeishuEntitySetting.entity_code == entity_code,
                QualityFeishuEntitySetting.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()
    if model is None:
        return
    model.last_sync_status = "success" if ok else "failed"
    model.last_sync_error = error
    model.last_synced_at = datetime.now(UTC)
    await db.commit()


async def sync_instrument_page(
    db: AsyncSession,
    entity_code: str,
    *,
    incremental: bool = True,
) -> dict[str, int]:
    """同步单个仪器子表到本地镜像。返回 {synced, removed, total}。

    incremental=True 且已有快照时走增量水位（只写变更行、不删历史）；
    否则全量（含删除对账）。飞书不可达抛 AppException，交由调度器记录。
    """
    if entity_code not in INSTRUMENT_MIRROR_ENTITIES:
        raise AppException(
            message=f"未知的仪器镜像实体：{entity_code}", status_code=400
        )

    label = INSTRUMENT_PAGE_TITLES.get(entity_code, entity_code)
    try:
        runtime, entity = await _resolve_runtime_entity(
            db, entity_code, direction="pull"
        )
    except AppException as exc:
        await _mark_sync_status(db, entity_code, ok=False, error=str(exc))
        raise
    client = BitableClient(
        app_token=entity.app_token,
        app_id=runtime.app_id,
        app_secret=runtime.app_secret,
    )
    table_id = feishu_sync_service._require_table_id(entity)

    prev_snapshot = await repo.get_snapshot(db, entity_code)
    use_incremental = bool(
        incremental and prev_snapshot is not None and prev_snapshot.total_rows > 0
    )

    field_items = await _fetch_or_fail(_fetch_field_items(client, table_id))
    columns = _build_columns(field_items)
    if not columns:
        # 列结构拉取失败时禁止降级写入：只有部分列的 cells 会在增量比对中
        # 把镜像整行数据覆盖掉（读路径用 snapshot.columns，不受此影响）
        raise AppException(
            message=f"获取仪器表列结构失败，已跳过本次同步：{entity_code}",
            status_code=503,
        )

    if use_incremental and prev_snapshot is not None:
        sort_field = INSTRUMENT_DATE_SORT_FIELDS.get(entity_code)
        try:
            records = await _fetch_or_fail(
                _fetch_incremental_records(
                    client,
                    table_id,
                    sort_field=sort_field,
                    last_synced_at=prev_snapshot.last_synced_at,
                )
            )
        except Exception as exc:  # noqa: BLE001
            # 业务日期排序被飞书拒绝 → 回退全量 + 客户端水位过滤
            logger.info(
                "instrument incremental fell back to full (%s): %s", entity_code, exc
            )
            records = await _fetch_or_fail(_fetch_full_records(client, table_id))
            watermark_ms = prev_snapshot.last_synced_at.timestamp() * 1000
            records = [
                record for record in records if _is_record_newer(record, watermark_ms)
            ]
    else:
        records = await _fetch_or_fail(_fetch_full_records(client, table_id))

    now = datetime.now(UTC)
    row_models: list[QualityItemsPageRow] = []
    seen_ids: set[str] = set()
    for index, record in enumerate(records, start=1):
        record_id = str(record.get("record_id") or "")
        if not record_id or record_id in seen_ids:
            continue
        seen_ids.add(record_id)
        cells = _normalize_record_cells(record, columns)
        row_models.append(
            QualityItemsPageRow(
                page_snapshot_id=None,  # 快照 upsert 后回填
                source_record_id=record_id,
                row_order=index,
                cells=cells,
                search_text=_build_search_text(cells),
                last_synced_at=now,
            )
        )

    snapshot = await repo.upsert_snapshot(
        db,
        page_key=entity_code,
        page_title=label,
        table_name=label,
        table_id=table_id,
        columns=columns,
        total_rows=len(row_models),
        source="feishu_bitable",
        last_synced_at=now,
        last_error=None,
    )
    for row in row_models:
        row.page_snapshot_id = snapshot.id

    if use_incremental:
        await repo.upsert_rows_incremental(db, snapshot.id, row_models)
        total_rows = await repo.count_rows(db, snapshot.id)
        snapshot.total_rows = total_rows
        await db.flush()
    else:
        await repo.upsert_rows_full(db, snapshot.id, row_models)

    await db.commit()
    logger.info(
        "instrument mirror sync entity=%s incremental=%s rows=%d",
        entity_code,
        use_incremental,
        len(row_models),
    )
    return {"synced": len(row_models), "removed": 0, "total": len(row_models)}


# ── 读取（列表页共用）──────────────────────────────────────────────────


def _row_to_item(row: QualityItemsPageRow, columns: list[str]) -> dict[str, Any]:
    item: dict[str, Any] = {
        "record_id": row.source_record_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": (
            row.cells.get(f"{_INTERNAL_PREFIX}last_modified")
            if isinstance(row.cells, dict)
            else None
        )
        or (row.updated_at.isoformat() if row.updated_at else None),
    }
    cells = row.cells or {}
    for key in columns:
        item[key] = cells.get(key)
    return item


async def get_instrument_mirror_fields(
    db: AsyncSession, entity_code: str
) -> list[str]:
    """读取镜像快照列结构；未同步返回空列表（由上层实时兜底）。"""
    snapshot = await repo.get_snapshot(db, entity_code)
    if snapshot is None:
        return []
    return [str(col.get("key")) for col in (snapshot.columns or []) if col.get("key")]


async def list_instrument_mirror(
    db: AsyncSession,
    entity_code: str,
    *,
    keyword: str | None = None,
    filters: dict[str, str] | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """从本地镜像读取仪器列表，返回结构与实时 _list_feishu 对齐。

    无镜像快照时返回 configured=False 空页（由上层触发同步或降级实时读）。
    过滤/排序/分页下沉 SQL（list_rows_filtered），避免整表载入内存。
    """
    snapshot = await repo.get_snapshot(db, entity_code)
    if snapshot is None:
        return {
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "configured": False,
            "fields": [],
            "last_sync_time": None,
        }

    columns = [
        str(col.get("key")) for col in (snapshot.columns or []) if col.get("key")
    ]
    rows, total = await repo.list_rows_filtered(
        db,
        snapshot.id,
        columns=columns,
        keyword=keyword,
        filters=filters,
        updated_sort_field=f"{_INTERNAL_PREFIX}last_modified",
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    items = [_row_to_item(row, columns) for row in rows]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "configured": True,
        "fields": list(columns),
        "last_sync_time": snapshot.last_synced_at.isoformat()
        if snapshot.last_synced_at
        else None,
    }
