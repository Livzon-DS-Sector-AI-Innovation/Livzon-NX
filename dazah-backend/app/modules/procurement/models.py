"""Procurement ORM models live here."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.identity.models import User  # noqa: F401
from app.shared.base_model import BaseModel


class InvoiceRecognitionRecord(BaseModel):
    """采购发票识别结果记录表。"""

    __tablename__ = "invoice_recognition_records"
    __table_args__ = (
        Index(
            "ix_procurement_invoice_recognition_invoice_number",
            "invoice_number",
        ),
        Index(
            "ix_procurement_invoice_recognition_duplicate_key",
            "duplicate_key",
        ),
        Index(
            "ix_procurement_invoice_recognition_source_file_sha256",
            "source_file_sha256",
        ),
        Index(
            "ix_procurement_invoice_recognition_seller_name",
            "seller_name",
        ),
        Index(
            "ix_procurement_invoice_recognition_created_at",
            "created_at",
        ),
        {"schema": "procurement"},
    )

    file_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="上传文件名",
    )
    include_details: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="是否开启明细识别",
    )
    invoice_number: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="发票号码",
    )
    duplicate_key: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="发票业务去重指纹",
    )
    source_file_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="上传文件 SHA256",
    )
    invoice_date: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="开票日期",
    )
    seller_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="销售方名称",
    )
    total_tax_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
        comment="税额合计",
    )
    total_amount_with_tax_small: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
        comment="价税合计（小写）",
    )
    line_items: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="识别到的发票明细",
    )
    raw_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
        comment="PDF 文本层原文",
    )


class Supplier(BaseModel):
    """采购供应商清单。"""

    __tablename__ = "suppliers"
    __table_args__ = (
        Index("ix_procurement_supplier_code", "supplier_code"),
        Index("ix_procurement_supplier_name", "supplier_name"),
        Index("ix_procurement_supplier_material_code", "material_code"),
        Index("ix_procurement_supplier_material_name", "material_name"),
        Index("ix_procurement_supplier_category", "purchase_category"),
        Index("ix_procurement_supplier_updated_date", "last_updated_date"),
        {"schema": "procurement"},
    )

    supplier_code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="",
        server_default="",
        comment="供应商代码",
    )
    supplier_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default="",
        comment="供应商名称",
    )
    material_code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="",
        server_default="",
        comment="物料编码",
    )
    material_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default="",
        comment="物料名称",
    )
    manufacturer_code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="",
        server_default="",
        comment="生产厂家编码",
    )
    manufacturer_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default="",
        comment="生产厂家名称",
    )
    purchase_category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="",
        server_default="",
        comment="采购品类名称",
    )
    last_updated_by: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="",
        server_default="",
        comment="最后更新人",
    )
    last_updated_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="最后更新日期",
    )
    import_file_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default="",
        comment="导入文件名",
    )
    import_sheet_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="",
        server_default="",
        comment="导入工作表",
    )
    import_row_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="导入文件行号",
    )
    import_columns: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="导入文件字段顺序",
    )
    raw_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="导入原始行数据",
    )


class ContractRecord(BaseModel):
    """采购合同生成记录。"""

    __tablename__ = "contract_records"
    __table_args__ = (
        Index("ix_procurement_contract_record_title", "title"),
        Index("ix_procurement_contract_record_category", "category"),
        Index("ix_procurement_contract_record_contract_number", "contract_number"),
        Index("ix_procurement_contract_record_seller_name", "seller_name"),
        Index("ix_procurement_contract_record_created_at", "created_at"),
        {"schema": "procurement"},
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="合同标题",
    )
    category: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="合同分类",
    )
    contract_number: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="合同编号",
    )
    contract_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="签订日期",
    )
    seller_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default="",
        comment="卖方名称",
    )
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="合同文件名",
    )
    file_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="合同文件路径或对象存储 key",
    )
    content_type: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="文件 MIME 类型",
    )
    file_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="文件大小（字节）",
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="合同生成请求快照",
    )


class PurchaseRequest(BaseModel):
    """采购申请单主表。"""

    __tablename__ = "purchase_requests"
    __table_args__ = (
        Index("ix_procurement_purchase_request_category", "category"),
        Index("ix_procurement_purchase_request_status", "status"),
        Index("ix_procurement_purchase_request_request_date", "request_date"),
        Index("ix_procurement_purchase_request_department", "request_department"),
        Index("ix_procurement_purchase_request_created_at", "created_at"),
        {"schema": "procurement"},
    )

    category: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="采购分类",
    )
    request_department: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="申购部门",
    )
    request_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="申请日期",
    )
    attachment_note: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
        comment="附件说明",
    )
    status: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="draft",
        server_default="draft",
        comment="流程状态",
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
        comment="申请总额",
    )
    rejected_step: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="驳回步骤",
    )
    status_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="状态更新时间",
    )


class PurchaseRequestItem(BaseModel):
    """采购申请单明细。"""

    __tablename__ = "purchase_request_items"
    __table_args__ = (
        Index(
            "ix_procurement_purchase_request_item_request_id",
            "purchase_request_id",
        ),
        {"schema": "procurement"},
    )

    purchase_request_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        comment="采购申请 ID",
    )
    sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="序号",
    )
    item_category: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="",
        server_default="",
        comment="明细实际采购类型",
    )
    product_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="商品名称",
    )
    specification: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default="",
        comment="规格",
    )
    material_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="",
        server_default="",
        comment="物料编码",
    )
    material_description: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default="",
        comment="物料说明",
    )
    rule_model: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default="",
        comment="规格型号",
    )
    purpose: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default="",
        comment="用途",
    )
    material: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default="",
        comment="材质",
    )
    brand: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default="",
        comment="品牌",
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        comment="数量",
    )
    unit: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="",
        server_default="",
        comment="单位",
    )
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        comment="单价",
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        comment="总额",
    )
    remarks: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
        comment="备注",
    )


class MaterialSourceConfig(BaseModel):
    """采购物料编码联想使用的飞书多维表格配置。"""

    __tablename__ = "material_source_configs"
    __table_args__ = (
        UniqueConstraint(
            "config_key",
            name="uq_procurement_material_source_config_key",
        ),
        Index(
            "ix_procurement_material_source_config_active",
            "config_key",
            "is_deleted",
        ),
        {"schema": "procurement"},
    )

    config_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="material-master",
        server_default="material-master",
        comment="配置业务键",
    )
    source_url: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        comment="飞书多维表格原始链接",
    )
    app_token: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="解析后的多维表格 app_token",
    )
    table_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="解析后的多维表格 table_id",
    )
    view_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="解析后的多维表格 view_id",
    )
    material_code_field: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="物料编码实际字段名",
    )
    material_code_field_type: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="飞书物料编码字段类型",
    )
    material_description_field: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="物料说明实际字段名",
    )
    rule_model_field: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="规格型号实际字段名",
    )
    last_test_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="not_tested",
        server_default="not_tested",
        comment="最近测试状态",
    )
    last_test_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="最近测试错误（不含第三方原始响应）",
    )
    last_tested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="最近测试时间",
    )


class PurchaseRequestApproval(BaseModel):
    """采购申请审批记录。"""

    __tablename__ = "purchase_request_approvals"
    __table_args__ = (
        Index(
            "ix_procurement_purchase_request_approval_request_id",
            "purchase_request_id",
        ),
        Index("ix_procurement_purchase_request_approval_role", "approval_role"),
        Index(
            "ix_procurement_purchase_request_approval_role_result_time",
            "approval_role",
            "result",
            "approval_time",
        ),
        Index("ix_procurement_purchase_request_approval_time", "approval_time"),
        {"schema": "procurement"},
    )

    purchase_request_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        comment="采购申请 ID",
    )
    approval_role: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="审批角色",
    )
    result: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="审批结果",
    )
    opinion: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
        comment="审批意见",
    )
    approver_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="",
        server_default="",
        comment="审批人姓名",
    )
    approval_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="审批时间",
    )
