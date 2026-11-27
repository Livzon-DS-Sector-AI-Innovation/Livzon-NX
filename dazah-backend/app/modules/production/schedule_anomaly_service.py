"""排产异常记录：人工登记计划外变化（延后/减批/补种/染菌/其他）。

看板与排产表只呈现「当前正常状态」，本服务提供异常的存与查：
列表按产品/批次/类型/日期筛选并分页，新增校验类型枚举与必填原因。
不与排产 Excel 比对或上传流程耦合，也没有审批流转。
"""
from __future__ import annotations

import io
import uuid
from datetime import date
from typing import Any

import openpyxl
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.production.schedule_anomaly_models import ScheduleAnomalyRecord
from app.platform.identity.models import User

ANOMALY_TYPE_LABELS: dict[str, str] = {
    "delayed": "延后",
    "reduced": "减批",
    "reseeded": "补种",
    "contamination": "染菌",
    "other": "其他",
}
ANOMALY_TYPES = frozenset(ANOMALY_TYPE_LABELS)


class AnomalyValidationError(ValueError):
    """异常记录入参不合法（映射 400）。"""


def _anomaly_filter_conditions(
    *,
    product_code: str,
    batch_no: str | None,
    anomaly_type: str | None,
    date_from: date | None,
    date_to: date | None,
) -> list[Any]:
    """列表与导出共用的筛选条件（未含分页）。"""
    conditions: list[Any] = [
        ScheduleAnomalyRecord.is_deleted.is_(False),
        ScheduleAnomalyRecord.product_code == product_code,
    ]
    if batch_no:
        conditions.append(ScheduleAnomalyRecord.batch_no == batch_no.strip())
    if anomaly_type:
        conditions.append(ScheduleAnomalyRecord.anomaly_type == anomaly_type)
    if date_from is not None:
        conditions.append(ScheduleAnomalyRecord.event_date >= date_from)
    if date_to is not None:
        conditions.append(ScheduleAnomalyRecord.event_date <= date_to)
    return conditions


async def list_anomalies(
    session: AsyncSession,
    *,
    product_code: str,
    batch_no: str | None = None,
    anomaly_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[tuple[ScheduleAnomalyRecord, str | None]], int]:
    """按筛选条件分页返回异常记录及其标记人姓名。"""
    conditions = _anomaly_filter_conditions(
        product_code=product_code,
        batch_no=batch_no,
        anomaly_type=anomaly_type,
        date_from=date_from,
        date_to=date_to,
    )

    total = (
        await session.execute(
            select(func.count())
            .select_from(ScheduleAnomalyRecord)
            .where(*conditions)
        )
    ).scalar_one()
    rows = (
        await session.execute(
            select(ScheduleAnomalyRecord, User.name)
            .outerjoin(User, User.id == ScheduleAnomalyRecord.created_by)
            .where(*conditions)
            .order_by(
                ScheduleAnomalyRecord.event_date.desc(),
                ScheduleAnomalyRecord.created_at.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return [(record, name) for record, name in rows], int(total)


# 导出上限：异常记录为人工登记、频次低，5000 条足够覆盖日常台账
EXPORT_ROW_LIMIT = 5000


async def list_anomalies_for_export(
    session: AsyncSession,
    *,
    product_code: str,
    batch_no: str | None = None,
    anomaly_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[tuple[ScheduleAnomalyRecord, str | None]]:
    """导出用：与列表同筛选，不分页，按导出上限截断。"""
    conditions = _anomaly_filter_conditions(
        product_code=product_code,
        batch_no=batch_no,
        anomaly_type=anomaly_type,
        date_from=date_from,
        date_to=date_to,
    )
    rows = (
        await session.execute(
            select(ScheduleAnomalyRecord, User.name)
            .outerjoin(User, User.id == ScheduleAnomalyRecord.created_by)
            .where(*conditions)
            .order_by(
                ScheduleAnomalyRecord.event_date.desc(),
                ScheduleAnomalyRecord.created_at.desc(),
            )
            .limit(EXPORT_ROW_LIMIT)
        )
    ).all()
    return [(record, name) for record, name in rows]


def build_anomalies_workbook(
    rows: list[tuple[ScheduleAnomalyRecord, str | None]],
) -> bytes:
    """把异常记录组装为 xlsx 字节流（导出用，单工作表）。"""
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None  # 新建工作簿必含默认工作表
    sheet.title = "排产异常记录"
    sheet.append(
        ["类型", "批号", "罐号", "发生日期", "原因", "备注", "标记人", "标记时间"]
    )
    for record, name in rows:
        sheet.append(
            [
                ANOMALY_TYPE_LABELS.get(record.anomaly_type, record.anomaly_type),
                record.batch_no,
                record.tank_no or "",
                record.event_date.isoformat() if record.event_date else "",
                record.reason or "",
                record.remark or "",
                name or "",
                (
                    record.created_at.strftime("%Y-%m-%d %H:%M")
                    if record.created_at
                    else ""
                ),
            ]
        )
    # 原因/备注列适当加宽，避免导出后全部挤在一列
    for column, width in (("B", 14), ("E", 40), ("F", 24), ("G", 12)):
        sheet.column_dimensions[column].width = width
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


async def create_anomaly(
    session: AsyncSession,
    *,
    product_code: str,
    batch_no: str,
    anomaly_type: str,
    event_date: date,
    reason: str,
    tank_no: str | None = None,
    remark: str | None = None,
    created_by: uuid.UUID | None = None,
) -> ScheduleAnomalyRecord:
    """新增一条异常记录；类型与必填字段在此统一校验。"""
    batch_no = batch_no.strip()
    reason = reason.strip()
    tank_no = (tank_no or "").strip() or None
    remark = (remark or "").strip() or None
    if not batch_no:
        raise AnomalyValidationError("批号不能为空")
    if len(batch_no) > 64:
        raise AnomalyValidationError("批号不能超过 64 个字符")
    if anomaly_type not in ANOMALY_TYPES:
        raise AnomalyValidationError("不支持的异常类型")
    if not reason:
        raise AnomalyValidationError("原因不能为空")
    if len(reason) > 255:
        raise AnomalyValidationError("原因不能超过 255 个字符")

    record = ScheduleAnomalyRecord(
        product_code=product_code,
        batch_no=batch_no,
        tank_no=tank_no,
        anomaly_type=anomaly_type,
        event_date=event_date,
        reason=reason,
        remark=remark,
        created_by=created_by,
        updated_by=created_by,
    )
    session.add(record)
    await session.flush()
    return record


def serialize_anomaly(
    record: ScheduleAnomalyRecord,
    *,
    created_by_name: str | None = None,
) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "product_code": record.product_code,
        "batch_no": record.batch_no,
        "tank_no": record.tank_no,
        "anomaly_type": record.anomaly_type,
        "anomaly_type_label": ANOMALY_TYPE_LABELS.get(
            record.anomaly_type, record.anomaly_type
        ),
        "event_date": record.event_date.isoformat() if record.event_date else None,
        "reason": record.reason,
        "remark": record.remark,
        "created_by_name": created_by_name,
        "created_at": (
            record.created_at.isoformat() if record.created_at else None
        ),
        "updated_at": (
            record.updated_at.isoformat() if record.updated_at else None
        ),
    }
