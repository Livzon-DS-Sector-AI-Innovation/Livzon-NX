"""OOS/OOT schemas."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OosOotRecordBase(BaseModel):
    """Shared OOS/OOT fields."""

    record_code: str = Field(..., description="记录编号")
    record_type: str = Field(default="OOS", description="记录类型：OOS / OOT")
    title: str = Field(..., description="标题")
    department: str | None = Field(default=None, description="责任部门")
    product_name: str | None = Field(default=None, description="产品名称")
    batch_number: str | None = Field(default=None, description="批号")
    test_item: str | None = Field(default=None, description="检验项目")
    specification: str | None = Field(default=None, description="标准规定")
    test_result: str | None = Field(default=None, description="检验结果")
    discovery_date: date | None = Field(default=None, description="发现日期")
    description: str | None = Field(default=None, description="描述")
    investigation_result: str | None = Field(default=None, description="调查结论")
    corrective_actions: str | None = Field(default=None, description="纠正措施")
    status: str = Field(default="open", description="状态")


class CreateOosOotRequest(OosOotRecordBase):
    """Create OOS/OOT request."""

    pass


class UpdateOosOotRequest(BaseModel):
    """Update OOS/OOT request."""

    title: str | None = None
    record_type: str | None = None
    department: str | None = None
    product_name: str | None = None
    batch_number: str | None = None
    test_item: str | None = None
    specification: str | None = None
    test_result: str | None = None
    discovery_date: date | None = None
    description: str | None = None
    investigation_result: str | None = None
    corrective_actions: str | None = None
    status: str | None = None


class OosOotRecordOut(OosOotRecordBase):
    """OOS/OOT record output."""

    id: UUID
    closed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
