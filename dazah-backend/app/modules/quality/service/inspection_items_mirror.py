"""质量检验-物品管理 飞书子表 -> 本地镜像回拉与读取。

照搬仓储 material_page_rows / 供应商资质镜像模式：物品三张飞书多维表格
（qc_items_inventory / qc_items_inbound / qc_items_outbound）由"每次实时直读
飞书"改为读本地镜像表 quality.quality_items_page_rows（cells 以飞书中文列名
为键，值为前端 renderFeishuValue 可直接渲染的结构）：
- 全量轮：GET /records 翻页拉全表 + 列元数据，写 snapshot.columns，upsert
  全部行并对账软删远端消失的行；
- 增量轮：复用全量翻页 + 按 last_modified_time 水位过滤，只写达到水位的行，
  不做删除对账（对齐仓储/供应商镜像实测：records/search 无 filter 翻页失效、
  filter/sort 对自动字段返回 InvalidFilter/InvalidSort）；
- 入库/出库页"物资名"双向关联列在读取时用本地库存镜像索引回填物资名称/
  规格型号/当前库存（替代旧的实时拉库存表）。

凭证与实体配置由质量模块 runtime 解析后显式传给平台 BitableClient，符合
app/platform/integrations/feishu 平台边界。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.quality.models.inspection_items_mirror import (
    QualityItemsPageRow,
)
from app.modules.quality.repository import inspection_items_mirror as repo
from app.modules.quality.service import quality_feishu_sync as feishu_sync_service
from app.modules.quality.service.inspection_helpers import _smart_normalize_value
from app.modules.quality.service.inspection_items_equipment import (
    INBOUND_FIELDS,
    ITEMS_FIELDS,
    OUTBOUND_FIELDS,
)
from app.modules.quality.service.quality_feishu_pages import _resolve_runtime_entity
from app.platform.integrations.feishu.bitable import BitableClient

logger = logging.getLogger(__name__)

# 物品三页镜像键 = 飞书实体编码
PAGE_INVENTORY = "qc_items_inventory"
PAGE_INBOUND = "qc_items_inbound"
PAGE_OUTBOUND = "qc_items_outbound"
ITEMS_MIRROR_PAGES: tuple[str, ...] = (PAGE_INVENTORY, PAGE_INBOUND, PAGE_OUTBOUND)

# 页标题（与 quality_feishu_settings PREFILLS 表名一致）
PAGE_TITLES: dict[str, str] = {
    PAGE_INVENTORY: "关键物资库存",
    PAGE_INBOUND: "关键物资入库明细",
    PAGE_OUTBOUND: "关键物资领用明细",
}

# 回退列清单（列元数据拉取失败时保证不空屏，对齐旧白名单）
PAGE_FALLBACK_FIELDS: dict[str, list[str]] = {
    PAGE_INVENTORY: ITEMS_FIELDS,
    PAGE_INBOUND: INBOUND_FIELDS,
    PAGE_OUTBOUND: OUTBOUND_FIELDS,
}

# 只读列 ui_type（不展示在筛选/编辑，仍展示为只读列）—— 与 inspection_feishu_crud 一致
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

# 内部保留键前缀（不进入 cells）
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


def _build_columns(field_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """飞书 list_fields -> 列结构（含全列 + 选项映射，供前端动态展示全部列）。"""
    columns: list[dict[str, Any]] = []
    for field in field_items:
        field_name = str(field.get("field_name") or "").strip()
        if not field_name:
            continue
        ui_type = str(field.get("ui_type") or field.get("type") or "")
        options = _extract_select_options(field)
        column: dict[str, Any] = {
            "key": field_name,
            "title": field_name,
            "ui_type": ui_type,
            "field_type": field.get("type"),
            "editable": ui_type not in _READ_ONLY_UI_TYPES,
        }
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
            id_to_name.get(str(v), str(v))
            for v in value
            if v not in (None, "")
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
    # 双向链接原始 record_ids（前端不可见，供物资名回填索引使用）
    link_ids = fields.get("物资名")
    if isinstance(link_ids, dict):
        raw_ids = link_ids.get("link_record_ids")
        if isinstance(raw_ids, list) and raw_ids:
            cells[f"{_INTERNAL_PREFIX}link_record_ids"] = [str(x) for x in raw_ids]
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
            message="从飞书拉取物品数据失败：无法连接飞书或访问该多维表格，"
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


async def _fetch_field_items(
    client: BitableClient, table_id: str
) -> list[dict[str, Any]]:
    try:
        return await client.list_fields(table_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("items mirror list_fields failed for %s: %s", table_id, exc)
        return []


# 业务日期排序字段（用于 records/search 单页增量；库存表无日期列，走 last_modified 路）
ITEMS_DATE_SORT_FIELDS: dict[str, str] = {
    PAGE_INBOUND: "入库日期",
    PAGE_OUTBOUND: "领用日期",
}


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


async def _fetch_incremental_records(
    client: BitableClient,
    table_id: str,
    *,
    sort_field: str | None,
    last_synced_at: datetime,
) -> list[dict[str, Any]]:
    """真增量：records/search 单页双路（业务日期降序 + last_modified_time 降序）。

    对齐仓储 fetch_feishu_table_records_incremental：无 filter 翻页失效，故每路各取
    一页（不翻页），客户端按水位过滤后按 record_id 去重。路一（业务日期）仅在该页配
    了日期排序字段时启用；无日期字段只走 last_modified 路。日期路排序被拒必抛错（上层
    回退全量），last_modified 路容错跳过。
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
                "items incremental sort %s unsupported: %s", sort_name, table_id
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


