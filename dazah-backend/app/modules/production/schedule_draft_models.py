"""FA 排产草稿生成历史模型。

每次生成/导出草稿落一条工作台记录（参数 + 摘要 + 校验快照 + 逐日事件，
导出时附 Excel 文件）；同一参数重复生成去重更新而非新增。历史仅是
过程记录，不生效、不进看板——排产表仍是唯一事实源，草稿需上传
排产计划页后才成为正式排产。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class ScheduleDraftRecord(BaseModel):
    """排产草稿生成历史（按产品隔离，同参数去重）"""

    __tablename__ = "schedule_draft_records"
    __table_args__ = (
        Index(
            "ix_schedule_draft_records_hash",
            "product_code",
            "params_hash",
        ),
        {"schema": "production"},
    )

    product_code: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="FA",
        comment="产品代码（当前仅 FA）",
    )
    # 归一化后的生成参数（对齐后的周期、批号、跳过日、占用窗口）
    params: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # 参数指纹（md5），同参数重复生成据此去重更新
    params_hash: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="参数指纹，同参数去重用"
    )
    days: Mapped[list] = mapped_column(JSONB, nullable=False, comment="逐日事件快照")
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False, comment="摘要快照")
    validation: Mapped[dict] = mapped_column(
        JSONB, nullable=False, comment="一期校验报告快照"
    )
    file_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="导出的 Excel 文件名（导出后非空）"
    )
    original_path: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="导出文件相对 uploads 的路径"
    )
    downloaded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="最近导出时间（仅预览未导出为空）",
    )
    note: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="备注（预留）"
    )
