"""Safety request and response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.safety.schemas.enums import (
    KnowledgeCategory,
)


class SafetyKnowledgeArticleBase(BaseModel):
    """安全知识库文章基础模式"""

    title: str = Field(..., max_length=255, description="文章标题")
    summary: str | None = Field(None, description="摘要")
    content: str | None = Field(None, description="正文内容")
    tags: str | None = Field(None, max_length=500, description="标签（逗号分隔）")
    category: KnowledgeCategory = Field(KnowledgeCategory.OTHER, description="分类")


class SafetyKnowledgeArticleCreate(SafetyKnowledgeArticleBase):
    """创建知识库文章"""

    pass


class SafetyKnowledgeArticleUpdate(BaseModel):
    """更新知识库文章"""

    title: str | None = Field(None, max_length=255, description="文章标题")
    summary: str | None = Field(None, description="摘要")
    content: str | None = Field(None, description="正文内容")
    tags: str | None = Field(None, max_length=500, description="标签（逗号分隔）")
    category: KnowledgeCategory | None = Field(None, description="分类")
    status: str | None = Field(None, max_length=32, description="状态")


class SafetyKnowledgeArticleResponse(SafetyKnowledgeArticleBase):
    """安全知识库文章响应"""

    id: uuid.UUID
    status: str
    view_count: int = 0
    attachment_path: str | None = None
    attachment_original_name: str | None = None
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


