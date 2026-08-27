"""Product quality customer standard schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ProductQualityStandardCreate(BaseModel):
    """Create product quality customer standard request."""

    customer_name: str | None = Field(default=None, description="客户名称")
    quality_standard: str | None = Field(default=None, description="质量标准")
    shipping_trend_url: str | None = Field(default=None, description="历史发货趋势")
    special_requirements: str | None = Field(default=None, description="特殊要求")
    packaging_requirements: str | None = Field(default=None, description="包装要求")
    label_requirements: str | None = Field(default=None, description="标签要求")
    pallet_requirements: str | None = Field(default=None, description="发货打托要求")
    target_market: str | None = Field(default=None, description="目标市场")
    registration_status: str | None = Field(default=None, description="注册情况")
    other_notes: str | None = Field(default=None, description="其他注意事项")


class ProductQualityStandardUpdate(BaseModel):
    """Update product quality customer standard request."""

    customer_name: str | None = Field(default=None, description="客户名称")
    quality_standard: str | None = Field(default=None, description="质量标准")
    shipping_trend_url: str | None = Field(default=None, description="历史发货趋势")
    special_requirements: str | None = Field(default=None, description="特殊要求")
    packaging_requirements: str | None = Field(default=None, description="包装要求")
    label_requirements: str | None = Field(default=None, description="标签要求")
    pallet_requirements: str | None = Field(default=None, description="发货打托要求")
    target_market: str | None = Field(default=None, description="目标市场")
    registration_status: str | None = Field(default=None, description="注册情况")
    other_notes: str | None = Field(default=None, description="其他注意事项")


class ProductQualityStandardOut(BaseModel):
    """Product quality customer standard output."""

    record_id: str
    serial_number: str | None = None
    customer_name: str | None = None
    quality_standard: str | None = None
    shipping_trend_url: str | None = None
    special_requirements: str | None = None
    packaging_requirements: str | None = None
    label_requirements: str | None = None
    packaging_photos: list[dict[str, Any]] = Field(default_factory=list)
    pallet_requirements: str | None = None
    target_market: str | None = None
    registration_status: str | None = None
    other_notes: str | None = None
    created_at: datetime
    updated_at: datetime
