"""质量检验-固体/液体物料检验 飞书子表 -> 本地镜像回拉与读取。

照搬物品管理镜像（inspection_items_mirror）模式，存储复用通用快照/行表
quality.quality_items_page_snapshots / quality.quality_items_page_rows
（page_key = 物料实体编码，如 qc_solid_ys002；cells 以飞书中文列名为键，
值为前端 renderFeishuValue 可直接渲染的结构）：
- 全量轮：GET /records 翻页拉全表 + 列元数据，写 snapshot.columns，upsert
  全部行并对账软删远端消失的行；
- 增量轮：records/search 按批号降序逐页拉取（飞书不支持按 last_modified_time
  排序/过滤），只写新批号 / 内容有变化的批号，整页无变更提前停止，不做删除
  对账（更早批号的历史修改由每日全量兜底）；
- 读取：列表镜像优先，飞书不可达/未同步时由上层降级实时读。

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
from app.modules.quality.service.quality_feishu_material_groups import (
    MATERIAL_ENTITY_CODES,
    MATERIAL_ENTITY_LABELS,
)
from app.modules.quality.service.quality_feishu_pages import _resolve_runtime_entity
from app.platform.integrations.feishu.bitable import BitableClient

logger = logging.getLogger(__name__)

# 全部固体/液体物料实体（= 本地镜像页键）
MATERIAL_MIRROR_ENTITIES: tuple[str, ...] = MATERIAL_ENTITY_CODES

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

# 内部保留键前缀（不进入 cells 的业务列）
_INTERNAL_PREFIX = "__"


def _entity_module(entity_code: str) -> str:
    return "solid" if entity_code.startswith("qc_solid") else "liquid"


def _entity_label(entity_code: str) -> str:
    module = _entity_module(entity_code)
    return MATERIAL_ENTITY_LABELS[module].get(entity_code, entity_code)


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
            message="从飞书拉取物料数据失败：无法连接飞书或访问该多维表格，"
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


async def _fetch_incremental_records(
    client: BitableClient,
    table_id: str,
    batch_index: dict[str, dict[str, Any]],
    columns: list[dict[str, Any]],
    page_size: int = 500,
) -> list[dict[str, Any]]:
    """批号驱动增量拉取：records/search 按批号降序逐页拉取，早期终止。

    飞书不支持按 last_modified_time 排序/过滤（InvalidSort/InvalidFilter），
    但支持按普通文本字段（批号）排序且翻页可靠（实测 page_token 逐页推进）。
    新批号批号更大 → 排序靠前，从最新批号页开始拉：
    - 每页过滤出"新批号 / 内容有变化"的记录；
    - 一整页都没有新/变更批号 → 后续更旧批号必然也已同步 → 提前停止。
    这样表任意大小都只拉"含新数据"的页；早期更旧批号的历史修改由每日全量兜底。
    """
    records: list[dict[str, Any]] = []
    page_token = ""
    for _page_index in range(200):
        params: dict[str, Any] = {
            "page_size": page_size,
            "field_name_type": "name",
            "automatic_fields": True,
        }
        if page_token:
            params["page_token"] = page_token
        data = await client.client.request(
            "POST",
            f"/bitable/v1/apps/{client.app_token}/tables/{table_id}/records/search",
            params=params,
            json={"sort": [{"field_name": "批号", "desc": True}]},
            timeout=60.0,
        )
        items = [item for item in (data.get("items") or []) if isinstance(item, dict)]
        page_new = [
            item
            for item in items
            if _record_is_incremental_new(item, batch_index, columns)
        ]
        records.extend(page_new)
        if not data.get("has_more"):
            break
        # 整页无新/变更 → 更旧批号全部已同步，提前停止
        if not page_new:
            break
        next_token = str(data.get("page_token") or "")
        if not next_token or next_token == page_token:
            break  # 防御：翻页 token 停滞/循环时停止
        page_token = next_token
    return records


async def _fetch_field_items(
    client: BitableClient, table_id: str
) -> list[dict[str, Any]]:
    try:
        return await client.list_fields(table_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("material mirror list_fields failed for %s: %s", table_id, exc)
        return []


# ── 同步编排 ──────────────────────────────────────────────────────────


async def sync_material_page(
    db: AsyncSession,
    entity_code: str,
    *,
    incremental: bool = True,
) -> dict[str, int]:
    """同步单个物料实体到本地镜像。返回 {synced, removed, total}。

    incremental=True 且已有快照时走增量水位（只写变更行、不删历史）；
    否则全量（含删除对账）。飞书不可达抛 AppException，交由调度器记录。
    """
    if entity_code not in MATERIAL_MIRROR_ENTITIES:
        raise AppException(
            message=f"未知的物料镜像实体：{entity_code}", status_code=400
        )

    label = _entity_label(entity_code)
    runtime, entity = await _resolve_runtime_entity(db, entity_code, direction="pull")
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
        # 列结构拉取失败时禁止降级写入：仅批号的 cells 会在增量比对中把
        # 镜像整行数据覆盖掉（读路径用 snapshot.columns，不受此影响）
        raise AppException(
            message=f"获取物料表列结构失败，已跳过本次同步：{entity_code}",
            status_code=503,
        )

    if use_incremental:
        batch_index = await _load_batch_index(db, prev_snapshot)
        try:
            # 批号驱动增量：按批号降序逐页拉取，只写新批号 / 内容有变化的批号
            records = await _fetch_or_fail(
                _fetch_incremental_records(
                    client, table_id, batch_index, columns
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "material batch-desc incremental failed for %s, fallback full: %s",
                entity_code,
                exc,
            )
            records = await _fetch_or_fail(_fetch_full_records(client, table_id))
            records = [
                record
                for record in records
                if _record_is_incremental_new(record, batch_index, columns)
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
        "material mirror sync entity=%s incremental=%s rows=%d",
        entity_code,
        use_incremental,
        len(row_models),
    )
    return {"synced": len(row_models), "removed": 0, "total": len(row_models)}


def _extract_batch(record: dict[str, Any]) -> str | None:
    """取记录批号：兼容飞书 records/search 返回的结构化文本（[{text,...}]）与
    GET /records 返回的纯字符串（_normalize_text 对两者归一化一致）。"""
    fields = record.get("fields") or {}
    text = feishu_sync_service._normalize_text(fields.get("批号"))
    return text.strip() if text else None


def _cells_content(cells: dict[str, Any]) -> dict[str, Any]:
    """剔除内部保留键（__last_modified 等）后的业务内容，用于增量变更比对。"""
    return {
        key: value
        for key, value in (cells or {}).items()
        if not key.startswith(_INTERNAL_PREFIX)
    }


async def _load_batch_index(
    db: AsyncSession, snapshot: Any
) -> dict[str, dict[str, Any]]:
    """本地镜像已同步行按批号索引（批号唯一，作为增量判重键）。"""
    if snapshot is None:
        return {}
    rows, _ = await repo.list_rows(db, snapshot.id, limit=None)
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        batch = (row.cells or {}).get("批号")
        if isinstance(batch, str) and batch.strip():
            index.setdefault(batch.strip(), row.cells or {})
    return index


def _record_is_incremental_new(
    record: dict[str, Any],
    batch_index: dict[str, dict[str, Any]],
    columns: list[dict[str, Any]],
) -> bool:
    """批号驱动的增量判定：新批号必拉；已同步批号仅业务内容变化时更新。

    飞书 records/search 不返回 last_modified_time，故改用批号 + 内容比对：
    内容一致视为未变更跳过（历史修改/删除由每日全量兜底）。
    """
    batch = _extract_batch(record)
    if batch is None:
        return True  # 无批号的兜底记录 → 按新处理
    prev_cells = batch_index.get(batch)
    if prev_cells is None:
        return True  # 新批号 → 增量写入
    new_cells = _normalize_record_cells(record, columns)
    return _cells_content(new_cells) != _cells_content(prev_cells)


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
    return item


def _has_visible_cell(item: dict[str, Any], columns: list[str]) -> bool:
    """跳过业务字段全空的占位行（对齐实时 _list_feishu 的过滤）。"""
    return any(str(item.get(col) or "").strip() for col in columns)


async def _load_page(
    db: AsyncSession, entity_code: str
) -> tuple[Any, list[str], list[QualityItemsPageRow], int]:
    snapshot = await repo.get_snapshot(db, entity_code)
    if snapshot is None:
        return None, [], [], 0
    columns = [
        str(col.get("key")) for col in (snapshot.columns or []) if col.get("key")
    ]
    rows, total = await repo.list_rows(db, snapshot.id, limit=None)
    return snapshot, columns, rows, total


async def get_material_mirror_fields(
    db: AsyncSession, entity_code: str
) -> list[str]:
    """读取镜像快照列结构；未同步返回空列表（由上层实时兜底）。"""
    snapshot = await repo.get_snapshot(db, entity_code)
    if snapshot is None:
        return []
    return [
        str(col.get("key")) for col in (snapshot.columns or []) if col.get("key")
    ]


async def list_material_mirror(
    db: AsyncSession,
    entity_code: str,
    *,
    keyword: str | None = None,
    filters: dict[str, str] | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """从本地镜像读取物料列表，返回结构与实时 _list_feishu 对齐。

    无镜像快照时返回 configured=False 空页（由上层触发同步或降级实时读）。
    """
    snapshot, columns, rows, _total = await _load_page(db, entity_code)
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

    items: list[dict[str, Any]] = []
    for row in rows:
        item = _row_to_item(row, columns)
        if _has_visible_cell(item, columns):
            items.append(item)

    if keyword:
        kw = keyword.lower()
        items = [
            it
            for it in items
            if any(kw in str(it.get(f) or "").lower() for f in columns)
        ]
    if filters:
        for fk, fv in filters.items():
            if fv:
                items = [it for it in items if str(it.get(fk) or "") == fv]

    # 与实时 _list_feishu 一致：按 updated_at 倒序（最新变更在前）
    items.sort(key=lambda x: str(x.get("updated_at") or ""), reverse=True)

    total = len(items)
    start = (page - 1) * page_size
    page_items = items[start : start + page_size]

    return {
        "items": page_items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "configured": True,
        "fields": list(columns),
        "last_sync_time": snapshot.last_synced_at.isoformat()
        if snapshot.last_synced_at
        else None,
    }
