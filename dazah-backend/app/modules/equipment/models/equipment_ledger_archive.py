"""设备台账 Excel 上传存档 ORM 模型。

每次台账导入成功后保存一份只读存档（解析后的全量表格结构 +
原件路径 + 导入结果摘要），供回看历次上传的台账全貌；
删除存档只删快照，不影响已导入的台账数据。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class EquipmentLedgerArchive(BaseModel):
    """设备台账 Excel 上传存档记录"""

    __tablename__ = "equipment_ledger_archives"
    __table_args__ = {"schema": "equipment"}

    workshop_code: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        server_default="201-1",
        comment="归属车间代码（如 101-1 / 201-1）",
    )
    file_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="原始文件名"
    )
    sheet_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="展示的工作表名（第一个可见 sheet）"
    )
    original_path: Mapped[str] = mapped_column(
        String(512), nullable=False, comment="原件相对路径（uploads/ 下）"
    )
    rows: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, comment="全量二维数组（不截断）"
    )
    merges: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, comment="合并单元格（0-based）"
    )
    col_widths: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, comment="各列宽度"
    )
    row_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="数据行数"
    )
    col_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="数据列数"
    )
    import_summary: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="导入结果摘要（created/updated/failed/flagged 等）",
    )
