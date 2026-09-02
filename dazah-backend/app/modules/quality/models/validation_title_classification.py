"""Validation AI classification cache model."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class ValidationTitleClassification(BaseModel):
    """验证确认名称的 AI 分类缓存。

    真实年度台账没有"验证类别"列，平台用 LLM 按确认名称推断分类；
    以名称（去空白）为唯一键缓存，避免列表每次都调用 LLM。
    """

    __tablename__ = "validation_title_classifications"
    __table_args__ = {"schema": "quality"}

    title: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ai", server_default="ai"
    )
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sample_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    classified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
