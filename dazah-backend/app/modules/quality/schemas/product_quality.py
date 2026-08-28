"""Product quality management schemas."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProductQualityBase(BaseModel):
    """Shared product quality fields."""

    record_code: str = Field(..., description="质量编号")
    record_type: str = Field(default="customer_standard", description="质量记录类型")
    title: str = Field(..., description="标题")
    product_name: str | None = Field(default=None, description="产品名称")
    batch_number: str | None = Field(default=None, description="批号")
    review_type: str | None = Field(default=None, description="评审类型")
    review_period_start: date | None = Field(default=None, description="回顾周期开始")
    review_period_end: date | None = Field(default=None, description="回顾周期结束")
    batch_count: int | None = Field(default=None, description="批次数量")
    qualified_count: int | None = Field(default=None, description="合格批次")
    unqualified_count: int | None = Field(default=None, description="不合格批次")
    oos_count: int | None = Field(default=None, description="OOS次数")
    deviation_count: int | None = Field(default=None, description="偏差次数")
    change_count: int | None = Field(default=None, description="变更次数")
    quality_trend: str | None = Field(default=None, description="质量趋势")
    conclusion: str | None = Field(default=None, description="评审结论")
    suggestions: str | None = Field(default=None, description="改进建议")
    reviewer: str | None = Field(default=None, description="评审人")
    review_date: date | None = Field(default=None, description="评审日期")
    status: str = Field(default="draft", description="状态")


class CreateProductQualityRequest(ProductQualityBase):
    """Create product quality request."""

    pass


class UpdateProductQualityRequest(BaseModel):
    """Update product quality request."""

    title: str | None = None
    product_name: str | None = None
    batch_number: str | None = None
    review_type: str | None = None
    review_period_start: date | None = None
    review_period_end: date | None = None
    batch_count: int | None = None
    qualified_count: int | None = None
    unqualified_count: int | None = None
    oos_count: int | None = None
    deviation_count: int | None = None
    change_count: int | None = None
    quality_trend: str | None = None
    conclusion: str | None = None
    suggestions: str | None = None
    reviewer: str | None = None
    review_date: date | None = None
    status: str | None = None


class ProductQualityOut(ProductQualityBase):
    """Product quality output."""

    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
