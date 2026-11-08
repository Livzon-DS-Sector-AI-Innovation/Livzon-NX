"""人员特殊作业证件的请求 / 响应模型（含 AI 识别建议）。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CertificateBase(BaseModel):
    person_name: str = Field(min_length=1, max_length=100, description="持证人姓名")
    identity_user_id: UUID | None = Field(default=None, description="平台账号")
    department: str | None = Field(default=None, max_length=100)
    certificate_category: str = Field(
        min_length=1, max_length=64, description="证件类别（字典值）"
    )
    certificate_no: str | None = Field(default=None, max_length=100)
    issuing_authority: str | None = Field(default=None, max_length=200)
    issue_date: date | None = None
    expiry_date: date | None = None
    qualification_scope: str | None = Field(default=None, max_length=2000)
    remark: str | None = Field(default=None, max_length=2000)


class SpecialWorkCertificateCreate(CertificateBase):
    pass


class SpecialWorkCertificateUpdate(BaseModel):
    person_name: str | None = Field(default=None, min_length=1, max_length=100)
    identity_user_id: UUID | None = None
    department: str | None = Field(default=None, max_length=100)
    certificate_category: str | None = Field(default=None, max_length=64)
    certificate_no: str | None = Field(default=None, max_length=100)
    issuing_authority: str | None = Field(default=None, max_length=200)
    issue_date: date | None = None
    expiry_date: date | None = None
    qualification_scope: str | None = Field(default=None, max_length=2000)
    remark: str | None = Field(default=None, max_length=2000)


class CertificateFileItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    file_name: str
    content_type: str | None = None
    size_bytes: int


class SpecialWorkCertificateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    person_name: str
    identity_user_id: UUID | None = None
    department: str | None = None
    certificate_category: str
    certificate_category_label: str = Field(
        default="", description="证件类别中文名（service 填充）"
    )
    certificate_no: str | None = None
    issuing_authority: str | None = None
    issue_date: date | None = None
    expiry_date: date | None = None
    qualification_scope: str | None = None
    status: str
    remark: str | None = None
    files: list[CertificateFileItem] = Field(default_factory=list)
    days_to_expiry: int | None = Field(
        default=None, description="距到期天数（负数=已过期）"
    )
    created_at: datetime
    updated_at: datetime


class SpecialWorkCertificateListResponse(BaseModel):
    items: list[SpecialWorkCertificateResponse]
    total: int
    page: int
    page_size: int


class CertificateExpirySummaryResponse(BaseModel):
    """证件到期统计卡（列表页顶部）。"""

    total: int = 0
    valid: int = 0
    expiring_in_30d: int = 0
    expired: int = 0


class CertificateExtractionSuggestion(BaseModel):
    """证件附件 AI 识别建议值（人工确认后才写入，不直接落库）。"""

    person_name: str | None = Field(default=None, max_length=100)
    certificate_category: str | None = Field(default=None, max_length=64)
    certificate_category_label: str = Field(default="", max_length=64)
    certificate_no: str | None = Field(default=None, max_length=100)
    issuing_authority: str | None = Field(default=None, max_length=200)
    issue_date: date | None = None
    expiry_date: date | None = None
    qualification_scope: str | None = Field(default=None, max_length=2000)


class CertificateUploadResponse(BaseModel):
    """上传证件附件成功后的响应：附件 + AI 识别建议。"""

    file: CertificateFileItem
    files: list[CertificateFileItem] = Field(default_factory=list)
    ai_suggestion: CertificateExtractionSuggestion | None = None
    ai_error: str | None = Field(
        default=None, description="AI 识别未执行/失败的原因（附件已保存成功）"
    )


class CertificateStatusOptionsResponse(BaseModel):
    categories: list[dict[str, str]]


class CertificateImportSheetInfo(BaseModel):
    """导入预览：单个子表的解析结果。"""

    sheet: str
    certificate_category: str
    certificate_category_label: str = ""
    row_count: int = 0
    sample: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)


class CertificateImportPreview(BaseModel):
    sheets: list[CertificateImportSheetInfo] = Field(default_factory=list)
    skipped_sheets: list[dict[str, str]] = Field(default_factory=list)


class CertificateImportResult(BaseModel):
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    total_parsed: int = 0
    skipped_sheets: list[dict[str, str]] = Field(default_factory=list)
    row_errors: list[dict[str, Any]] = Field(default_factory=list)
    archive_path: str | None = None
