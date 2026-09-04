"""验证方案与报告 AI 审核 schema。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ReviewMode = Literal["upload", "entry"]
ReviewStatus = Literal["draft", "processing", "completed", "failed"]
DocKind = Literal["plan", "report"]
FindingCategory = Literal[
    "reference_missing",
    "version_mismatch",
    "plan_report_mismatch",
    "content_consistency",
    "format_issue",
    "numeric_check",
]
FindingSeverity = Literal["high", "medium", "low"]


class ValidationReviewCreateRequest(BaseModel):
    """新建一次 AI 审核会话。entry 模式需传 entry_id（文件管理目录条目）。"""

    review_mode: ReviewMode = "upload"
    entry_id: uuid.UUID | None = None
    title: str | None = Field(default=None, max_length=255)


class ValidationReviewFileUploadRequest(BaseModel):
    """上传 VP/VR 文档时可选标注文档类型；不传则由后端按文件名自动判断。"""

    doc_kind: DocKind | None = None


class ValidationReviewFindingOut(BaseModel):
    category: FindingCategory
    severity: FindingSeverity = "medium"
    location: str = ""
    quote: str = ""
    quote_verified: bool = False
    basis_source: str | None = None
    basis_match_type: str | None = None
    detail: str = ""


class ValidationReviewFileOut(BaseModel):
    id: uuid.UUID
    doc_kind: str
    source: str
    file_name: str
    file_type: str
    file_size: int
    parse_status: str
    parse_error: str | None = None
    sort_order: int


class ValidationReviewStatsOut(BaseModel):
    total_findings: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    references_checked: int = 0
    references_matched: int = 0
    plan_report_checked: bool = False


class ValidationReviewOut(BaseModel):
    id: uuid.UUID
    title: str
    review_mode: str
    status: str
    error_message: str | None = None
    model_name: str | None = None
    input_snapshot: dict[str, Any] | None = None
    summary: str | None = None
    stats: ValidationReviewStatsOut | None = None
    findings: list[ValidationReviewFindingOut] = []
    basis_used: list[dict[str, Any]] = []
    job_id: str | None = None
    last_generated_at: datetime | None = None
    files: list[ValidationReviewFileOut] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ValidationReviewListItem(BaseModel):
    id: uuid.UUID
    title: str
    review_mode: str
    status: str
    model_name: str | None = None
    file_count: int = 0
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ValidationReviewRunOut(BaseModel):
    job_id: str
    review_id: uuid.UUID


class ValidationReviewFileUploadedOut(BaseModel):
    id: uuid.UUID
    file_name: str
    doc_kind: str
    parse_status: str


class ValidationReviewJobStatusResponse(BaseModel):
    job_id: str
    state: str
    progress: str = ""
    status: str | None = None
    error_message: str | None = None
    review_id: uuid.UUID | None = None
