"""Registration fee schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

# 非空白字符串：去除首尾空白后长度至少为 1
_NonBlankShortStr = Annotated[
    str, StringConstraints(min_length=1, max_length=64, strip_whitespace=True)
]
_NonBlankNameStr = Annotated[
    str, StringConstraints(min_length=1, max_length=128, strip_whitespace=True)
]


class FeeEntryCreate(BaseModel):
    """新增费用记录。"""

    fee_type: _NonBlankShortStr = Field(..., description="费用类型")
    amount: Decimal = Field(..., ge=0, description="金额")
    currency: str = Field(default="CNY", max_length=16, description="币种")
    payment_status: str = Field(..., max_length=32, description="支付状态")
    payment_date: str | None = Field(None, max_length=64, description="支付日期")
    project_name: str | None = Field(None, max_length=255, description="关联项目名称")
    product_name: str | None = Field(None, max_length=255, description="关联产品名称")
    country: str | None = Field(None, max_length=128, description="国家/地区")
    agency_name: str | None = Field(None, max_length=255, description="代理机构名称")
    expense_content: str | None = Field(None, description="开支内容")
    handler: str | None = Field(None, max_length=128, description="经办人")
    contract_received: bool = Field(default=False, description="是否收到纸版合同")
    invoice_settled: bool = Field(default=False, description="是否收到发票及冲账")
    contact: str | None = Field(None, max_length=128, description="联系人")
    phone: str | None = Field(None, max_length=64, description="联系电话")
    address: str | None = Field(None, description="地址")
    invoice_number: str | None = Field(None, max_length=128, description="发票号")
    remarks: str | None = Field(None, description="备注")


class FeeEntryUpdate(BaseModel):
    """更新费用记录。"""

    fee_type: str | None = Field(None, max_length=64)
    amount: Decimal | None = Field(None, ge=0)
    currency: str | None = Field(None, max_length=16)
    payment_status: str | None = Field(None, max_length=32)
    payment_date: str | None = Field(None, max_length=64)
    project_name: str | None = Field(None, max_length=255)
    product_name: str | None = Field(None, max_length=255)
    country: str | None = Field(None, max_length=128)
    agency_name: str | None = Field(None, max_length=255)
    expense_content: str | None = None
    handler: str | None = Field(None, max_length=128)
    contract_received: bool | None = None
    invoice_settled: bool | None = None
    contact: str | None = Field(None, max_length=128)
    phone: str | None = Field(None, max_length=64)
    address: str | None = None
    invoice_number: str | None = Field(None, max_length=128)
    remarks: str | None = None


class FeeEntryResponse(BaseModel):
    """费用记录响应。"""

    id: UUID = Field(..., description="记录ID")
    fee_type: str = Field(..., description="费用类型")
    amount: Decimal = Field(..., description="金额")
    currency: str = Field(..., description="币种")
    payment_status: str = Field(..., description="支付状态")
    payment_date: str | None = Field(None, description="支付日期")
    project_name: str | None = Field(None, description="关联项目名称")
    product_name: str | None = Field(None, description="关联产品名称")
    country: str | None = Field(None, description="国家/地区")
    agency_name: str | None = Field(None, description="代理机构名称")
    expense_content: str | None = Field(None, description="开支内容")
    handler: str | None = Field(None, description="经办人")
    contract_received: bool = Field(..., description="是否收到纸版合同")
    invoice_settled: bool = Field(..., description="是否收到发票及冲账")
    contact: str | None = Field(None, description="联系人")
    phone: str | None = Field(None, description="联系电话")
    address: str | None = Field(None, description="地址")
    invoice_number: str | None = Field(None, description="发票号")
    remarks: str | None = Field(None, description="备注")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


# ── Inspection contact schemas ─────────────────────────────────────────


class InspectionContactCreate(BaseModel):
    """新增外检联系记录。"""

    test_item: str | None = Field(None, max_length=255, description="检测项目")
    agency_name: str | None = Field(None, max_length=255, description="外检机构")
    contact_name: _NonBlankNameStr = Field(..., description="联系人")
    contact_phone: str | None = Field(None, max_length=128, description="联系电话")
    contact_email: str | None = Field(None, description="邮箱")
    address: str | None = Field(None, description="地址")


class InspectionContactUpdate(BaseModel):
    """更新外检联系记录。"""

    test_item: str | None = Field(None, max_length=255)
    agency_name: str | None = Field(None, max_length=255)
    contact_name: str | None = Field(None, max_length=128)
    contact_phone: str | None = Field(None, max_length=128)
    contact_email: str | None = None
    address: str | None = None


class InspectionContactResponse(BaseModel):
    """外检联系记录响应。"""

    id: UUID = Field(..., description="记录ID")
    test_item: str | None = Field(None, description="检测项目")
    agency_name: str | None = Field(None, description="外检机构")
    contact_name: str | None = Field(None, description="联系人")
    contact_phone: str | None = Field(None, description="联系电话")
    contact_email: str | None = Field(None, description="邮箱")
    address: str | None = Field(None, description="地址")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class FeeTypeSummary(BaseModel):
    """按费用类型汇总。"""

    fee_type: str = Field(..., description="费用类型")
    total_amount: Decimal = Field(..., description="总金额")
    record_count: int = Field(..., description="记录数")


class PaymentStatusSummary(BaseModel):
    """按支付状态汇总。"""

    payment_status: str = Field(..., description="支付状态")
    total_amount: Decimal = Field(..., description="总金额")
    record_count: int = Field(..., description="记录数")


class YearSummary(BaseModel):
    """按年度汇总。"""

    year: int = Field(..., description="年度")
    total_amount: Decimal = Field(..., description="总金额")
    record_count: int = Field(..., description="记录数")


class YearFeeTypeSummary(BaseModel):
    """按年度×费用类型交叉汇总。"""

    year: int = Field(..., description="年度")
    fee_type: str = Field(..., description="费用类型")
    total_amount: Decimal = Field(..., description="总金额")
    record_count: int = Field(..., description="记录数")


class FeeOverview(BaseModel):
    """费用统计概览。"""

    total_records: int = Field(..., description="总记录数")
    total_amount: Decimal = Field(..., description="总金额")
    pending_amount: Decimal = Field(..., description="待支付金额")
    paid_amount: Decimal = Field(..., description="已支付金额")
    fee_type_summaries: list[FeeTypeSummary] = Field(
        default_factory=list, description="按类型汇总"
    )
    payment_status_summaries: list[PaymentStatusSummary] = Field(
        default_factory=list, description="按状态汇总"
    )
    year_summaries: list[YearSummary] = Field(
        default_factory=list, description="按年度汇总"
    )


class AgencySummary(BaseModel):
    """按付款方汇总。"""

    agency_name: str = Field(..., description="付款方名称")
    total_amount: Decimal = Field(..., description="总金额")
    record_count: int = Field(..., description="记录数")


class FeeDashboardResponse(BaseModel):
    """费用仪表盘响应。"""

    total_records: int = Field(..., description="总记录数")
    total_amount: Decimal = Field(..., description="总金额")
    pending_amount: Decimal = Field(..., description="待支付金额")
    paid_amount: Decimal = Field(..., description="已支付金额")
    fee_type_summaries: list[FeeTypeSummary] = Field(
        default_factory=list, description="按类型汇总"
    )
    payment_status_summaries: list[PaymentStatusSummary] = Field(
        default_factory=list, description="按状态汇总"
    )
    year_summaries: list[YearSummary] = Field(
        default_factory=list, description="按年度汇总"
    )
    year_fee_type_summaries: list[YearFeeTypeSummary] = Field(
        default_factory=list, description="按年度×费用类型交叉汇总"
    )
    agency_summaries: list[AgencySummary] = Field(
        default_factory=list, description="按付款方汇总 TOP15"
    )
    inspection_contact_count: int = Field(..., description="外检机构数量")
