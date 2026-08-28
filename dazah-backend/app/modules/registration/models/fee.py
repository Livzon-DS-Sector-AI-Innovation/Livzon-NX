"""Registration fee ORM models."""

from decimal import Decimal

from sqlalchemy import Boolean, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class RegistrationFee(BaseModel):
    """注册费用台账记录表。"""

    __tablename__ = "fee_entries"
    __table_args__ = (
        Index("ix_registration_fee_entries_fee_type", "fee_type"),
        Index("ix_registration_fee_entries_payment_status", "payment_status"),
        Index("ix_registration_fee_entries_project_name", "project_name"),
        Index("ix_registration_fee_entries_product_name", "product_name"),
        {"schema": "registration"},
    )

    fee_type: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="费用类型"
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, comment="金额"
    )
    currency: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="CNY", comment="币种"
    )
    payment_status: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="支付状态"
    )
    payment_date: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="支付日期"
    )
    project_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="关联项目名称"
    )
    product_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="关联产品名称"
    )
    country: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="国家/地区"
    )
    agency_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="代理机构名称"
    )
    expense_content: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="开支内容"
    )
    handler: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="经办人"
    )
    contract_received: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", comment="是否收到纸版合同"
    )
    invoice_settled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", comment="是否收到发票及冲账"
    )
    contact: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="联系人"
    )
    phone: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="联系电话"
    )
    address: Mapped[str | None] = mapped_column(Text, nullable=True, comment="地址")
    invoice_number: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="发票号"
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


class InspectionContact(BaseModel):
    """外检机构联系信息表。"""

    __tablename__ = "inspection_contacts"
    __table_args__ = (
        Index("ix_registration_inspection_contacts_agency_name", "agency_name"),
        Index("ix_registration_inspection_contacts_test_item", "test_item"),
        {"schema": "registration"},
    )

    test_item: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="检测项目"
    )
    agency_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="外检机构"
    )
    contact_name: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="联系人"
    )
    contact_phone: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="联系电话"
    )
    contact_email: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="邮箱"
    )
    address: Mapped[str | None] = mapped_column(Text, nullable=True, comment="地址")