# ── 同步编排 ──────────────────────────────────────────────────────────


async def sync_items_page(
    db: AsyncSession,
    page_key: str,
    *,
    incremental: bool = True,
) -> dict[str, int]:
    """同步单个物品页到本地镜像。返回 {synced, removed, total}。

    incremental=True 且已有快照时走增量水位（只写变更行、不删历史）；
    否则全量（含删除对账）。飞书不可达抛 AppException，交由调度器记录。
    """
    if page_key not in ITEMS_MIRROR_PAGES:
        raise AppException(message=f"未知的物品镜像页：{page_key}", status_code=400)

    runtime, entity = await _resolve_runtime_entity(db, page_key, direction="pull")
    client = BitableClient(
        app_token=entity.app_token,
        app_id=runtime.app_id,
        app_secret=runtime.app_secret,
    )
    table_id = feishu_sync_service._require_table_id(entity)

    prev_snapshot = await repo.get_snapshot(db, page_key)
    use_incremental = bool(
        incremental and prev_snapshot is not None and prev_snapshot.total_rows > 0
    )

    field_items = await _fetch_or_fail(_fetch_field_items(client, table_id))
    columns = _build_columns(field_items) or _fallback_columns(page_key)

    if use_incremental and prev_snapshot is not None:
        sort_field = ITEMS_DATE_SORT_FIELDS.get(page_key)
        try:
            records = await _fetch_incremental_records(
                client,
                table_id,
                sort_field=sort_field,
                last_synced_at=prev_snapshot.last_synced_at,
            )
        except Exception as exc:  # noqa: BLE001
            # 业务日期排序被飞书拒绝 → 回退全量 + 客户端水位过滤（仅此类页兜底）
            logger.info("items incremental fell back to full (%s): %s", page_key, exc)
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
        page_key=page_key,
        page_title=PAGE_TITLES.get(page_key, page_key),
        table_name=PAGE_TITLES.get(page_key, page_key),
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
        "items mirror sync page=%s incremental=%s rows=%d",
        page_key,
        use_incremental,
        len(row_models),
    )
    return {"synced": len(row_models), "removed": 0, "total": len(row_models)}


def _fallback_columns(page_key: str) -> list[dict[str, Any]]:
    return [
        {
            "key": name,
            "title": name,
            "ui_type": "",
            "field_type": None,
            "editable": True,
        }
        for name in PAGE_FALLBACK_FIELDS.get(page_key, [])
    ]


def _is_record_newer(record: dict[str, Any], watermark_ms: float) -> bool:
    if not watermark_ms:
        return True
    modified = _record_modified_ms(record)
    if modified is None:
        return True
    return modified >= watermark_ms


# ── 读取（列表页/仪表盘共用）────────────────────────────────────────────


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
    item["__link_record_ids"] = cells.get(f"{_INTERNAL_PREFIX}link_record_ids") or []
    return item


