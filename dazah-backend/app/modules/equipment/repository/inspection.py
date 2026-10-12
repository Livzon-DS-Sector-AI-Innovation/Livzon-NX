"""Inspection repository: data access for inspection tasks, photos."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.equipment.models.equipment import Equipment
from app.modules.equipment.models.inspection import (
    InspectionPhoto,
    InspectionTask,
)
from app.modules.equipment.models.inspection_template import (
    InspectionRecord,
)


# ═══════════ 路线 ═══════════
async def get_max_task_no(db: AsyncSession) -> str | None:
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"IT-{today}-"
    stmt = (
        select(InspectionTask.task_no)
        .where(InspectionTask.task_no.like(f"{prefix}%"))
        .order_by(InspectionTask.task_no.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_task(db: AsyncSession, data: dict[str, Any]) -> InspectionTask:
    task = InspectionTask(**data)
    db.add(task)
    await db.flush()
    # eager re-fetch 加载关联，避免 _task_to_response 访问关系时 MissingGreenlet
    result = await db.execute(
        select(InspectionTask)
        .options(
            selectinload(InspectionTask.equipment),
            selectinload(InspectionTask.assignee),
        )
        .where(InspectionTask.id == task.id)
    )
    return result.scalar_one()


async def get_task_by_id(db: AsyncSession, task_id: uuid.UUID) -> InspectionTask | None:
    stmt = (
        select(InspectionTask)
        .options(
            selectinload(InspectionTask.equipment),
            selectinload(InspectionTask.assignee),
        )
        .where(
            InspectionTask.id == task_id,
            InspectionTask.is_deleted == False,  # noqa: E712
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_tasks(
    db: AsyncSession,
    status: str | None = None,
    exclude_status: str | None = None,
    assigned_to: uuid.UUID | None = None,
    equipment_id: uuid.UUID | None = None,
    planned_time_from: datetime | None = None,
    planned_time_to: datetime | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[InspectionTask], int]:
    conditions = [InspectionTask.is_deleted == False]  # noqa: E712
    if status:
        conditions.append(InspectionTask.status == status)
    if exclude_status:
        conditions.append(InspectionTask.status != exclude_status)
    if assigned_to:
        conditions.append(InspectionTask.assigned_to == assigned_to)
    if equipment_id:
        conditions.append(
            or_(
                InspectionTask.equipment_id == equipment_id,
                cast(InspectionTask.equipment_ids, String).like(f'%"{equipment_id}"%'),
            )
        )
    if planned_time_from:
        conditions.append(InspectionTask.planned_time >= planned_time_from)
    if planned_time_to:
        conditions.append(InspectionTask.planned_time <= planned_time_to)

    count_stmt = select(func.count(InspectionTask.id)).where(and_(*conditions))
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(InspectionTask)
        .options(
            selectinload(InspectionTask.equipment),
            selectinload(InspectionTask.assignee),
        )
        .where(and_(*conditions))
        .order_by(
            InspectionTask.planned_time.desc(),
            InspectionTask.created_at.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


async def get_task_equipment_completed_ids(
    db: AsyncSession, task_id: uuid.UUID
) -> set[uuid.UUID]:
    stmt = (
        select(InspectionRecord.equipment_id)
        .where(
            InspectionRecord.task_id == task_id,
            InspectionRecord.is_deleted == False,  # noqa: E712
        )
        .distinct()
    )
    result = await db.execute(stmt)
    return {row[0] for row in result.all()}


# ═══════════ 巡检记录 ═══════════
async def soft_delete_records_by_task_equipment(
    db: AsyncSession, task_id: uuid.UUID, equipment_id: uuid.UUID
) -> None:
    """软删除某任务+设备的已有巡检记录（用于重新提交时替换旧数据）"""
    from sqlalchemy import update

    stmt = (
        update(InspectionRecord)
        .where(
            InspectionRecord.task_id == task_id,
            InspectionRecord.equipment_id == equipment_id,
            InspectionRecord.is_deleted == False,  # noqa: E712
        )
        .values(is_deleted=True)
    )
    await db.execute(stmt)


async def create_inspection_records(
    db: AsyncSession, records_data: list[dict[str, Any]]
) -> list[InspectionRecord]:
    objs = [InspectionRecord(**r) for r in records_data]
    db.add_all(objs)
    await db.flush()
    return objs


async def get_records_by_task(
    db: AsyncSession, task_id: uuid.UUID
) -> list[InspectionRecord]:
    stmt = (
        select(InspectionRecord)
        .options(selectinload(InspectionRecord.template_item))
        .where(
            InspectionRecord.task_id == task_id,
            InspectionRecord.is_deleted == False,  # noqa: E712
        )
        .order_by(InspectionRecord.created_at)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ═══════════ 照片 ═══════════
async def create_photo(db: AsyncSession, data: dict[str, Any]) -> InspectionPhoto:
    # equipment_id 为 None 时（线路巡检照片）不传入构造
    if data.get("equipment_id") is None:
        data = {k: v for k, v in data.items() if k != "equipment_id" or v is not None}
    photo = InspectionPhoto(**data)
    db.add(photo)
    await db.flush()
    await db.refresh(photo)
    return photo


async def get_photos_by_task(
    db: AsyncSession, task_id: uuid.UUID
) -> list[InspectionPhoto]:
    stmt = (
        select(InspectionPhoto)
        .where(
            InspectionPhoto.task_id == task_id,
            InspectionPhoto.is_deleted == False,  # noqa: E712
        )
        .order_by(InspectionPhoto.uploaded_at)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_photos_by_task_and_equipment(
    db: AsyncSession, task_id: uuid.UUID, equipment_id: uuid.UUID
) -> list[InspectionPhoto]:
    stmt = (
        select(InspectionPhoto)
        .where(
            InspectionPhoto.task_id == task_id,
            InspectionPhoto.equipment_id == equipment_id,
            InspectionPhoto.is_deleted == False,  # noqa: E712
        )
        .order_by(InspectionPhoto.uploaded_at)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_photo_by_id(
    db: AsyncSession, photo_id: uuid.UUID
) -> InspectionPhoto | None:
    stmt = select(InspectionPhoto).where(
        InspectionPhoto.id == photo_id,
        InspectionPhoto.is_deleted == False,  # noqa: E712
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def delete_photo(db: AsyncSession, photo_id: uuid.UUID) -> bool:
    photo = await get_photo_by_id(db, photo_id)
    if not photo:
        return False
    photo.is_deleted = True
    await db.flush()
    return True


async def count_photos_by_task(db: AsyncSession, task_id: uuid.UUID) -> int:
    stmt = select(func.count(InspectionPhoto.id)).where(
        InspectionPhoto.task_id == task_id,
        InspectionPhoto.is_deleted == False,  # noqa: E712
    )
    result = await db.execute(stmt)
    return result.scalar_one()


async def get_equipment_names_by_ids(
    db: AsyncSession, equipment_ids: list[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """根据设备ID列表批量获取设备名称映射"""
    if not equipment_ids:
        return {}
    stmt = select(Equipment.id, Equipment.name).where(
        Equipment.id.in_(equipment_ids),
        Equipment.is_deleted == False,  # noqa: E712
    )
    result = await db.execute(stmt)
    return {row[0]: row[1] for row in result.all()}


# ═══════════ 线路地点配置（新） ═══════════


