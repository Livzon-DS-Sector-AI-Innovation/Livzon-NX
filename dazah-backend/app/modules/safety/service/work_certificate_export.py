"""持证人员台账 Excel 导出：按证件类别分子表（与汇总表同构）。

每个有数据的类别一个子表，子表名即类别中文 label（导入侧
``match_sheet_rule`` 会精确命中，导出文件可直接再导入形成闭环）。
列头沿用汇总表写法（姓名/车间/取证日期/有效日期/证书编号等），
日期写原生日期单元格，保证回导时 ``parse_date_cell`` 可直接解析。
"""

from __future__ import annotations

import io
from datetime import date
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.safety.models import SpecialWorkCertificate
from app.modules.safety.service.work_permit_templates import (
    CERTIFICATE_CATEGORIES,
)

# 状态 code → 台账展示中文（与前端 STATUS_META 口径一致）
STATUS_LABELS: dict[str, str] = {
    "valid": "有效",
    "expiring": "即将到期",
    "expired": "已过期",
    "revoked": "已吊销",
}

# 导出列（表头写法与导入 COLUMN_LABELS 兼容，保证回导可解析）
_EXPORT_COLUMNS: tuple[str, ...] = (
    "姓名",
    "车间",
    "证书编号",
    "取证日期",
    "有效日期",
    "发证机关",
    "准操项目",
    "状态",
    "备注",
)

# 前两列外的日期列（0-based 列号：3=取证日期, 4=有效日期）
_DATE_COLUMN_INDEXES = (3, 4)

_HEADER_FONT = Font(bold=True)
_CENTER = Alignment(horizontal="center")

__all__ = ["STATUS_LABELS", "export_certificates_workbook"]


def _cert_row(cert: SpecialWorkCertificate) -> list[Any]:
    return [
        cert.person_name,
        cert.department or "",
        cert.certificate_no or "",
        cert.issue_date,
        cert.expiry_date,
        cert.issuing_authority or "",
        cert.qualification_scope or "",
        STATUS_LABELS.get(cert.status, cert.status),
        cert.remark or "",
    ]


def build_workbook(certs: list[SpecialWorkCertificate]) -> Workbook:
    """按类别分组建工作簿：类别中文 label 为子表名，仅含有数据的类别。"""
    by_category: dict[str, list[SpecialWorkCertificate]] = {}
    for cert in certs:
        by_category.setdefault(cert.certificate_category, []).append(cert)

    workbook = Workbook()
    active = workbook.active
    if active is not None:
        workbook.remove(active)

    for item in CERTIFICATE_CATEGORIES:
        category = item["value"]
        rows = by_category.get(category)
        if not rows:
            continue
        rows.sort(
            key=lambda cert: (
                cert.expiry_date is None,
                cert.expiry_date or date.min,
                cert.person_name,
            )
        )
        sheet = workbook.create_sheet(title=item["label"])
        sheet.append([f"{item['label']}台账"])
        title_cell = sheet.cell(row=1, column=1)
        title_cell.font = Font(bold=True, size=12)
        sheet.append(list(_EXPORT_COLUMNS))
        for col_index in range(1, len(_EXPORT_COLUMNS) + 1):
            header_cell = sheet.cell(row=2, column=col_index)
            header_cell.font = _HEADER_FONT
            header_cell.alignment = _CENTER
        for row_index, cert in enumerate(rows, start=3):
            sheet.append(_cert_row(cert))
            for col_index in _DATE_COLUMN_INDEXES:
                sheet.cell(
                    row=row_index, column=col_index + 1
                ).number_format = "yyyy-mm-dd"
        sheet.freeze_panes = "A3"
    return workbook


async def export_certificates_workbook(
    db: AsyncSession,
) -> tuple[bytes, str]:
    """导出全部未删除证件，返回 (xlsx 字节, 文件名)。"""
    result = await db.execute(
        select(SpecialWorkCertificate)
        .where(SpecialWorkCertificate.is_deleted.is_(False))
        .order_by(SpecialWorkCertificate.person_name)
    )
    certs = list(result.scalars().all())
    workbook = build_workbook(certs)
    buffer = io.BytesIO()
    workbook.save(buffer)
    filename = f"持证人员汇总表_{date.today().strftime('%Y%m%d')}.xlsx"
    return buffer.getvalue(), filename
