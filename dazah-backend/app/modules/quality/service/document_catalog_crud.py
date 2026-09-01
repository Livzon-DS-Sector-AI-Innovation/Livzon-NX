"""Document catalog CRUD business services.

承接文件目录模块的部门/条目核心 CRUD 与查询逻辑，避免 API 层内联 DB 操作
（分层职责）。API 层负责鉴权、scope 计算、记录级权限校验与 Schema 序列化；
本层负责查询、业务规则（重名/软删复活/级联删除）与持久化，返回 ORM record。
可预期分支抛 AppException，由全局 handler 统一映射为 4xx。
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.exceptions import AppException
from app.modules.quality.models import DocumentDepartment, DocumentEntry


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ─── 部门 CRUD ─────────────────────────────────────────────────────


async def list_document_departments(
    db: AsyncSession,
) -> tuple[list[DocumentDepartment], dict[uuid.UUID, int]]:
    """返回未删除部门列表及各部门在用条目计数。"""
    result = await db.execute(
        select(DocumentDepartment)
        .where(DocumentDepartment.is_deleted.is_(False))
        .order_by(
            DocumentDepartment.sort_order.asc(), DocumentDepartment.name.asc()
        )
    )
    departments = list(result.scalars().all())

    count_result = await db.execute(
        select(DocumentEntry.department_id, func.count(DocumentEntry.id))
        .where(DocumentEntry.is_deleted.is_(False))
        .group_by(DocumentEntry.department_id)
    )
    counts: dict[uuid.UUID, int] = {
        row[0]: row[1] for row in count_result.all()
    }
    return departments, counts


async def create_document_department(
    db: AsyncSession,
    name: str,
    sort_order: int,
) -> DocumentDepartment:
    """创建部门；同名已软删时复活。"""
    cleaned = name.strip()
    result = await db.execute(
        select(DocumentDepartment).where(DocumentDepartment.name == cleaned)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        if not existing.is_deleted:
            raise AppException(message="该部门已存在", status_code=400)
        existing.is_deleted = False
        existing.sort_order = sort_order
        await db.flush()
        return existing

    department = DocumentDepartment(name=cleaned, sort_order=sort_order)
    db.add(department)
    await db.flush()
    return department


async def get_document_department(
    db: AsyncSession, department_id: uuid.UUID
) -> DocumentDepartment:
    """返回未删除部门；不存在抛 404（供 API 层记录级权限校验）。"""
    result = await db.execute(
        select(DocumentDepartment).where(
            DocumentDepartment.id == department_id,
            DocumentDepartment.is_deleted.is_(False),
        )
    )
    department = result.scalar_one_or_none()
    if department is None:
        raise AppException(message="部门不存在", status_code=404)
    return department


async def update_document_department(
    db: AsyncSession,
    department: DocumentDepartment,
    update_data: dict[str, Any],
) -> DocumentDepartment:
    """更新部门（重名校验），返回重新查询的 record。"""
    if "name" in update_data:
        new_name = update_data["name"].strip()
        dup_result = await db.execute(
            select(DocumentDepartment).where(
                DocumentDepartment.name == new_name,
                DocumentDepartment.id != department.id,
            )
        )
        if dup_result.scalar_one_or_none() is not None:
            raise AppException(message="该部门名称已存在", status_code=400)
        update_data["name"] = new_name

    for key, value in update_data.items():
        setattr(department, key, value)
    await db.flush()

    result = await db.execute(
        select(DocumentDepartment).where(DocumentDepartment.id == department.id)
    )
    return result.scalar_one()


async def delete_document_department(
    db: AsyncSession, department: DocumentDepartment
) -> None:
    """软删部门及其全部条目。"""
    department.is_deleted = True
    entry_result = await db.execute(
        select(DocumentEntry).where(
            DocumentEntry.department_id == department.id,
            DocumentEntry.is_deleted.is_(False),
        )
    )
    for entry in entry_result.scalars().all():
        entry.is_deleted = True
    await db.flush()


# ─── 条目 CRUD ──────────────────────────────────────────────────────


def _latest_entry_sort_key(entry: DocumentEntry) -> Any:
    """最新版判定：code 尾部修订号 /NN 最大 → 生效日期 → 更新时间。"""
    m = re.search(r"/(\d+)$", (entry.code or "").strip())
    rev = int(m.group(1)) if m else -1
    return (
        rev,
        entry.effective_date or date.min,
        entry.updated_at or datetime.min,
    )


async def find_latest_entry_by_name(
    db: AsyncSession, core: str
) -> DocumentEntry | None:
    """按文件名称查找最新版条目（精确→模糊→反向包含）。"""
    from sqlalchemy import literal

    base = select(DocumentEntry).where(DocumentEntry.is_deleted.is_(False))
    rows = (await db.execute(base.where(DocumentEntry.name == core))).scalars().all()
    if not rows:
        rows = (
            (
                await db.execute(
                    base.where(
                        DocumentEntry.name.ilike(f"%{_escape_like(core)}%")
                    )
                )
            )
            .scalars()
            .all()
        )
    if not rows:
        rows = (
            (
                await db.execute(
                    base.where(func.strpos(literal(core), DocumentEntry.name) > 0)
                )
            )
            .scalars()
            .all()
        )
    if not rows:
        return None
    return max(rows, key=_latest_entry_sort_key)


async def list_document_entries(
    db: AsyncSession,
    *,
    department_id: uuid.UUID | None,
    keyword: str | None,
    page: int,
    page_size: int,
    scope_dept_ids: list[str] | None,
) -> tuple[list[DocumentEntry], int]:
    """分页返回文件目录条目；scope_dept_ids 由 API 层按数据范围计算。"""
    base_query = select(DocumentEntry).where(DocumentEntry.is_deleted.is_(False))
    count_query = (
        select(func.count())
        .select_from(DocumentEntry)
        .where(DocumentEntry.is_deleted.is_(False))
    )

    if scope_dept_ids is not None:
        base_query = base_query.where(
            DocumentEntry.department_id.in_(scope_dept_ids)
        )
        count_query = count_query.where(
            DocumentEntry.department_id.in_(scope_dept_ids)
        )

    if department_id is not None:
        base_query = base_query.where(DocumentEntry.department_id == department_id)
        count_query = count_query.where(
            DocumentEntry.department_id == department_id
        )

    if keyword:
        pattern = f"%{_escape_like(keyword)}%"
        filters = or_(
            DocumentEntry.name.ilike(pattern),
            DocumentEntry.code.ilike(pattern),
        )
        base_query = base_query.where(filters)
        count_query = count_query.where(filters)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    if department_id is None:
        base_query = base_query.join(
            DocumentDepartment,
            DocumentEntry.department_id == DocumentDepartment.id,
        )
        order_by: list[ColumnElement[Any]] = [
            DocumentDepartment.sort_order.asc(),
            DocumentEntry.seq_no.asc().nulls_last(),
            DocumentEntry.created_at.asc(),
        ]
    else:
        order_by = [
            DocumentEntry.seq_no.asc().nulls_last(),
            DocumentEntry.created_at.asc(),
        ]

    offset = (page - 1) * page_size
    result = await db.execute(
        base_query.order_by(*order_by).offset(offset).limit(page_size)
    )
    return list(result.scalars().all()), total


async def create_document_entry(
    db: AsyncSession, data: dict[str, Any]
) -> DocumentEntry:
    """创建条目；校验部门存在。"""
    dept_result = await db.execute(
        select(DocumentDepartment).where(
            DocumentDepartment.id == data.get("department_id"),
            DocumentDepartment.is_deleted.is_(False),
        )
    )
    if dept_result.scalar_one_or_none() is None:
        raise AppException(message="部门不存在", status_code=404)

    entry = DocumentEntry(**data)
    db.add(entry)
    await db.flush()
    result = await db.execute(select(DocumentEntry).where(DocumentEntry.id == entry.id))
    return result.scalar_one()


async def get_document_entry(
    db: AsyncSession, entry_id: uuid.UUID
) -> DocumentEntry:
    result = await db.execute(
        select(DocumentEntry).where(
            DocumentEntry.id == entry_id,
            DocumentEntry.is_deleted.is_(False),
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise AppException(message="条目不存在", status_code=404)
    return entry


async def update_document_entry(
    db: AsyncSession,
    entry: DocumentEntry,
    update_data: dict[str, Any],
) -> DocumentEntry:
    """更新条目（变更部门时校验部门存在）。"""
    if "department_id" in update_data:
        dept_result = await db.execute(
            select(DocumentDepartment).where(
                DocumentDepartment.id == update_data["department_id"],
                DocumentDepartment.is_deleted.is_(False),
            )
        )
        if dept_result.scalar_one_or_none() is None:
            raise AppException(message="部门不存在", status_code=404)

    for key, value in update_data.items():
        setattr(entry, key, value)
    await db.flush()

    result = await db.execute(
        select(DocumentEntry).where(DocumentEntry.id == entry.id)
    )
    return result.scalar_one()


async def delete_document_entry(
    db: AsyncSession, entry: DocumentEntry
) -> None:
    entry.is_deleted = True
    await db.flush()
