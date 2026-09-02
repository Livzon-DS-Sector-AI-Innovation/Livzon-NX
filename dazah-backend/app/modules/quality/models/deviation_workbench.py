"""偏差工作台 ORM models。

偏差工作台：独立生成调查报告的页面。每次生成落库为一条可检索的工作台记录
（来源 = 报告记录 / 手动输入 + 附件），保留检索到的参考内容（context_snapshot）
与完整调查报告（report_payload / report_md），并支持单行提示词配置。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel

# 单行设置记录的固定主键（get-or-create 用）
WORKBENCH_SETTINGS_ID = "10000000-0000-0000-0000-000000000001"


class DeviationWorkbenchSettings(BaseModel):
    __tablename__ = "deviation_workbench_settings"
    __table_args__ = {"schema": "quality"}

    report_system_prompt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
        comment="调查报告系统提示词（可修改）",
    )


class DeviationWorkbenchReport(BaseModel):
    __tablename__ = "deviation_workbench_reports"
    __table_args__ = (
        Index(
            "uq_quality_deviation_workbench_reports_code",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "quality"},
    )

    code: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="工作台记录编号（自动生成 WB-YYYYMM###）"
    )
    source_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="manual",
        server_default="manual",
        comment="信息来源：report_record=偏差管理报告记录，manual=手动输入/附件",
    )
    source_record_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="来源报告记录 ID（飞书 record_id）"
    )
    deviation_summary: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="偏差摘要（来源记录或 AI 生成）"
    )
    manual_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachments: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, default=list, comment="附件描述（原件+转MD产物+图片资产）"
    )
    context_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="检索到的参考内容（历史偏差/文件管理）"
    )
    report_payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="结构化调查报告（5M1E+直接/根本原因+结论/建议）"
    )
    report_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="processing",
        server_default="processing",
        comment="processing/completed/failed",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="删除操作人"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="删除时间"
    )
