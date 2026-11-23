"""质量检验-成品检验 飞书子表 -> 本地镜像回拉与读取。

照搬固体/液体物料镜像（inspection_material_mirror）模式，存储复用通用
快照/行表 quality.quality_items_page_snapshots / quality.quality_items_page_rows
（page_key = 成品实体编码，如 qc_finished_internal；cells 以飞书中文列名为键，
值为前端 renderFeishuValue 可直接渲染的结构）：
- 全量轮：GET /records 翻页拉全表 + 列元数据，写 snapshot.columns，upsert
  全部行并对账软删远端消失的行；
- 增量轮：records/search 按"批号"降序逐页拉取，早期终止（每张成品表的批号
  唯一，作为增量判重键；新批号/内容有变化才写，不做删除对账）；
- 读取：列表镜像优先，飞书不可达/未同步时由上层降级实时读。

凭证与实体配置由质量模块 runtime 解析后显式传给平台 BitableClient，符合
app/platform/integrations/feishu 平台边界。
"""

from __future__ import annotations

from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.quality.models.inspection_items_mirror import (
    QualityItemsPageRow,
)
from app.modules.quality.repository import inspection_items_mirror as repo
from app.modules.quality.service import quality_feishu_sync as feishu_sync_service
from app.modules.quality.service.inspection_batch_mirror_sync import sync_batch_mirror
from app.modules.quality.service.inspection_helpers import _smart_normalize_value
from app.modules.quality.service.quality_feishu_finished_groups import (
    FINISHED_ENTITY_LABELS,
    FINISHED_PRODUCT_GROUP_ENTITY_MAP,
)
from app.modules.quality.service.quality_feishu_pages import _resolve_runtime_entity
from app.platform.integrations.feishu.bitable import BitableClient

# 全部成品检验实体（= 本地镜像页键）
FINISHED_MIRROR_ENTITIES: tuple[str, ...] = tuple(
    entity_code
    for entity_codes in FINISHED_PRODUCT_GROUP_ENTITY_MAP.values()
    for entity_code in entity_codes
)

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


def _entity_label(entity_code: str) -> str:
    return FINISHED_ENTITY_LABELS.get(entity_code, entity_code)


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
            message="从飞书拉取成品检验数据失败：无法连接飞书或访问该多维表格，"
            "请检查网络及质量模块飞书应用对该 Base 的协作者权限",
            status_code=503,
        ) from exc


# ── 同步编排 ──────────────────────────────────────────────────────────


async def sync_finished_page(
    db: AsyncSession,
    entity_code: str,
    *,
    incremental: bool = True,
) -> dict[str, int]:
    """同步单个成品实体到本地镜像。返回 {synced, removed, total}。

    incremental=True 且已有快照时走批号水位（只写变更行、不删历史）；
    否则全量（含删除对账）。飞书不可达抛 AppException，交由调度器记录。
    """
    if entity_code not in FINISHED_MIRROR_ENTITIES:
        raise AppException(
            message=f"未知的成品检验镜像实体：{entity_code}", status_code=400
        )

    label = _entity_label(entity_code)
    runtime, entity = await _resolve_runtime_entity(db, entity_code, direction="pull")
    client = BitableClient(
        app_token=entity.app_token,
        app_id=runtime.app_id,
        app_secret=runtime.app_secret,
    )
    table_id = feishu_sync_service._require_table_id(entity)

    field_items = await _fetch_or_fail(client.list_fields(table_id))
    columns = _build_columns(field_items)
    if not columns:
        raise AppException(
            message=f"获取成品检验表列结构失败，已跳过本次同步：{entity_code}",
            status_code=503,
        )

    return await sync_batch_mirror(
        db,
        client,
        entity_code=entity_code,
        label=label,
        table_id=table_id,
        columns=columns,
        incremental=incremental,
        normalize_cells=_normalize_record_cells,
        extract_batch=_extract_batch,
        build_search_text=_build_search_text,
    )


