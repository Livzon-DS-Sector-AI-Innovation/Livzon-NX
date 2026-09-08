"""排产计划 Excel 存档：解析、保存与查询。

解析协议与前端 scheduling 页一致：
- 单元格值为标量或空字符串（空值统一为 ""）；
- 合并单元格用 0-based {s: {r, c}, e: {r, c}}；
- 行列不截断，rows 为完整二维数组。
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time
from io import BytesIO
from typing import Any

import openpyxl  # type: ignore[import-untyped]
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.production.schedule_excel_models import ScheduleExcelArchive


def _serialize_cell(value: Any) -> Any:
    """把 openpyxl 单元格值转成 JSON 安全且可读的展示值。

    日期/时间转可读字符串（前端本地解析时日期会显示为序列号，
    这里统一转成可读文本更符合“不转换字段”的业务直觉）；其余原样。
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        # Excel 无独立 date 类型，date 读出为零点 datetime → 显示为日期
        if (
            value.hour == 0
            and value.minute == 0
            and value.second == 0
            and value.microsecond == 0
        ):
            return value.strftime("%Y-%m-%d")
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def parse_workbook_bytes(data: bytes) -> dict[str, Any]:
    """解析 Excel 第一个工作表，返回与前端渲染协议一致的结构。"""
    workbook = openpyxl.load_workbook(BytesIO(data), data_only=True)
    try:
        worksheet = workbook.worksheets[0]
    finally:
        workbook.close()

    rows: list[list[Any]] = []
    for row in worksheet.iter_rows():  # 空行也保留，与前端 blankrows 一致
        rows.append([_serialize_cell(cell.value) for cell in row])

    merges = [
        {
            "s": {"r": rng.min_row - 1, "c": rng.min_col - 1},
            "e": {"r": rng.max_row - 1, "c": rng.max_col - 1},
        }
        for rng in worksheet.merged_cells.ranges
    ]

    from openpyxl.utils import get_column_letter

    col_widths: list[int] = []
    for index in range(1, worksheet.max_column + 1):
        dimension = worksheet.column_dimensions.get(get_column_letter(index))
        width = dimension.width if dimension and dimension.width else 80
        col_widths.append(int(width))

    return {
        "sheet_name": worksheet.title,
        "rows": rows,
        "merges": merges,
        "col_widths": col_widths,
        "row_count": len(rows),
        "col_count": worksheet.max_column,
    }


def serialize_archive(
    archive: ScheduleExcelArchive,
    *,
    created_by_name: str | None = None,
) -> dict[str, Any]:
    """ORM → API 响应（mode=json 友好的 dict）。"""
    return {
        "id": str(archive.id),
        "file_name": archive.file_name,
        "sheet_name": archive.sheet_name,
        "original_path": archive.original_path,
        "rows": archive.rows,
        "merges": archive.merges,
        "col_widths": archive.col_widths,
        "row_count": archive.row_count,
        "col_count": archive.col_count,
        "created_by_name": created_by_name,
        "created_at": (
            archive.created_at.isoformat() if archive.created_at else None
        ),
        "updated_at": (
            archive.updated_at.isoformat() if archive.updated_at else None
        ),
    }


def serialize_archive_summary(
    archive: ScheduleExcelArchive,
    *,
    created_by_name: str | None = None,
) -> dict[str, Any]:
    """列表项（不含 rows，避免大字段传输）。"""
    payload = serialize_archive(archive, created_by_name=created_by_name)
    payload.pop("rows", None)
    payload.pop("merges", None)
    payload.pop("col_widths", None)
    payload.pop("original_path", None)
    return payload


async def create_archive(
    session: AsyncSession,
    *,
    file_name: str,
    sheet_name: str,
    original_path: str,
    rows: list[list[Any]],
    merges: list[dict[str, Any]],
    col_widths: list[int],
    row_count: int,
    col_count: int,
    created_by: uuid.UUID | None = None,
) -> ScheduleExcelArchive:
    archive = ScheduleExcelArchive(
        file_name=file_name,
        sheet_name=sheet_name,
        original_path=original_path,
        rows=rows,
        merges=merges,
        col_widths=col_widths,
        row_count=row_count,
        col_count=col_count,
        created_by=created_by,
    )
    session.add(archive)
    await session.commit()
    await session.refresh(archive)
    return archive


async def list_archives(
    session: AsyncSession,
    *,
    page: int,
    page_size: int,
) -> tuple[list[tuple[ScheduleExcelArchive, str | None]], int]:
    """分页列表，附带上传人姓名（created_by 外键 join identity.users）。"""
    from app.platform.identity.models import User

    total = await session.scalar(
        select(func.count(ScheduleExcelArchive.id)).where(
            ScheduleExcelArchive.is_deleted.is_(False)
        )
    )
    query = (
        select(ScheduleExcelArchive, User.name)
        .outerjoin(User, User.id == ScheduleExcelArchive.created_by)
        .where(ScheduleExcelArchive.is_deleted.is_(False))
        .order_by(ScheduleExcelArchive.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await session.execute(query)
    items = [(archive, name) for archive, name in result.all()]
    return items, int(total or 0)


async def get_user_name(
    session: AsyncSession, user_id: uuid.UUID | None
) -> str | None:
    """按用户 ID 取姓名（用于详情等单条响应）。"""
    if user_id is None:
        return None
    from app.platform.identity.models import User

    name = await session.scalar(
        select(User.name).where(User.id == user_id)
    )
    return name


async def get_archive(
    session: AsyncSession, archive_id: uuid.UUID
) -> ScheduleExcelArchive | None:
    result = await session.execute(
        select(ScheduleExcelArchive).where(
            ScheduleExcelArchive.id == archive_id,
            ScheduleExcelArchive.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def delete_archive(
    session: AsyncSession,
    archive: ScheduleExcelArchive,
    *,
    deleted_by: uuid.UUID | None = None,
) -> None:
    archive.is_deleted = True
    archive.updated_by = deleted_by
    await session.commit()
