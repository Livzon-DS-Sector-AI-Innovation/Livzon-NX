"""MC 霉酚酸 — 提取工段 Pydantic Schemas"""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.shared.validators import normalize_yield_rate

# ═══════════════════════ 提取主表 ═══════════════════════


class ExtractionRecordCreate(BaseModel):
    batch_no: str = Field(..., description="提取批号（MC-260129）")
    workshop: str = Field(default="201-2")
    extract_date: date | None = Field(None)
    total_crude_weight: float | None = Field(None, description="粗品总投入量(kg)")
    total_converted_qty: float | None = Field(None, description="折纯总量(kg)")
    filter_product_qty: float | None = Field(None, description="滤液产品量(kg)")
    filter_potency: float | None = Field(None, description="滤液效价(mg/L)")
    filter_volume: float | None = Field(None, description="滤液体积(m³)")
    carbon_usage: float | None = Field(None, description="用碳量(kg)")
    wet_weight: float | None = Field(None, description="湿粉毛重(kg)")
    wet_content: float | None = Field(None, description="湿粉含量(%)")
    dry_loss: float | None = Field(None, description="干燥失重(%)")
    dry_weight: float | None = Field(None, description="折干产量(kg)")
    yield_rate: float | None = Field(None, description="单步收率(%)")
    mother_volume: float | None = Field(None, description="母液体积(kL)")
    mother_content: float | None = Field(None, description="母液含量(mg/L)")
    mother_loss: float | None = Field(None, description="母液损失量(kg)")
    yield_to_filter: float | None = Field(None, description="对滤液收率(%)")
    status: int = Field(default=0, description="状态")
    remarks: str | None = Field(None)

    @field_validator("yield_rate")
    @classmethod
    def normalize_yield_rate_field(cls, v: float | None) -> float | None:
        return normalize_yield_rate(v)


class ExtractionRecordUpdate(BaseModel):
    batch_no: str | None = None
    workshop: str | None = None
    extract_date: date | None = None
    total_crude_weight: float | None = None
    total_converted_qty: float | None = None
    filter_product_qty: float | None = None
    filter_potency: float | None = None
    filter_volume: float | None = None
    carbon_usage: float | None = None
    wet_weight: float | None = None
    wet_content: float | None = None
    dry_loss: float | None = None
    dry_weight: float | None = None
    yield_rate: float | None = None
    mother_volume: float | None = None
    mother_content: float | None = None
    mother_loss: float | None = None
    yield_to_filter: float | None = None
    status: int | None = None
    remarks: str | None = None

    @field_validator("yield_rate")
    @classmethod
    def normalize_yield_rate_field(cls, v: float | None) -> float | None:
        return normalize_yield_rate(v)


class ExtractionRecordResponse(BaseModel):
    id: UUID
    batch_no: str
    workshop: str
    extract_date: date | None = None
    total_crude_weight: float | None = None
    total_converted_qty: float | None = None
    filter_product_qty: float | None = None
    filter_potency: float | None = None
    filter_volume: float | None = None
    carbon_usage: float | None = None
    wet_weight: float | None = None
    wet_content: float | None = None
    dry_loss: float | None = None
    dry_weight: float | None = None
    yield_rate: float | None = None
    mother_volume: float | None = None
    mother_content: float | None = None
    mother_loss: float | None = None
    yield_to_filter: float | None = None
    status: int
    remarks: str | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


# ═══════════════════════ 提取投入明细 ═══════════════════════


class ExtractionInputCreate(BaseModel):
    extraction_batch: str = Field(..., description="提取批号")
    seq_no: int = Field(default=1, description="投入顺序号")
    crude_batch_no: str = Field(..., description="粗品批号")
    crude_weight: float = Field(..., description="粗品重量(kg)")
    crude_moisture: float = Field(..., description="水分(%)")
    crude_content: float = Field(..., description="含量(%)")
    converted_qty: float | None = Field(None, description="折合产品重量(kg)")


class ExtractionInputUpdate(BaseModel):
    seq_no: int | None = None
    crude_batch_no: str | None = None
    crude_weight: float | None = None
    crude_moisture: float | None = None
    crude_content: float | None = None
    converted_qty: float | None = None


class ExtractionInputResponse(BaseModel):
    id: UUID
    extraction_batch: str
    seq_no: int
    crude_batch_no: str
    crude_weight: float
    crude_moisture: float
    crude_content: float
    converted_qty: float | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
