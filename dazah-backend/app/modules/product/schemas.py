"""Product business request and response schemas live here."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProductBase(BaseModel):
    name: str = Field(..., max_length=128, description="产品名称")
    major_category: str | None = Field(None, max_length=32, description="产品代码")
    formulation_code: str | None = Field(None, max_length=32, description="制剂代码")
    product_type: str | None = Field(None, max_length=32, description="产品剂型")
    spec: str | None = Field(None, max_length=128, description="生产规格")
    capacity_range: str | None = Field(None, max_length=256, description="生产批量")
    unit: str | None = Field(None, max_length=16, description="单位")
    indication: str | None = Field(None, max_length=64, description="适应症")


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str | None = Field(None, max_length=128)
    major_category: str | None = Field(None, max_length=32)
    formulation_code: str | None = Field(None, max_length=32)
    product_type: str | None = Field(None, max_length=32)
    spec: str | None = Field(None, max_length=128)
    capacity_range: str | None = Field(None, max_length=256)
    unit: str | None = Field(None, max_length=16)
    indication: str | None = Field(None, max_length=64)


class ProductResponse(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    feishu_record_id: str | None = None
    feishu_synced_at: date | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SyncStatusResponse(BaseModel):
    local_total: int
    feishu_total: int
    synced_count: int
    unsynced_count: int
    last_sync_at: datetime | None = None
