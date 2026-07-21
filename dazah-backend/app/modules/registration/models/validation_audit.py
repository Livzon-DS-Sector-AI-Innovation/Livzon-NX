"""Validation Audit ORM models."""

from sqlalchemy import Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class ValidationAuditTask(BaseModel):
    """验证文件审核任务主表"""

    __tablename__ = "validation_audit_tasks"
    __table_args__ = (
        Index("ix_validation_audit_tasks_status", "status"),
        Index("ix_validation_audit_tasks_source_company", "source_company"),
        {"schema": "registration"},
    )

    task_name: Mapped[str] = mapped_column(
        String(300), nullable=False, comment="任务名称"
    )
    product_name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="品种名称"
    )
    method_name: Mapped[str] = mapped_column(
        String(300), nullable=False, comment="方法名称"
    )
    source_company: Mapped[str] = mapped_column(
        String(300), nullable=False, comment="来源公司"
    )
    audit_mode: Mapped[str] = mapped_column(
        String(30), nullable=False, comment="审核模式: protocol/report/protocol_report"
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="draft",
        comment="状态: draft/uploaded/parsing/auditing/completed/failed"
    )
    conclusion: Mapped[str | None] = mapped_column(
        String(30), nullable=True, comment="审核结论: pass/conditional_pass/fail"
    )
    risk_level: Mapped[str | None] = mapped_column(
        String(30), nullable=True, comment="风险等级: high/medium/low"
    )
    serious_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", comment="严重问题数"
    )
    general_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", comment="一般问题数"
    )
    suggestion_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", comment="建议优化数"
    )
    compliant_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", comment="合规项数"
    )
    non_compliant_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", comment="不合规项数"
    )
    report_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="审核报告文件路径"
    )


class ValidationAuditFile(BaseModel):
    """验证文件审核-上传文件表"""

    __tablename__ = "validation_audit_files"
    __table_args__ = (
        Index("ix_validation_audit_files_task_id", "task_id"),
        {"schema": "registration"},
    )

    task_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), nullable=False, comment="任务ID（逻辑关联）"
    )
    file_type: Mapped[str] = mapped_column(
        String(30), nullable=False, comment="文件类型: protocol/report/attachment"
    )
    original_filename: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="原始文件名"
    )
    file_path: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="文件存储路径"
    )
    file_size: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", comment="文件大小(字节)"
    )
    parse_status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="pending",
        comment="解析状态: pending/parsing/completed/failed"
    )
    parsed_text: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="解析后的文本内容"
    )


class ValidationAuditIssue(BaseModel):
    """验证文件审核-问题表"""

    __tablename__ = "validation_audit_issues"
    __table_args__ = (
        Index("ix_validation_audit_issues_task_id", "task_id"),
        Index("ix_validation_audit_issues_file_id", "file_id"),
        {"schema": "registration"},
    )

    task_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), nullable=False, comment="任务ID（逻辑关联）"
    )
    file_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="文件ID（逻辑关联）"
    )
    issue_no: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="问题编号，如 P001"
    )
    dimension: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="所属维度"
    )
    check_item: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="检查项"
    )
    description: Mapped[str] = mapped_column(
        Text, nullable=False, comment="问题描述"
    )
    suggestion: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="修改建议"
    )
    issue_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="问题类型: serious/general/suggestion"
    )
    page_no: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="所在页码"
    )
    evidence_text: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="证据原文"
    )


class ValidationAuditReport(BaseModel):
    """验证文件审核-报告表"""

    __tablename__ = "validation_audit_reports"
    __table_args__ = (
        Index("ix_validation_audit_reports_task_id", "task_id"),
        {"schema": "registration"},
    )

    task_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), nullable=False, comment="任务ID（逻辑关联）"
    )
    report_title: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="报告标题"
    )
    report_markdown: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="报告 Markdown 内容"
    )
    report_file_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="报告文件路径"
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1", comment="报告版本"
    )


class ValidationAuditKnowledgeBase(BaseModel):
    """验证文件审核-知识库表"""

    __tablename__ = "validation_audit_knowledge_base"
    __table_args__ = (
        Index("ix_validation_audit_kb_source_task_id", "source_task_id"),
        {"schema": "registration"},
    )

    dimension: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="所属维度"
    )
    check_item: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="检查项"
    )
    issue_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="问题类型: serious/general/suggestion"
    )
    description_template: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="问题描述模板"
    )
    suggestion_template: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="修改建议模板"
    )
    frequency: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1", comment="出现频次"
    )
    related_product: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="涉及品种"
    )
    source_task_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="来源任务ID（逻辑关联）"
    )
