"""Validation Audit schemas."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── 枚举 ──────────────────────────────────────────────────


class AuditMode(str, Enum):
    PROTOCOL = "protocol"
    REPORT = "report"
    PROTOCOL_REPORT = "protocol_report"


class TaskStatus(str, Enum):
    DRAFT = "draft"
    UPLOADED = "uploaded"
    PARSING = "parsing"
    AUDITING = "auditing"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskConclusion(str, Enum):
    PASS = "pass"
    CONDITIONAL_PASS = "conditional_pass"
    FAIL = "fail"


class FileType(str, Enum):
    PROTOCOL = "protocol"
    REPORT = "report"
    ATTACHMENT = "attachment"


class ParseStatus(str, Enum):
    PENDING = "pending"
    PARSING = "parsing"
    COMPLETED = "completed"
    FAILED = "failed"


class IssueType(str, Enum):
    SERIOUS = "serious"
    GENERAL = "general"
    SUGGESTION = "suggestion"


# ── Task ──────────────────────────────────────────────────


class ValidationAuditTaskCreate(BaseModel):
    """创建审核任务"""
    task_name: str = Field(..., max_length=300, description="任务名称")
    product_name: str = Field(..., max_length=200, description="品种名称")
    method_name: str = Field(..., max_length=300, description="方法名称")
    source_company: str = Field(..., max_length=300, description="来源公司")
    audit_mode: AuditMode = Field(..., description="审核模式")


class ValidationAuditTaskUpdate(BaseModel):
    """更新审核任务"""
    task_name: str | None = Field(None, max_length=300, description="任务名称")
    product_name: str | None = Field(None, max_length=200, description="品种名称")
    method_name: str | None = Field(None, max_length=300, description="方法名称")
    source_company: str | None = Field(None, max_length=300, description="来源公司")
    audit_mode: AuditMode | None = Field(None, description="审核模式")


class ValidationAuditTaskResponse(BaseModel):
    """审核任务详情"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_name: str
    product_name: str
    method_name: str
    source_company: str
    audit_mode: str
    status: str
    conclusion: str | None = None
    risk_level: str | None = None
    serious_count: int = 0
    general_count: int = 0
    suggestion_count: int = 0
    compliant_count: int = 0
    non_compliant_count: int = 0
    report_path: str | None = None
    created_at: datetime
    updated_at: datetime


class ValidationAuditTaskListItem(BaseModel):
    """审核任务列表项"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_name: str
    product_name: str
    source_company: str
    audit_mode: str
    status: str
    conclusion: str | None = None
    serious_count: int = 0
    general_count: int = 0
    suggestion_count: int = 0
    created_at: datetime


# ── File ──────────────────────────────────────────────────


class ValidationAuditFileResponse(BaseModel):
    """审核文件详情"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    file_type: str
    original_filename: str
    file_path: str
    file_size: int
    parse_status: str
    created_at: datetime


class ValidationAuditFileListItem(BaseModel):
    """审核文件列表项"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    file_type: str
    original_filename: str
    file_size: int
    parse_status: str
    created_at: datetime


# ── Issue ─────────────────────────────────────────────────


class ValidationAuditIssueResponse(BaseModel):
    """审核问题详情"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    file_id: UUID | None = None
    issue_no: str
    dimension: str
    check_item: str
    description: str
    suggestion: str | None = None
    issue_type: str
    page_no: int | None = None
    evidence_text: str | None = None
    created_at: datetime


# ── Report ────────────────────────────────────────────────


class ValidationAuditReportResponse(BaseModel):
    """审核报告详情"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    report_title: str
    report_markdown: str | None = None
    report_file_path: str | None = None
    version: int
    created_at: datetime


# ── Knowledge Base ────────────────────────────────────────


class ValidationAuditKnowledgeBaseResponse(BaseModel):
    """知识库条目"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dimension: str
    check_item: str
    issue_type: str
    description_template: str | None = None
    suggestion_template: str | None = None
    frequency: int
    related_product: str | None = None
    source_task_id: UUID | None = None
    created_at: datetime


# ── Audit Result (AI 返回结构) ────────────────────────────


class AuditIssueItem(BaseModel):
    """AI 审核返回的单个问题"""
    issue_no: str = Field(..., description="问题编号")
    dimension: str = Field(..., description="所属维度")
    check_item: str = Field(..., description="检查项")
    description: str = Field(..., description="问题描述")
    suggestion: str | None = Field(None, description="修改建议")
    issue_type: IssueType = Field(..., description="问题类型")
    page_no: int | None = Field(None, description="所在页码")
    evidence_text: str | None = Field(None, description="证据原文")


class AuditResult(BaseModel):
    """AI 审核返回的完整结果"""
    conclusion: TaskConclusion = Field(..., description="审核结论")
    risk_level: str = Field(..., description="风险等级: high/medium/low")
    compliant_count: int = Field(0, description="合规项数")
    non_compliant_count: int = Field(0, description="不合规项数")
    issues: list[AuditIssueItem] = Field(default_factory=list, description="问题列表")
    summary: str = Field("", description="审核总结")
