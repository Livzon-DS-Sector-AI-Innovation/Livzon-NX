"""Return & recall schemas."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReturnRecallBase(BaseModel):
    """Shared return/recall fields."""

    record_code: str = Field(..., description="记录编号")
    record_type: str = Field(default="return", description="记录类型：return / recall")
    title: str = Field(..., description="标题")
    product_name: str | None = Field(default=None, description="产品名称")
    batch_number: str | None = Field(default=None, description="批号")
    quantity: float | None = Field(default=None, description="数量")
    unit: str | None = Field(default=None, description="单位")
    customer_name: str | None = Field(default=None, description="客户/退货方")
    reason: str | None = Field(default=None, description="退货/召回原因")
    occurrence_date: date | None = Field(default=None, description="发生日期")
    handler: str | None = Field(default=None, description="处理人")
    disposition: str | None = Field(default=None, description="处置方式")
    assessment_date: date | None = Field(default=None, description="评估日期")
    completion_date: date | None = Field(default=None, description="完成日期")
    status: str = Field(default="pending", description="状态")


class CreateReturnRecallRequest(ReturnRecallBase):
    """Create return/recall request."""

    pass


class UpdateReturnRecallRequest(BaseModel):
    """Update return/recall request."""

    title: str | None = None
    record_type: str | None = None
    product_name: str | None = None
    batch_number: str | None = None
    quantity: float | None = None
    unit: str | None = None
    customer_name: str | None = None
    reason: str | None = None
    occurrence_date: date | None = None
    handler: str | None = None
    disposition: str | None = None
    assessment_date: date | None = None
    completion_date: date | None = None
    status: str | None = None


class ReturnRecallOut(ReturnRecallBase):
    """Return/recall output."""

    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
