"""应急处置卡的请求 / 响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EmergencyCardStep(BaseModel):
    """一步现场处置（对应卡片「序号 / 步骤 / 处置 / 负责人」一行）。"""

    order: str = ""
    step: str = ""
    action: str = ""
    person: str = ""


class EmergencyCardExtra(BaseModel):
    """卡片上的其他段落（如「次生、衍生事故」）。"""

    label: str = ""
    content: str = ""


class EmergencyCardCreate(BaseModel):
    workshop: str = Field(min_length=1, max_length=60, description="车间/部门")
    position: str = Field(default="", max_length=60, description="岗位，可为空")
    title: str = Field(min_length=1, max_length=200, description="卡片标题")
    subject: str = Field(default="", max_length=120, description="处置主题")
    accident_type: str = Field(default="综合", max_length=40, description="事故类型")
    steps: list[EmergencyCardStep] = Field(default_factory=list)
    extras: list[EmergencyCardExtra] = Field(default_factory=list)
    phones: str = Field(default="", max_length=2000, description="应急电话")
    risks: str = Field(
        default="", max_length=8000, description="主要导致风险及导致的后果"
    )
    precautions: str = Field(default="", max_length=8000, description="应急注意事项")
    sort_order: int = Field(default=0, ge=0, le=999999)


class EmergencyCardUpdate(BaseModel):
    workshop: str | None = Field(default=None, min_length=1, max_length=60)
    position: str | None = Field(default=None, max_length=60)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    subject: str | None = Field(default=None, max_length=120)
    accident_type: str | None = Field(default=None, max_length=40)
    steps: list[EmergencyCardStep] | None = None
    extras: list[EmergencyCardExtra] | None = None
    phones: str | None = Field(default=None, max_length=2000)
    risks: str | None = Field(default=None, max_length=8000)
    precautions: str | None = Field(default=None, max_length=8000)
    sort_order: int | None = Field(default=None, ge=0, le=999999)


class EmergencyCardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workshop: str
    position: str
    title: str
    subject: str
    accident_type: str
    steps: list[EmergencyCardStep] = Field(default_factory=list)
    extras: list[EmergencyCardExtra] = Field(default_factory=list)
    phones: str
    risks: str
    precautions: str
    source_file: str
    sort_order: int
    created_at: datetime
    updated_at: datetime


class EmergencyCardListResponse(BaseModel):
    items: list[EmergencyCardResponse]
    total: int
    page: int
    page_size: int


class EmergencyCardWorkshopStat(BaseModel):
    workshop: str
    total: int
    positions: list[str] = Field(default_factory=list)


class EmergencyCardStatsResponse(BaseModel):
    total: int
    workshops: list[EmergencyCardWorkshopStat] = Field(default_factory=list)
    accident_types: list[str] = Field(default_factory=list)


class EmergencyCardCompletenessItem(BaseModel):
    """完整性检查项：status=ok 已覆盖 / missing 缺失 / unclear 不明确。"""

    item: str = Field(min_length=1, max_length=200)
    status: Literal["ok", "missing", "unclear"]
    note: str = Field(default="", max_length=500)


class EmergencyCardSuggestion(BaseModel):
    """完善建议：section 指明建议追加的位置。"""

    section: Literal["steps", "phones", "risks", "precautions"]
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=4000)


class EmergencyCardReviewResponse(BaseModel):
    """AI 审阅结果（辅助分析，采纳需人工确认）。"""

    summary: str = Field(default="", max_length=2000)
    completeness: list[EmergencyCardCompletenessItem] = Field(default_factory=list)
    suggestions: list[EmergencyCardSuggestion] = Field(default_factory=list)
