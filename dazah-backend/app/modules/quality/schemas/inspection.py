"""Inspection schemas."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InspectionRecordBase(BaseModel):
    """Shared inspection fields."""

    inspection_no: str = Field(..., description="检验编号")
    product_name: str | None = Field(default=None, description="产品名称")
    batch_no: str | None = Field(default=None, description="批号")
    inspection_type: str | None = Field(
        default=None, description="检验类型：来料检验/中间体检验/成品检验/留样检验"
    )
    inspection_item: str | None = Field(default=None, description="检验项目")
    specification: str | None = Field(default=None, description="标准规定")
    test_result: str | None = Field(default=None, description="检验结果")
    conclusion: str | None = Field(default=None, description="检验结论：合格/不合格")
    inspector: str | None = Field(default=None, description="检验人")
    inspection_date: date | None = Field(default=None, description="检验日期")
    department: str | None = Field(default=None, description="检验部门")
    remark: str | None = Field(default=None, description="备注")


class CreateInspectionRequest(InspectionRecordBase):
    """Create inspection request."""

    pass


class UpdateInspectionRequest(BaseModel):
    """Update inspection request."""

    inspection_no: str | None = None
    product_name: str | None = None
    batch_no: str | None = None
    inspection_type: str | None = None
    inspection_item: str | None = None
    specification: str | None = None
    test_result: str | None = None
    conclusion: str | None = None
    inspector: str | None = None
    inspection_date: date | None = None
    department: str | None = None
    remark: str | None = None


class InspectionRecordOut(InspectionRecordBase):
    """Inspection record output."""

    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
