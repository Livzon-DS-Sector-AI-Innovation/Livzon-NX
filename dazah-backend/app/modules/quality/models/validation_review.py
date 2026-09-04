"""验证方案与报告 AI 审核记录模型。

审核会话与附件文件两张表，镜像 deviation_ai_session 的结构：
- validation_review_records：一次 AI 审核会话（输入快照 + 输出结论）
- validation_review_files：会话下挂载的 VP/VR 文档（上传或从文件管理引用）
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class ValidationReviewRecord(BaseModel):
    __tablename__ = "validation_review_records"
    __table_args__ = {"schema": "quality"}

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default="",
    )
    # 审核来源：upload=页面上传文档；entry=从文件管理目录条目引用
    review_mode: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="upload",
        server_default="upload",
    )
    # draft / processing / completed / failed
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="draft",
        server_default="draft",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 输入快照：基准匹配结果 + 引用清单 + 方案/报告摘要（审核依据，便于追溯）
    input_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # 输出结论：{summary, stats, findings, basis_used}
    output_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ValidationReviewFile(BaseModel):
    __tablename__ = "validation_review_files"
    __table_args__ = {"schema": "quality"}

    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    # plan=验证/确认方案；report=验证/确认报告
    doc_kind: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="plan",
        server_default="plan",
    )
    # 文件来源：upload=本次上传；entry_attachment=文件管理条目附件
    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="upload",
        server_default="upload",
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # pending / completed / failed
    parse_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
