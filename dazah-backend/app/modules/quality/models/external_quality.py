"""Platform-owned supplier, complaint, recall and product-quality ORM models."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, synonym

from app.shared.base_model import BaseModel


class ExternalQualityBaseModel(BaseModel):
    """Quality-owned records with UUID audit columns and no database FKs."""

    __abstract__ = True

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )


class Supplier(ExternalQualityBaseModel):
    """Approved or pending external supplier master record."""

    __tablename__ = "suppliers"
    __table_args__ = (
        UniqueConstraint("supplier_code", name="uq_quality_suppliers_supplier_code"),
        Index("ix_quality_suppliers_active_status", "is_deleted", "status"),
        Index("ix_quality_suppliers_active_category", "is_deleted", "category"),
        Index("ix_quality_suppliers_name", "name"),
        {"schema": "quality"},
    )

    supplier_code: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="供应商编号"
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="供应商名称")
    category: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="供应商类别"
    )
    contact_person: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="联系人"
    )
    contact_phone: Mapped[str | None] = mapped_column(
        String(30), nullable=True, comment="联系电话"
    )
    address: Mapped[str | None] = mapped_column(
        String(300), nullable=True, comment="地址"
    )
    qualification_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
        server_default="pending",
        comment="资质状态",
    )
    audit_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="最近审计日期"
    )
    audit_result: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="审计结论"
    )
    next_audit_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="下次审计日期"
    )
    scope_of_supply: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="供应范围"
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
    # The current API contract calls this field ``remarks`` while the legacy
    # table stores ``remark``.  A synonym keeps both contracts/data layouts.
    remarks = synonym("remark")
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="active",
        server_default="active",
        comment="供应商状态",
    )


class SupplierQualification(ExternalQualityBaseModel):
    """Supplier qualification document tracked in the platform database."""

    __tablename__ = "supplier_qualifications"
    __table_args__ = (
        UniqueConstraint(
            "qualification_code", name="uq_quality_supplier_qualifications_code"
        ),
        Index(
            "ix_quality_supplier_qualifications_active_supplier_expiry",
            "is_deleted",
            "supplier_id",
            "expiry_date",
        ),
        Index(
            "ix_quality_supplier_qualifications_active_status", "is_deleted", "status"
        ),
        {"schema": "quality"},
    )

    supplier_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, comment="供应商ID（应用层关联）"
    )
    qualification_code: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="资质编号"
    )
    qualification_name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="资质名称"
    )
    document_no: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="文件编号"
    )
    obtained_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="取得日期"
    )
    expiry_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="到期日期"
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
        server_default="pending",
        comment="资质状态",
    )
    responsible_person: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="责任人"
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


class ComplaintRecord(ExternalQualityBaseModel):
    """Customer or internal complaint with a controlled quality lifecycle."""

    __tablename__ = "complaint_records"
    __table_args__ = (
        UniqueConstraint("complaint_code", name="uq_quality_complaint_records_code"),
        Index(
            "ix_quality_complaint_records_active_status_date",
            "is_deleted",
            "status",
            "complaint_date",
        ),
        Index(
            "ix_quality_complaint_records_product_batch", "product_name", "batch_number"
        ),
        {"schema": "quality"},
    )

    complaint_code: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="投诉编号"
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, comment="投诉标题")
    complaint_source: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="投诉来源"
    )
    customer_name: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="客户名称"
    )
    product_name: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="涉及产品"
    )
    batch_number: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="批号"
    )
    complaint_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="投诉日期"
    )
    complaint_category: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="投诉类别"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="投诉描述"
    )
    handler: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="处理人"
    )
    investigation_result: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="调查结论"
    )
    response_content: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="回复内容"
    )
    response_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="回复日期"
    )
    capa_code: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="关联CAPA编号"
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
        server_default="pending",
        comment="投诉状态",
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="关闭时间"
    )


class ReturnRecallRecord(ExternalQualityBaseModel):
    """Return or recall case with assessment and disposition controls."""

    __tablename__ = "return_recall_records"
    __table_args__ = (
        UniqueConstraint("record_code", name="uq_quality_return_recall_records_code"),
        Index(
            "ix_quality_return_recall_records_active_type_status",
            "is_deleted",
            "record_type",
            "status",
        ),
        Index(
            "ix_quality_return_recall_records_product_batch",
            "product_name",
            "batch_number",
        ),
        {"schema": "quality"},
    )

    record_code: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="记录编号"
    )
    record_type: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="退货或召回"
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, comment="标题")
    product_name: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="产品名称"
    )
    batch_number: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="批号"
    )
    quantity: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 4), nullable=True, comment="数量"
    )
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="单位")
    customer_name: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="客户或退货方"
    )
    reason: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="退货或召回原因"
    )
    occurrence_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="发生日期"
    )
    handler: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="处理人"
    )
    assessment_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="评估日期"
    )
    disposition: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="处置方式"
    )
    completion_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="完成日期"
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
        server_default="pending",
        comment="处理状态",
    )


class ProductQualityRecord(ExternalQualityBaseModel):
    """Annual product review or customer-specific quality standard document."""

    __tablename__ = "product_quality_records"
    __table_args__ = (
        UniqueConstraint("record_code", name="uq_quality_product_quality_records_code"),
        Index(
            "ix_quality_product_quality_records_active_type_status",
            "is_deleted",
            "record_type",
            "status",
        ),
        Index("ix_quality_product_quality_records_product", "product_name"),
        {"schema": "quality"},
    )

    record_code: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="质量记录编号"
    )
    record_type: Mapped[str] = mapped_column(
        String(30), nullable=False, comment="年度回顾或客户标准"
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, comment="标题")
    product_name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="产品名称"
    )
    customer_name: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="客户名称"
    )
    batch_number: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="批号"
    )
    document_no: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="标准文件编号"
    )
    document_version: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="标准文件版本"
    )
    review_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="评审类型"
    )
    review_period_start: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="回顾周期开始"
    )
    review_period_end: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="回顾周期结束"
    )
    batch_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="批次数量"
    )
    qualified_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="合格批次"
    )
    unqualified_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="不合格批次"
    )
    oos_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="OOS次数"
    )
    deviation_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="偏差次数"
    )
    change_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="变更次数"
    )
    quality_trend: Mapped[str | None] = mapped_column(
        String(30), nullable=True, comment="质量趋势"
    )
    quality_standard: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="质量标准"
    )
    special_requirements: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="特殊要求"
    )
    packaging_requirements: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="包装要求"
    )
    label_requirements: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="标签要求"
    )
    pallet_requirements: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="打托要求"
    )
    target_market: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="目标市场"
    )
    registration_status: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="注册情况"
    )
    conclusion: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="评审结论"
    )
    suggestions: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="改进建议"
    )
    reviewer: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="评审人"
    )
    review_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="评审日期"
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="draft",
        server_default="draft",
        comment="记录状态",
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="批准时间"
    )


class ProductQualityStandardItem(ExternalQualityBaseModel):
    """A controlled item under a customer-specific product quality standard."""

    __tablename__ = "product_quality_standard_items"
    __table_args__ = (
        UniqueConstraint(
            "product_quality_id",
            "display_order",
            name="uq_quality_product_quality_standard_items_order",
        ),
        Index(
            "ix_quality_product_quality_standard_items_active_record",
            "is_deleted",
            "product_quality_id",
        ),
        {"schema": "quality"},
    )

    product_quality_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, comment="产品质量记录ID（应用层关联）"
    )
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1", comment="显示顺序"
    )
    category: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="要求分类"
    )
    item_name: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="要求项目"
    )
    requirement: Mapped[str] = mapped_column(Text, nullable=False, comment="要求内容")
    is_critical: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="是否关键要求",
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
