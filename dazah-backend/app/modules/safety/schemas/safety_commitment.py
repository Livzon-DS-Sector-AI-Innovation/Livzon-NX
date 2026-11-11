"""安全承诺（应急〔2018〕74号 承诺公告制度）Schema。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

CommitmentCardTypeLiteral = Literal["commitment", "major_hazard"]

# AI 研判允许的风险档位（与 service 校验保持一致）
RISK_LEVELS = ("低", "中", "较高", "高")


class SafetyCommitmentReportItem(BaseModel):
    """安全承诺日报（企业状态 + AI 研判 + 承诺公告正文）。"""

    id: UUID
    report_date: date
    enterprise_status: dict[str, Any] = Field(default_factory=dict)
    commitment_text: str | None = None
    risk_assessment: dict[str, Any] | None = None
    status: str = "draft"
    publisher_name: str | None = None
    published_at: datetime | None = None
    fill_source: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SafetyCommitmentReportResponse(BaseModel):
    report: SafetyCommitmentReportItem
    created_today: bool = False


class SafetyCommitmentUpdateRequest(BaseModel):
    """编辑企业状态 / 承诺公告正文。"""

    enterprise_status: dict[str, Any] | None = None
    commitment_text: str | None = Field(default=None, max_length=20000)


class SafetyCommitmentPublishRequest(BaseModel):
    """发布当日承诺公告。"""

    publisher_name: str = Field(min_length=1, max_length=100)


class RiskAssessmentResponse(BaseModel):
    """AI 风险研判结果。"""

    success: bool
    message: str = ""
    report: SafetyCommitmentReportItem | None = None


class SafetyCommitmentCardItem(BaseModel):
    """安全承诺页滚动信息卡。"""

    id: UUID
    card_type: CommitmentCardTypeLiteral
    title: str = ""
    content: str = ""
    sort_order: int = 0
    updated_at: datetime | None = None


class SafetyCommitmentCardListResponse(BaseModel):
    cards: list[SafetyCommitmentCardItem] = Field(default_factory=list)


class SafetyCommitmentCardCreateRequest(BaseModel):
    card_type: CommitmentCardTypeLiteral
    title: str = Field(default="", max_length=100)
    content: str = Field(default="", max_length=20000)
    sort_order: int = 0


class SafetyCommitmentCardUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=100)
    content: str | None = Field(default=None, max_length=20000)
    sort_order: int | None = None