def _extract_batch(record: dict[str, Any]) -> str | None:
    """取记录批号：兼容飞书 records/search 返回的结构化文本（[{text,...}]）与
    GET /records 返回的纯字符串（_normalize_text 对两者归一化一致）。"""
    fields = record.get("fields") or {}
    text = feishu_sync_service._normalize_text(fields.get("批号"))
    return text.strip() if text else None


# ── 读取（列表页共用）────────────────────────────────────────────────


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


async def get_finished_mirror_fields(
    db: AsyncSession, entity_code: str
) -> list[str]:
    """读取镜像快照列结构；未同步返回空列表（由上层实时兜底）。"""
    snapshot = await repo.get_snapshot(db, entity_code)
    if snapshot is None:
        return []
    return [
        str(col.get("key")) for col in (snapshot.columns or []) if col.get("key")
    ]


async def list_finished_mirror(
    db: AsyncSession,
    entity_code: str,
    *,
    keyword: str | None = None,
    filters: dict[str, str] | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """从本地镜像读取成品列表，返回结构与实时 _list_feishu 对齐。

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
        text_sort_field="批号",
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


async def upsert_record_by_id(
    db: AsyncSession,
    entity_code: str,
    record_id: str,
) -> bool:
    """按飞书记录 ID 拉取最新单条并写穿到本地镜像（编辑/新增后即时生效）。

    增量同步按批号降序逐页拉取且整页无变更提前停止，编辑旧批号的行
    往往拉不到；本函数单条 get_record 后直接 upsert 对应镜像行，
    不受 early-stop 影响。无镜像快照/列结构时返回 False（由增量轮兜底）。
    """
    if entity_code not in FINISHED_MIRROR_ENTITIES:
        return False
    await repo.lock_batch_mirror(db, entity_code)
    snapshot = await repo.get_snapshot(db, entity_code)
    if snapshot is None or snapshot.total_rows <= 0:
        return False
    # snapshot.columns 即 sync 时 _build_columns 的列结构（含 key/options），
    # _normalize_record_cells 依赖 options 做单选 id→文字解析
    columns = [col for col in (snapshot.columns or []) if col.get("key")]
    if not columns or not record_id:
        return False
    runtime, entity = await _resolve_runtime_entity(db, entity_code, direction="pull")
    client = BitableClient(
        app_token=entity.app_token,
        app_id=runtime.app_id,
        app_secret=runtime.app_secret,
    )
    record = await client.get_record(
        feishu_sync_service._require_table_id(entity), record_id
    )
    if not record or not record.get("record_id"):
        return False
    existing_row = await db.scalar(
        select(QualityItemsPageRow).where(
            QualityItemsPageRow.page_snapshot_id == snapshot.id,
            QualityItemsPageRow.source_record_id == record_id,
        )
    )
    cells = _normalize_record_cells(record, columns)
    row = QualityItemsPageRow(
        page_snapshot_id=snapshot.id,
        source_record_id=record_id,
        row_order=existing_row.row_order if existing_row else 0,
        cells=cells,
        search_text=_build_search_text(cells),
        last_synced_at=datetime.now(UTC),
    )
    await repo.upsert_rows_incremental(db, snapshot.id, [row])
    snapshot.total_rows = await repo.count_rows(db, snapshot.id)
    await db.commit()
    return True


async def delete_mirror_record(
    db: AsyncSession,
    entity_code: str,
    record_id: str,
) -> bool:
    """删除记录后立即软删对应镜像行（无需等全量删除对账）。"""
    if entity_code not in FINISHED_MIRROR_ENTITIES:
        return False
    await repo.lock_batch_mirror(db, entity_code)
    snapshot = await repo.get_snapshot(db, entity_code)
    if snapshot is None:
        return False
    deleted = await repo.delete_row_by_record_id(db, snapshot.id, record_id)
    if deleted:
        snapshot.total_rows = await repo.count_rows(db, snapshot.id)
        await db.commit()
    return deleted
