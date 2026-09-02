"""历史偏差 ORM models。

历史偏差记录：独立于偏差台账/报告记录的历史偏差台账，正文由 AI 从附件提取
（偏差事件 / 偏差内容(5M1E) / 调查结论(直接原因+根本原因)），附件复用文件管理
同套 doc/docx/wps → 标准 MD（保留表格与图片）转换管线。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class HistoricalDeviation(BaseModel):
    __tablename__ = "historical_deviations"
    __table_args__ = (
        Index(
            "uq_quality_historical_deviations_code",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "quality"},
    )

    code: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="历史偏差编号（自动生成 HD-YYYYMM###）"
    )
    deviation_event: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="偏差事件（AI 从附件提取）"
    )
    deviation_content: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="偏差内容（AI 提取，按人机料法环测总结）"
    )
    direct_cause: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="调查结论-直接原因（AI 提取）"
    )
    root_cause: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="调查结论-根本原因（AI 提取）"
    )
    investigation_conclusion: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="调查结论汇总（可人工编辑）"
    )
    attachments: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, default=list
    )
    ai_extract_payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="AI 提取原始结果（审计追溯）"
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="删除操作人"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="删除时间"
    )
