"""Complaint schemas."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ComplaintBase(BaseModel):
    """Shared complaint fields."""

    complaint_code: str = Field(..., description="投诉编号")
    title: str = Field(..., description="投诉标题")
    complaint_source: str | None = Field(default=None, description="投诉来源")
    customer_name: str | None = Field(default=None, description="客户名称")
    product_name: str | None = Field(default=None, description="涉及产品")
    batch_number: str | None = Field(default=None, description="批号")
    complaint_date: date | None = Field(default=None, description="投诉日期")
    complaint_category: str | None = Field(default=None, description="投诉类别")
    description: str | None = Field(default=None, description="投诉描述")
    handler: str | None = Field(default=None, description="处理人")
    investigation_result: str | None = Field(default=None, description="调查结论")
    response_content: str | None = Field(default=None, description="回复内容")
    response_date: date | None = Field(default=None, description="回复日期")
    capa_code: str | None = Field(default=None, description="关联CAPA编号")
    status: str = Field(default="pending", description="状态")


class CreateComplaintRequest(ComplaintBase):
    """Create complaint request."""

    pass


class UpdateComplaintRequest(BaseModel):
    """Update complaint request."""

    title: str | None = None
    complaint_source: str | None = None
    customer_name: str | None = None
    product_name: str | None = None
    batch_number: str | None = None
    complaint_date: date | None = None
    complaint_category: str | None = None
    description: str | None = None
    handler: str | None = None
    investigation_result: str | None = None
    response_content: str | None = None
    response_date: date | None = None
    capa_code: str | None = None
    status: str | None = None


class ComplaintOut(ComplaintBase):
    """Complaint output."""

    id: UUID
    closed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