async def _load_page(
    db: AsyncSession, page_key: str
) -> tuple[Any, list[dict[str, Any]], list[QualityItemsPageRow], int]:
    snapshot = await repo.get_snapshot(db, page_key)
    if snapshot is None:
        return None, [], [], 0
    columns = [
        str(col.get("key")) for col in (snapshot.columns or []) if col.get("key")
    ]
    rows, total = await repo.list_rows(db, snapshot.id, limit=None)
    return snapshot, columns, rows, total


async def _inventory_link_index(
    db: AsyncSession,
) -> dict[str, dict[str, Any]]:
    """库存镜像 record_id -> 行，供入出库"物资名"link 回填。"""
    _, columns, rows, _total = await _load_page(db, PAGE_INVENTORY)
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = _row_to_item(row, columns)
        index[row.source_record_id] = item
    return index


def _fill_from_inventory(
    item: dict[str, Any],
    link_record_ids: list[str],
    inventory_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if item.get("物资名称") and item.get("规格型号"):
        return item
    if not link_record_ids:
        return item
    inv = inventory_index.get(link_record_ids[0])
    if not inv:
        return item
    if not item.get("物资名称"):
        item["物资名称"] = inv.get("物资名称") or inv.get("物资名（规格）")
    if not item.get("规格型号"):
        item["规格型号"] = inv.get("规格型号")
    if not item.get("当前库存"):
        item["当前库存"] = inv.get("当前库存")
    return item


async def list_items_mirror(
    db: AsyncSession,
    page_key: str,
    *,
    keyword: str | None = None,
    filters: dict[str, str] | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """从本地镜像读取物品页列表，返回结构与旧 _list_feishu 对齐。

    无镜像行时返回 configured=False 空页（降级由路由层处理）。
    """
    snapshot, columns, rows, total = await _load_page(db, page_key)
    if snapshot is None:
        return {"items": [], "total": 0, "page": page, "page_size": page_size,
                "configured": False, "fields": [], "last_sync_time": None}

    inventory_index = (
        await _inventory_link_index(db)
        if page_key in (PAGE_INBOUND, PAGE_OUTBOUND)
        else {}
    )

    items: list[dict[str, Any]] = []
    for row in rows:
        item = _row_to_item(row, columns)
        link_ids = item.pop("__link_record_ids", []) or []
        if inventory_index:
            _fill_from_inventory(item, link_ids, inventory_index)
        else:
            item.pop("__link_record_ids", None)
        items.append(item)

    if keyword:
        kw = keyword.lower()
        kw_fields = _keyword_fields(page_key)
        items = [
            it
            for it in items
            if any(kw in str(it.get(f) or "").lower() for f in kw_fields)
        ]
    if filters:
        for fk, fv in filters.items():
            if fv:
                items = [it for it in items if str(it.get(fk) or "") == fv]

    total = len(items)
    start = (page - 1) * page_size
    page_items = items[start : start + page_size]

    display_fields = list(columns)
    if page_key in (PAGE_INBOUND, PAGE_OUTBOUND):
        derived = ["物资名称", "规格型号", "当前库存"]
        for key in derived:
            if key not in display_fields and any(
                it.get(key) not in (None, "") for it in items
            ):
                display_fields.append(key)

    return {
        "items": page_items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "configured": True,
        "fields": display_fields,
        "last_sync_time": snapshot.last_synced_at.isoformat()
        if snapshot.last_synced_at
        else None,
    }


def _keyword_fields(page_key: str) -> list[str]:
    if page_key == PAGE_INVENTORY:
        return ["物资名称", "规格型号", "物资名（规格）", "备注"]
    if page_key == PAGE_OUTBOUND:
        return ["物资名称", "领用人"]
    return ["物资名称"]


async def list_distinct_column_values(
    db: AsyncSession, page_key: str, column_key: str
) -> list[str]:
    """镜像某列去重值（供库存台账动态筛选项/分类）。"""
    _snapshot, _columns, rows, _total = await _load_page(db, page_key)
    values: list[str] = []
    seen: set[str] = set()
    for row in rows:
        raw = (row.cells or {}).get(column_key)
        value = str(raw).strip() if raw not in (None, "") else ""
        if value and value not in seen:
            seen.add(value)
            values.append(value)
    return values
