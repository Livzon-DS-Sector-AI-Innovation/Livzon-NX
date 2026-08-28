"""Lab item schemas."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LabItemBase(BaseModel):
    """Shared lab item fields."""

    name: str = Field(..., description="物品名称")
    specification: str | None = Field(default=None, description="规格/型号")
    category: str | None = Field(
        default=None, description="类别：试剂/耗材/标准品/其他"
    )
    quantity: int | None = Field(default=0, description="数量")
    unit: str | None = Field(default=None, description="单位")
    location: str | None = Field(default=None, description="存放位置")
    supplier: str | None = Field(default=None, description="供应商")
    batch_no: str | None = Field(default=None, description="批号")
    expiry_date: date | None = Field(default=None, description="有效期至")
    status: str = Field(default="normal", description="状态")
    remark: str | None = Field(default=None, description="备注")


class CreateLabItemRequest(LabItemBase):
    pass


class UpdateLabItemRequest(BaseModel):
    name: str | None = None
    specification: str | None = None
    category: str | None = None
    quantity: int | None = None
    unit: str | None = None
    location: str | None = None
    supplier: str | None = None
    batch_no: str | None = None
    expiry_date: date | None = None
    status: str | None = None
    remark: str | None = None


class LabItemOut(LabItemBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
