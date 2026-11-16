"""作业安全监护人名单管理：列表（按车间汇总）、增删改、Excel 导出。

名单以最新一次导入为准（导入整表替换），行级手工增删改在两次导入
之间生效；导出按当前筛选条件生成 xlsx（车间→姓名排序）。
"""

from __future__ import annotations

import io
from datetime import date
from uuid import UUID

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.modules.safety.models import GuardianRoster
from app.modules.safety.schemas.guardian_roster import (
    GuardianRosterCreate,
    GuardianRosterListResponse,
    GuardianRosterUpdate,
)
from app.platform.audit.service import record_audit_log
from app.platform.identity.models import User

EXPORT_HEADERS = (
    "姓名",
    "车间/部门",
    "联系电话",
    "岗位",
    "考试分数",
    "考试名称",
    "考试日期",
    "备注",
    "来源文件",
)


async def get_guardian(db: AsyncSession, guardian_id: UUID) -> GuardianRoster:
    result = await db.execute(
        select(GuardianRoster).where(
            GuardianRoster.id == guardian_id,
            GuardianRoster.is_deleted.is_(False),
        )
    )
    guardian = result.scalar_one_or_none()
    if guardian is None:
        raise NotFoundException("监护人", str(guardian_id))
    return guardian


async def create_guardian(
    db: AsyncSession, data: GuardianRosterCreate, current_user: User
) -> GuardianRoster:
    guardian = GuardianRoster(
        **data.model_dump(),
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(guardian)
    await db.flush()
    await record_audit_log(
        db,
        action="create",
        resource_type="guardian_roster",
        resource_id=guardian.id,
        user_id=current_user.id,
        new_value={"person": guardian.person_name},
    )
    return guardian


async def update_guardian(
    db: AsyncSession,
    guardian_id: UUID,
    data: GuardianRosterUpdate,
    current_user: User,
) -> GuardianRoster:
    guardian = await get_guardian(db, guardian_id)
    patch = data.model_dump(exclude_unset=True, exclude_none=True)
    if patch:
        for field, value in patch.items():
            setattr(guardian, field, value)
        guardian.updated_by = current_user.id
        await db.flush()
        await record_audit_log(
            db,
            action="update",
            resource_type="guardian_roster",
            resource_id=guardian.id,
            user_id=current_user.id,
        )
    return guardian


async def delete_guardian(
    db: AsyncSession, guardian_id: UUID, current_user: User
) -> None:
    guardian = await get_guardian(db, guardian_id)
    guardian.is_deleted = True
    guardian.updated_by = current_user.id
    await db.flush()
    await record_audit_log(
        db,
        action="delete",
        resource_type="guardian_roster",
        resource_id=guardian.id,
        user_id=current_user.id,
    )


async def list_guardians(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    workshop: str | None = None,
    keyword: str | None = None,
) -> GuardianRosterListResponse:
    conditions: list[ColumnElement[bool]] = [GuardianRoster.is_deleted.is_(False)]
    if workshop:
        conditions.append(GuardianRoster.workshop == workshop)
    if keyword:
        like = f"%{keyword}%"
        conditions.append(
            GuardianRoster.person_name.ilike(like)
            | GuardianRoster.workshop.ilike(like)
            | GuardianRoster.phone.ilike(like)
            | GuardianRoster.position.ilike(like)
        )
    total = await db.scalar(select(func.count(GuardianRoster.id)).where(*conditions))
    result = await db.execute(
        select(GuardianRoster)
        .where(*conditions)
        .order_by(GuardianRoster.workshop.asc(), GuardianRoster.person_name.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(result.scalars().all())
    workshop_counts = await db.execute(
        select(
            GuardianRoster.workshop,
            func.count(GuardianRoster.id),
        )
        .where(GuardianRoster.is_deleted.is_(False))
        .group_by(GuardianRoster.workshop)
        .order_by(GuardianRoster.workshop.asc())
    )
    return GuardianRosterListResponse(
        items=items,
        total=total or 0,
        page=page,
        page_size=page_size,
        workshops=[
            {"workshop": row[0], "count": row[1]} for row in workshop_counts.all()
        ],
    )


async def export_guardians_xlsx(
    db: AsyncSession,
    *,
    workshop: str | None = None,
    keyword: str | None = None,
) -> tuple[bytes, str]:
    """按筛选条件导出全部名单（不分页）为 xlsx 字节。"""
    conditions: list[ColumnElement[bool]] = [GuardianRoster.is_deleted.is_(False)]
    if workshop:
        conditions.append(GuardianRoster.workshop == workshop)
    if keyword:
        like = f"%{keyword}%"
        conditions.append(
            GuardianRoster.person_name.ilike(like)
            | GuardianRoster.workshop.ilike(like)
            | GuardianRoster.phone.ilike(like)
            | GuardianRoster.position.ilike(like)
        )
    result = await db.execute(
        select(GuardianRoster)
        .where(*conditions)
        .order_by(GuardianRoster.workshop.asc(), GuardianRoster.person_name.asc())
    )
    rows = list(result.scalars().all())

    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "监护人名单"
    sheet.append(EXPORT_HEADERS)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
    for item in rows:
        sheet.append(
            [
                item.person_name,
                item.workshop,
                item.phone or "",
                item.position or "",
                item.score if item.score is not None else "",
                item.exam_name or "",
                (
                    item.exam_date.isoformat()
                    if isinstance(item.exam_date, date)
                    else ""
                ),
                item.remark or "",
                item.source_file or "",
            ]
        )
    for column, width in zip(
        "ABCDEFGHI", (14, 16, 15, 14, 10, 14, 13, 24, 30), strict=False
    ):
        sheet.column_dimensions[column].width = width
    buffer = io.BytesIO()
    workbook.save(buffer)
    today = date.today().strftime("%Y%m%d")
    name_part = workshop or "全部车间"
    filename = f"监护人名单_{name_part}_{today}.xlsx"
    return buffer.getvalue(), filename


__all__ = [
    "create_guardian",
    "delete_guardian",
    "export_guardians_xlsx",
    "get_guardian",
    "list_guardians",
    "update_guardian",
]
