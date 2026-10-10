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


class RegulationRadarRunSummary(BaseModel):
    """法规雷达扫描批次摘要。"""

    id: uuid.UUID
    started_at: datetime
    finished_at: datetime | None = None
    status: str
    trigger: str
    dry_run: bool = False
    sites_total: int = 0
    sites_failed: int = 0
    found_count: int = 0
    new_count: int = 0
    revised_count: int = 0
    link_fixed_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    error_message: str | None = None
    is_acknowledged: bool = False

    class Config:
        from_attributes = True


class RegulationRadarRunDetail(RegulationRadarRunSummary):
    """法规雷达扫描批次详情（含全部明细）。"""

    items: list[dict[str, Any]] | None = None

    class Config:
        from_attributes = True
