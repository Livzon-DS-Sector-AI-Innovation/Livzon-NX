"""质量检验-物品管理本地镜像持久化辅助。

写库三态照搬仓储 material_page_rows 语义（去掉状态变更日志）：
- 全量：命中即更新并复活软删行；本地有但本次未传入的 → 软删（对账）
- 增量：只 upsert 本次变更记录，不删历史、不复活软删行
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import TIMESTAMP, asc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.inspection_items_mirror import (
    QualityItemsPageRow,
    QualityItemsPageSnapshot,
)


async def get_snapshot(
    db: AsyncSession, page_key: str
) -> QualityItemsPageSnapshot | None:
    result = await db.execute(
        select(QualityItemsPageSnapshot).where(
            QualityItemsPageSnapshot.page_key == page_key,
            QualityItemsPageSnapshot.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def upsert_snapshot(
    db: AsyncSession,
    *,
    page_key: str,
    page_title: str,
    table_name: str,
    table_id: str,
    columns: list[dict[str, Any]],
    total_rows: int,
    source: str = "feishu_bitable",
    last_synced_at: datetime | None = None,
    last_error: str | None = None,
) -> QualityItemsPageSnapshot:
    now = last_synced_at or datetime.now(UTC)
    snapshot = await get_snapshot(db, page_key)
    payload = {
        "page_key": page_key,
        "page_title": page_title,
        "table_name": table_name,
        "table_id": table_id,
        "columns": columns,
        "total_rows": total_rows,
        "source": source,
        "last_synced_at": now,
        "last_error": last_error,
    }
    if snapshot is not None:
        for field, value in payload.items():
            setattr(snapshot, field, value)
        snapshot.is_deleted = False
        await db.flush()
        await db.refresh(snapshot)
        return snapshot

    snapshot = QualityItemsPageSnapshot(**payload)
    db.add(snapshot)
    await db.flush()
    await db.refresh(snapshot)
    return snapshot


async def upsert_rows_full(
    db: AsyncSession,
    snapshot_id: Any,
    rows: Sequence[QualityItemsPageRow],
) -> None:
    """全量同步：命中更新并复活软删，未传入的历史行软删对账。"""
    result = await db.execute(
        select(QualityItemsPageRow).where(
            QualityItemsPageRow.page_snapshot_id == snapshot_id,
        )
    )
    existing_rows: dict[str, QualityItemsPageRow] = {
        row.source_record_id: row for row in result.scalars().all()
    }

    incoming_ids: set[str] = set()
    for row in rows:
        incoming_ids.add(row.source_record_id)
        existing = existing_rows.get(row.source_record_id)
        if existing is not None:
            existing.cells = row.cells
            existing.search_text = row.search_text
            existing.row_order = row.row_order
            existing.last_synced_at = row.last_synced_at
            existing.is_deleted = False
        else:
            db.add(row)

    for record_id, existing in existing_rows.items():
        if record_id not in incoming_ids and existing.is_deleted is not True:
            existing.is_deleted = True

    await db.flush()


async def upsert_rows_incremental(
    db: AsyncSession,
    snapshot_id: Any,
    rows: Sequence[QualityItemsPageRow],
) -> None:
    """增量同步：只 upsert 本次变更，不软删历史、不复活已软删行。"""
    result = await db.execute(
        select(QualityItemsPageRow).where(
            QualityItemsPageRow.page_snapshot_id == snapshot_id,
        )
    )
    existing_rows: dict[str, QualityItemsPageRow] = {
        row.source_record_id: row for row in result.scalars().all()
    }

    for row in rows:
        existing = existing_rows.get(row.source_record_id)
        if existing is not None:
            # 已软删行不因增量复活：仅全量确认飞书仍存在才恢复
            if existing.is_deleted:
                continue
            existing.cells = row.cells
            existing.search_text = row.search_text
            existing.row_order = row.row_order
            existing.last_synced_at = row.last_synced_at
        else:
            db.add(row)

    await db.flush()


async def list_rows(
    db: AsyncSession,
    snapshot_id: Any,
    *,
    keyword: str | None = None,
    offset: int = 0,
    limit: int | None = 50,
) -> tuple[list[QualityItemsPageRow], int]:
    """读取镜像行（is_deleted=False，search_text 关键词过滤，row_order 排序）。"""
    count_stmt = (
        select(func.count())
        .select_from(QualityItemsPageRow)
        .where(
            QualityItemsPageRow.page_snapshot_id == snapshot_id,
            QualityItemsPageRow.is_deleted.is_(False),
        )
    )
    stmt = (
        select(QualityItemsPageRow)
        .where(
            QualityItemsPageRow.page_snapshot_id == snapshot_id,
            QualityItemsPageRow.is_deleted.is_(False),
        )
        .order_by(
            asc(QualityItemsPageRow.row_order),
            asc(QualityItemsPageRow.created_at),
        )
    )
    if keyword:
        keyword_value = f"%{keyword.lower()}%"
        count_stmt = count_stmt.where(
            func.lower(QualityItemsPageRow.search_text).like(keyword_value)
        )
        stmt = stmt.where(
            func.lower(QualityItemsPageRow.search_text).like(keyword_value)
        )
    if offset:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)

    total = int((await db.execute(count_stmt)).scalar_one() or 0)
    rows = list((await db.execute(stmt)).scalars().all())
    return rows, total


async def list_rows_filtered(
    db: AsyncSession,
    snapshot_id: Any,
    *,
    columns: list[str],
    keyword: str | None = None,
    filters: dict[str, str] | None = None,
    updated_sort_field: str = "__last_modified",
    offset: int = 0,
    limit: int | None = 50,
) -> tuple[list[QualityItemsPageRow], int]:
    """读取镜像行：占位行过滤 + 关键词 + 任意列精确匹配，按更新时间倒序 SQL 分页。

    cells 以飞书中文列名为键，动态列通过 JSONB ->> 过滤：
    - 占位行：所有业务列均为空的行跳过（等价内存版 _has_visible_cell）；
    - filters：列值精确匹配（NULL 视为不匹配）；
    - 排序：默认按镜像内部更新时间字段（__last_modified）倒序，缺失排最后。
    相比 list_rows 的全表载入 + Python 过滤，本方法把过滤/排序/分页下沉到 SQL，
    避免列表页把整张镜像表传输进应用进程。
    """
    base_conditions = [
        QualityItemsPageRow.page_snapshot_id == snapshot_id,
        QualityItemsPageRow.is_deleted.is_(False),
    ]
    visible_conditions = [
        func.coalesce(QualityItemsPageRow.cells[col].astext, "") != ""
        for col in columns
        if col
    ]
    if visible_conditions:
        base_conditions.append(or_(*visible_conditions))

    count_stmt = (
        select(func.count())
        .select_from(QualityItemsPageRow)
        .where(*base_conditions)
    )
    stmt = select(QualityItemsPageRow).where(*base_conditions)

    if keyword:
        keyword_value = f"%{keyword}%"
        count_stmt = count_stmt.where(
            QualityItemsPageRow.search_text.ilike(keyword_value)
        )
        stmt = stmt.where(QualityItemsPageRow.search_text.ilike(keyword_value))
    if filters:
        for field_key, field_value in filters.items():
            if not field_value:
                continue
            condition = QualityItemsPageRow.cells[field_key].astext == field_value
            count_stmt = count_stmt.where(condition)
            stmt = stmt.where(condition)

    stmt = stmt.order_by(
        # ISO 字符串按 collation 排序不可靠（如 "+00:00" 与 ".100000" 顺序颠倒），
        # cast 成 timestamptz 精确排序；__last_modified 由本模块以合法 ISO 写入
        func.nullif(
            QualityItemsPageRow.cells[updated_sort_field].astext, ""
        )
        .cast(TIMESTAMP(timezone=True))
        .desc()
        .nullslast(),
        QualityItemsPageRow.updated_at.desc().nullslast(),
    )
    if offset:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)

    total = int((await db.execute(count_stmt)).scalar_one() or 0)
    rows = list((await db.execute(stmt)).scalars().all())
    return rows, total


async def count_rows(db: AsyncSession, snapshot_id: Any) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(QualityItemsPageRow)
        .where(
            QualityItemsPageRow.page_snapshot_id == snapshot_id,
            QualityItemsPageRow.is_deleted.is_(False),
        )
    )
    return int(result.scalar_one() or 0)
