"""排产计划 Excel 存档模型。

保存上传的排产 Excel 解析结果（全量行列 + 合并单元格 + 列宽），
并保留原始文件路径用于下载核对。rows 为不截断的二维数组，
结构沿用前端 scheduling 页的渲染协议：单元格值为标量或空字符串，
合并单元格用 0-based {s:{r,c},e:{r,c}} 表达。
"""
from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class ScheduleExcelArchive(BaseModel):
    """排产计划 Excel 存档记录"""

    __tablename__ = "schedule_excel_archives"
    __table_args__ = {"schema": "production"}

    product_code: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="FA",
        comment="产品代码（如 FA/MC/DR），存档按产品隔离",
    )
    file_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="原始文件名"
    )
    sheet_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="展示的工作表名（第一个 sheet）"
    )
    original_path: Mapped[str] = mapped_column(
        String(512), nullable=False, comment="原件相对路径（uploads/ 下）"
    )
    rows: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, comment="全量二维数组（不截断）"
    )
    merges: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, comment="合并单元格（0-based）"
    )
    col_widths: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, comment="各列宽度"
    )
    row_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="数据行数"
    )
    col_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="数据列数"
    )
