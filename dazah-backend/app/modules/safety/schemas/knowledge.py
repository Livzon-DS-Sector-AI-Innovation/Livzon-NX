"""Safety request and response schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SafetyKnowledgeArticleBase(BaseModel):
    """安全知识库文章基础模式（严格对齐 EHS 法规库多维表格字段）"""

    title: str = Field(..., max_length=255, description="法律法规及标准名称")
    article_no: str | None = Field(None, max_length=100, description="法规编号")
    regulation_category: str | None = Field(
        None, max_length=64, description="法规类别"
    )
    source: str | None = Field(None, max_length=255, description="颁布机关")
    promulgation_date: datetime | None = Field(None, description="颁布修订日期")
    implement_date: datetime | None = Field(None, description="实施日期")
    regulation_status: str | None = Field(
        None, max_length=50, description="法规状态"
    )
    regulation_link: str | None = Field(None, description="法规链接")
    summary: str | None = Field(None, description="核心要点总结")
    notes: str | None = Field(None, description="备注")


class SafetyKnowledgeArticleCreate(SafetyKnowledgeArticleBase):
    """创建知识库文章"""

    pass


class SafetyKnowledgeArticleUpdate(BaseModel):
    """更新知识库文章"""

    title: str | None = Field(None, max_length=255, description="法律法规及标准名称")
    article_no: str | None = Field(None, max_length=100, description="法规编号")
    regulation_category: str | None = Field(
        None, max_length=64, description="法规类别"
    )
    source: str | None = Field(None, max_length=255, description="颁布机关")
    promulgation_date: datetime | None = Field(None, description="颁布修订日期")
    implement_date: datetime | None = Field(None, description="实施日期")
    regulation_status: str | None = Field(
        None, max_length=50, description="法规状态"
    )
    regulation_link: str | None = Field(None, description="法规链接")
    summary: str | None = Field(None, description="核心要点总结")
    notes: str | None = Field(None, description="备注")


class SafetyKnowledgeArticleResponse(SafetyKnowledgeArticleBase):
    """安全知识库文章响应"""

    id: uuid.UUID
    feishu_record_id: str | None = None
    feishu_attachments: list[dict[str, Any]] | None = None
    local_attachments: list[dict[str, Any]] | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
