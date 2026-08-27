"""CPV Import Task ORM model."""

import uuid
from typing import Any

from sqlalchemy import JSON, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class CpvImportTask(BaseModel):
    """持续工艺验证导入任务表"""

    __tablename__ = "cpv_import_tasks"
    __table_args__ = {"schema": "quality", "comment": "CPV导入任务表"}

    file_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="文件名"
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, comment="产品ID"
    )
    data_type: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="数据类型: CPP/CQA"
    )
    import_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="导入模式: create/update/overwrite"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        comment="状态: pending/processing/completed/failed",
    )
    total_rows: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="总行数"
    )
    success_rows: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="成功行数"
    )
    failed_rows: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="失败行数"
    )
    error_details: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="错误详情"
    )
