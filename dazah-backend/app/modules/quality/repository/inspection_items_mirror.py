"""质量检验-物品管理本地镜像持久化辅助。

写库三态照搬仓储 material_page_rows 语义（去掉状态变更日志）：
- 全量：命中即更新并复活软删行；本地有但本次未传入的 → 软删（对账）
- 增量：只 upsert 本次变更记录，不删历史、不复活软删行
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    TIMESTAMP,
    ColumnElement,
    Numeric,
    Row,
    SQLColumnExpression,
    String,
    all_,
    any_,
    asc,
    bindparam,
    case,
    cast,
    false,
    func,
    literal,
    literal_column,
    null,
    or_,
    select,
    type_coerce,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.modules.quality.models.inspection_items_mirror import (
    QualityItemsPageRow,
    QualityItemsPageSnapshot,
)

# 与既有批号比对使用的 Python str.strip() 一致，包括全角空格。
_BATCH_NUMBER_WHITESPACE = (
    "\t\n\v\f\r\x1c\x1d\x1e\x1f \x85\xa0\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u2028\u2029\u202f\u205f\u3000"
)


async def lock_batch_mirror(db: AsyncSession, page_key: str) -> None:
    """串行化同一物料/成品镜像的同步和单行写穿，包括首次建快照。"""
    await db.execute(
        select(
            func.pg_advisory_xact_lock(
                func.hashtextextended(
                    f"quality.batch_mirror:{page_key}",
                    0,
                )
            )
        )
    )


async def get_cells_by_batches(
    db: AsyncSession,
    snapshot_id: UUID,
    batches: set[str],
) -> dict[str, dict[str, Any]]:
    if not batches:
        return {}
    field = QualityItemsPageRow.cells["批号"]
    batch = func.btrim(field.astext, _BATCH_NUMBER_WHITESPACE)
    result = await db.execute(
        select(batch, QualityItemsPageRow.cells)
        .where(
            QualityItemsPageRow.page_snapshot_id == snapshot_id,
            QualityItemsPageRow.is_deleted.is_(False),
            func.jsonb_typeof(field) == "string",
            batch.in_(batches),
        )
        .distinct(batch)
        .order_by(batch, QualityItemsPageRow.row_order, QualityItemsPageRow.created_at)
    )
    return {number: cells for number, cells in result}


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
    await upsert_mirror_batch(db, snapshot_id, rows, revive_deleted=False)


async def upsert_mirror_batch(
    db: AsyncSession,
    snapshot_id: UUID,
    rows: Sequence[QualityItemsPageRow],
    *,
    revive_deleted: bool,
) -> None:
    if not rows:
        return
    record_ids = [row.source_record_id for row in rows]
    result = await db.execute(
        select(QualityItemsPageRow).where(
            QualityItemsPageRow.page_snapshot_id == snapshot_id,
            QualityItemsPageRow.source_record_id
            == any_(
                bindparam("record_ids", record_ids, type_=ARRAY(String)),
            ),
        )
    )
    existing_rows: dict[str, QualityItemsPageRow] = {
        row.source_record_id: row for row in result.scalars().all()
    }

    for row in rows:
        existing = existing_rows.get(row.source_record_id)
        if existing is not None:
            # 已软删行不因增量复活：仅全量确认飞书仍存在才恢复
            if existing.is_deleted and not revive_deleted:
                continue
            existing.cells = row.cells
            existing.search_text = row.search_text
            existing.row_order = row.row_order
            existing.last_synced_at = row.last_synced_at
            existing.is_deleted = False
        else:
            db.add(row)

    await db.flush()


async def soft_delete_missing_mirror_rows(
    db: AsyncSession,
    snapshot_id: UUID,
    seen_ids: set[str],
) -> None:
    """完成全量分页后用记录 ID 对账，避免加载历史行内容。"""
    await db.execute(
        update(QualityItemsPageRow)
        .where(
            QualityItemsPageRow.page_snapshot_id == snapshot_id,
            QualityItemsPageRow.is_deleted.is_(False),
            QualityItemsPageRow.source_record_id
            != all_(
                bindparam("seen_ids", list(seen_ids), type_=ARRAY(String)),
            ),
        )
        .values(is_deleted=True)
        .execution_options(synchronize_session=False)
    )


async def delete_row_by_record_id(
    db: AsyncSession,
    snapshot_id: Any,
    source_record_id: str,
) -> bool:
    """按飞书记录 ID 软删镜像行（用户删除记录后立即从列表消失）。

    与全量删除对账语义一致（软删）；返回是否确有行被删。
    """
    result = await db.execute(
        update(QualityItemsPageRow)
        .where(
            QualityItemsPageRow.page_snapshot_id == snapshot_id,
            QualityItemsPageRow.source_record_id == source_record_id,
            QualityItemsPageRow.is_deleted.is_(False),
        )
        .values(is_deleted=True)
    )
    await db.flush()
    return bool(getattr(result, "rowcount", 0))


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
    numeric_ranges: dict[str, tuple[float, float]] | None = None,
    updated_sort_field: str = "__last_modified",
    text_sort_field: str | None = None,
    offset: int = 0,
    limit: int | None = 50,
) -> tuple[list[QualityItemsPageRow], int]:
    """读取镜像行：占位行过滤 + 关键词 + 任意列精确匹配，按更新时间倒序 SQL 分页。

    cells 以飞书中文列名为键，动态列通过 JSONB ->> 过滤：
    - 占位行：所有业务列均为空的行跳过（等价内存版 _has_visible_cell）；
    - filters：列值精确匹配（NULL 视为不匹配）；
    - numeric_ranges：列值数值范围匹配（如维保列表按生成日期毫秒时间戳
      落月）；先用正则确认文本是数字再 cast，脏文本/空值不落入任何区间；
    - 排序：text_sort_field 给定时按该文本列倒序（对齐飞书批号文本降序），
      缺失排最后、次键回落更新时间；未指定时默认按镜像更新时间字段
      （__last_modified）倒序。
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
        select(func.count()).select_from(QualityItemsPageRow).where(*base_conditions)
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
    if numeric_ranges:
        for field_key, (low, high) in numeric_ranges.items():
            cell_text = func.nullif(QualityItemsPageRow.cells[field_key].astext, "")
            numeric_cell = cell_text.cast(Numeric)
            # 左闭右开 [low, high)：月末 1 日 00:00 恰为上月 high 时归当月；
            # 先用正则确认是数字再 cast，脏文本/空值不落入任何区间
            condition = (
                cell_text.op("~")(r"^-?\d+(\.\d+)?$")
                & (numeric_cell >= low)
                & (numeric_cell < high)
            )
            count_stmt = count_stmt.where(condition)
            stmt = stmt.where(condition)

    if text_sort_field:
        # 按文本列（如批号）倒序：与飞书 records/search 的批号降序对齐；
        # 次键回落到更新时间，保证同批号/空批号行顺序稳定。
        stmt = stmt.order_by(
            func.nullif(QualityItemsPageRow.cells[text_sort_field].astext, "")
            .desc()
            .nullslast(),
            func.nullif(QualityItemsPageRow.cells[updated_sort_field].astext, "")
            .cast(TIMESTAMP(timezone=True))
            .desc()
            .nullslast(),
            QualityItemsPageRow.row_order.asc(),
        )
    else:
        stmt = stmt.order_by(
            # ISO 字符串按 collation 排序不可靠（如 "+00:00" 与 ".100000" 顺序颠倒），
            # cast 成 timestamptz 精确排序；__last_modified 由本模块以合法 ISO 写入
            func.nullif(QualityItemsPageRow.cells[updated_sort_field].astext, "")
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


ITEM_INVENTORY_FIELDS = ("物资名称", "规格型号", "当前库存")


def _nonempty_json_cell(cell: ColumnElement[Any]) -> ColumnElement[Any]:
    # Match str(value or "") for normalized mirror scalars and empty containers.
    cell = type_coerce(cell, JSONB)
    return case(
        (cell.in_([None, False, 0, "", [], {}]), null()),
        else_=cell,
    )


def _cell_text(cell: ColumnElement[Any]) -> ColumnElement[str]:
    value = _nonempty_json_cell(cell)
    text = type_coerce(value.op("#>>")(literal_column("'{}'")), String)
    normalized = case((func.jsonb_typeof(value) == "boolean", "True"), else_=text)
    return func.coalesce(normalized, "")


def _timestamp_text(value: SQLColumnExpression[Any]) -> ColumnElement[str]:
    utc_value = func.timezone("UTC", value)
    base = func.to_char(utc_value, 'YYYY-MM-DD"T"HH24:MI:SS')
    microseconds = func.to_char(utc_value, "US")
    return (
        base + case((microseconds != "000000", "." + microseconds), else_="") + "+00:00"
    )


async def list_business_page(
    db: AsyncSession,
    snapshot_id: Any,
    *,
    columns: Sequence[str],
    keyword_fields: Sequence[str],
    keyword: str | None,
    filters: dict[str, str] | None,
    sort_field: str | None,
    offset: int,
    limit: int,
    exclude_empty: bool = False,
    inventory_snapshot: QualityItemsPageSnapshot | None = None,
) -> tuple[list[tuple[QualityItemsPageRow, dict[str, Any] | None]], int, set[str]]:
    """Filter and count mirror rows, with an optional first linked stock row."""
    row = QualityItemsPageRow
    predicates = [row.page_snapshot_id == snapshot_id, row.is_deleted.is_(False)]
    stmt = select(row, literal(None, type_=JSONB).label("inventory_cells"))
    count_stmt = select(func.count().label("total")).select_from(row)
    cell_values = {key: row.cells[key] for key in columns}
    derived_fields: list[str] = []

    if inventory_snapshot is not None:
        missing = cast(null(), JSONB)
        stock = aliased(QualityItemsPageRow)
        stock_columns = {
            str(col.get("key")) for col in (inventory_snapshot.columns or [])
        }
        can_fill = ~(
            _nonempty_json_cell(cell_values.get("物资名称", missing)).is_not(None)
            & _nonempty_json_cell(cell_values.get("规格型号", missing)).is_not(None)
        )
        link = (
            (stock.page_snapshot_id == inventory_snapshot.id)
            & (stock.source_record_id == row.cells["__link_record_ids"][0].astext)
            & stock.is_deleted.is_(False)
            & can_fill
        )
        stmt = select(row, stock.cells.label("inventory_cells")).outerjoin(stock, link)
        count_stmt = count_stmt.outerjoin(stock, link)
        for key in ITEM_INVENTORY_FIELDS:
            source = stock.cells[key] if key in stock_columns else missing
            if key == "物资名称" and "物资名（规格）" in stock_columns:
                source = func.coalesce(
                    _nonempty_json_cell(source), stock.cells["物资名（规格）"]
                )
            current = cell_values.get(key, missing)
            effective: ColumnElement[Any] = case(
                (
                    stock.id.is_not(None),
                    func.coalesce(_nonempty_json_cell(current), source),
                ),
                else_=current,
            )
            effective = type_coerce(effective, JSONB)
            cell_values[key] = effective
            if key not in columns:
                # Linked zero and false values still make a derived column visible.
                count_stmt = count_stmt.add_columns(
                    func.bool_or(
                        effective.is_not(None) & ~effective.in_([None, ""])
                    ).label(f"has_derived_{len(derived_fields)}")
                )
                derived_fields.append(key)

    text_values: dict[str, SQLColumnExpression[str]] = {
        key: _cell_text(value) for key, value in cell_values.items()
    }
    metadata = {
        "record_id": row.source_record_id,
        "created_at": _timestamp_text(row.created_at),
        "updated_at": func.coalesce(
            func.nullif(row.cells["__last_modified"].astext, ""),
            _timestamp_text(row.updated_at),
        ),
    }
    for key, expression in metadata.items():
        text_values.setdefault(key, expression)
    if exclude_empty:
        predicates.append(
            or_(
                false(),
                *[
                    func.btrim(text_values[key], _BATCH_NUMBER_WHITESPACE) != ""
                    for key in columns
                ],
            )
        )
    if keyword:
        predicates.append(
            or_(
                false(),
                *[
                    func.strpos(func.lower(text_values[key]), keyword.lower()) > 0
                    for key in keyword_fields
                    if key in text_values
                ],
            )
        )
    for key, value in (filters or {}).items():
        if value:
            predicates.append(
                text_values[key] == value if key in text_values else false()
            )
    if sort_field is not None and sort_field in text_values:
        sort_value = text_values[sort_field].collate("C")
        stmt = stmt.add_columns(sort_value.label("business_sort")).order_by(
            sort_value.desc()
        )
    limited = (
        stmt.where(*predicates)
        .order_by(row.row_order, row.created_at, row.source_record_id)
        .offset(offset)
        .limit(limit)
        .subquery()
    )
    totals = count_stmt.where(*predicates).subquery()
    page_row = aliased(QualityItemsPageRow, limited)
    page_query = (
        select(page_row, limited.c.inventory_cells, *totals.c)
        .select_from(totals)
        .outerjoin(limited, literal(True))
    )
    if "business_sort" in limited.c:
        page_query = page_query.order_by(limited.c.business_sort.desc())
    page_query = page_query.order_by(
        page_row.row_order, page_row.created_at, page_row.source_record_id
    )
    # One statement keeps the aggregate and page on the same database snapshot.
    results = (await db.execute(page_query)).all()
    total = int(results[0][2])
    flags = zip(derived_fields, results[0][3:], strict=True)
    derived = {key for key, present in flags if present}
    rows = [(result[0], result[1]) for result in results if result[0] is not None]
    return rows, total, derived


async def iter_statistics_rows(
    db: AsyncSession,
    snapshot_id: Any,
    *,
    sort_field: str | None = None,
    project_fields: Sequence[str] | None = None,
) -> AsyncGenerator[Row[tuple[str, datetime, datetime, dict[str, Any]]], None]:
    """Read one mirror in batches, projecting only the cells an aggregate needs."""
    row = QualityItemsPageRow
    cells: SQLColumnExpression[dict[str, Any]] = row.cells
    if project_fields is not None:
        fields = [
            expression
            for key in project_fields
            for expression in (literal(key, type_=String), row.cells[key])
        ]
        cells = func.jsonb_build_object(*fields, type_=JSONB)
    stmt = select(row.source_record_id, row.created_at, row.updated_at, cells).where(
        row.page_snapshot_id == snapshot_id, row.is_deleted.is_(False)
    )
    if sort_field:
        stmt = stmt.order_by(_cell_text(row.cells[sort_field]).collate("C").desc())
    stmt = stmt.order_by(row.row_order, row.created_at, row.source_record_id)
    result = await db.stream(stmt.execution_options(yield_per=256))
    try:
        async for entry in result:
            yield entry
    finally:
        await result.close()


async def list_distinct_cells(
    db: AsyncSession, snapshot_id: Any, column_key: str
) -> Sequence[Any]:
    row = QualityItemsPageRow
    value = row.cells[column_key]
    first = (
        select(value.label("value"), row.row_order, row.created_at)
        .where(
            row.page_snapshot_id == snapshot_id,
            row.is_deleted.is_(False),
            value.is_not(None),
        )
        .distinct(value)
        .order_by(value, row.row_order, row.created_at)
        .subquery()
    )
    return (
        await db.scalars(
            select(first.c.value).order_by(first.c.row_order, first.c.created_at)
        )
    ).all()


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
