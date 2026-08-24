"""Authorization letter ORM models."""

import uuid

from sqlalchemy import Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from app.shared.base_model import BaseModel


class AuthorizationLetter(BaseModel):
    """授权书生成记录表"""

    __tablename__ = "authorization_letters"
    __table_args__ = (
        Index("ix_authorization_letters_product_name", "product_name"),
        Index("ix_authorization_letters_registration_number", "registration_number"),
        {"schema": "registration"},
    )

    api_company: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default="珠海保税区丽珠合成制药有限公司",
        comment="原料药企业名称",
    )
    product_name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="产品名称（对照表标准名）"
    )
    registration_number: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="产品登记号"
    )
    preparation_unit: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="制剂单位名称（药品上市许可持有人/申请人）"
    )
    preparation_name: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="制剂名称"
    )
    administration_route: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="给药途径"
    )
    template_file_key: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="模板文件 key"
    )
    template_file_name: Mapped[str] = mapped_column(
        String(256), nullable=True, comment="模板文件名"
    )
    output_file_key: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="生成文件 key"
    )
    output_file_name: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="生成文件名"
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


class SupplementaryReply(BaseModel):
    """发补回复生成记录表。

    This legacy model remains part of the metadata so existing supplementary
    reply records and their service/repository compatibility entry points are
    not treated as removed during migration.
    """

    __tablename__ = "supplementary_replies"
    __table_args__ = (
        Index("ix_supplementary_replies_drug_name", "drug_name"),
        Index("ix_supplementary_replies_registration_number", "registration_number"),
        {"schema": "registration"},
    )

    drug_name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="药品名称"
    )
    registration_number: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="登记号"
    )
    acceptance_number: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="受理号"
    )
    company_name: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="申请人/公司名称"
    )
    notice_file_key: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="CDE通知函文件 key"
    )
    notice_file_name: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="CDE通知函文件名"
    )
    template_file_key: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="公司模板文件 key"
    )
    template_file_name: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="公司模板文件名"
    )
    output_file_key: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="生成文件 key"
    )
    output_file_name: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="生成文件名"
    )
    question_count: Mapped[int] = mapped_column(
        nullable=False, server_default="0", comment="提取的问题数量"
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


class AuthorizationLedgerEntry(BaseModel):
    """授权书台账记录表"""

    __tablename__ = "authorization_ledger_entries"
    __table_args__ = (
        Index("ix_authorization_ledger_entries_product_name", "product_name"),
        Index("ix_authorization_ledger_entries_market_name", "market_name"),
        Index("ix_authorization_ledger_entries_status", "status"),
        {"schema": "registration"},
    )

    product_name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="产品名称"
    )
    market_name: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="市场/地区"
    )
    source_sequence: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="来源表格序号"
    )
    authorization_file_name: Mapped[str] = mapped_column(
        String(512), nullable=False, comment="授权文件名称"
    )
    quality_standard: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="质量标准"
    )
    company_name: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="单位名称"
    )
    country: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="国家"
    )
    customer_code: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="客户编号"
    )
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True, comment="用途")
    authorization_date: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="授权日期"
    )
    handler: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="经手人"
    )
    status: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="授权状态"
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


class AuthorizationLedgerMain(BaseModel):
    """市场授权主记录表。"""

    __tablename__ = "authorization_ledger_main_records"
    __table_args__ = (
        Index("ix_authorization_ledger_main_records_product_name", "product_name"),
        Index("ix_authorization_ledger_main_records_market_name", "market_name"),
        Index("ix_authorization_ledger_main_records_status", "status"),
        {"schema": "registration"},
    )

    product_name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="产品名称"
    )
    market_name: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="市场/地区"
    )
    source_sequence: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="来源表格序号"
    )
    authorization_file_name: Mapped[str] = mapped_column(
        String(512), nullable=False, comment="授权文件名称"
    )
    quality_standard: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="质量标准"
    )
    company_name: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="单位名称"
    )
    country: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="国家"
    )
    customer_code: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="客户编号"
    )
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True, comment="用途")
    status: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="授权状态"
    )

    updates: Mapped[list["AuthorizationLedgerUpdate"]] = relationship(
        "AuthorizationLedgerUpdate",
        back_populates="main",
        primaryjoin=lambda: (
            AuthorizationLedgerMain.id
            == foreign(AuthorizationLedgerUpdate.ledger_main_id)
        ),
        cascade="all, delete-orphan",
        order_by=lambda: (
            AuthorizationLedgerUpdate.sort_order.asc(),
            AuthorizationLedgerUpdate.created_at.asc(),
        ),
    )


class AuthorizationLedgerUpdate(BaseModel):
    """市场授权更新子行表。"""

    __tablename__ = "authorization_ledger_updates"
    __table_args__ = (
        UniqueConstraint(
            "ledger_main_id",
            "sort_order",
            name="uq_registration_authorization_ledger_updates_main_sort",
        ),
        Index("ix_authorization_ledger_updates_ledger_main_id", "ledger_main_id"),
        Index(
            "ix_authorization_ledger_updates_authorization_date", "authorization_date"
        ),
        {"schema": "registration"},
    )

    ledger_main_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        comment="主记录ID",
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
        comment="更新序号",
    )
    authorization_date: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="授权日期"
    )
    handler: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="经手人"
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="更新备注")

    main: Mapped["AuthorizationLedgerMain"] = relationship(
        "AuthorizationLedgerMain",
        back_populates="updates",
        primaryjoin=lambda: (
            foreign(AuthorizationLedgerUpdate.ledger_main_id)
            == AuthorizationLedgerMain.id
        ),
    )


class AuthorizationFdaEntry(BaseModel):
    """FDA 授权记录表"""

    __tablename__ = "authorization_fda_entries"
    __table_args__ = (
        Index("ix_authorization_fda_entries_product_name", "product_name"),
        Index("ix_authorization_fda_entries_company_name", "company_name"),
        {"schema": "registration"},
    )

    product_name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="产品名称"
    )
    source_sequence: Mapped[int | None] = mapped_column(
        nullable=True, comment="来源表格序号"
    )
    company_name: Mapped[str] = mapped_column(
        String(512), nullable=False, comment="客户/公司名称"
    )
    address: Mapped[str | None] = mapped_column(Text, nullable=True, comment="地址")
    reference_number: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="引用编号"
    )
    loa_date: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="LOA日期"
    )
    submission_date: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="递交日期"
    )
    referenced_sections: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="引用章节"
    )
