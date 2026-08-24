"""MC 霉酚酸 — MC 二次精制工段 Pydantic Schemas"""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.shared.validators import normalize_yield_rate


class McRefinementRecordCreate(BaseModel):
    batch_no: str = Field(..., description="二次结晶批号（MC-F2-260101）")
    workshop: str = Field(default="201-2")
    input_date: date | None = None
    total_input_weight: float | None = Field(None, description="总重(kg)")
    total_pure_qty: float | None = Field(None, description="折纯量(kg)")
    dry_product_total: float | None = Field(None, description="折干产品总量(kg)")
    dissolution_tank: str | None = Field(None, description="溶解用罐")
    butyl_acetate_volume: float | None = Field(None, description="加入丁酯量(m³)")
    crystallization_tank: str | None = Field(None, description="结晶用罐")
    wet_weight: float | None = Field(None, description="湿粉重量(kg)")
    dry_weight: float | None = Field(None, description="干粉重量(kg)")
    single_step_yield: float | None = Field(None, description="单步收率(%)")
    cumulative_dry_product: float | None = Field(None, description="累计折干产品量(kg)")
    cumulative_dry_weight: float | None = Field(None, description="累计干粉重量(kg)")
    cumulative_yield: float | None = Field(None, description="二次结晶累计收率(%)")
    mother_liquid_content: float | None = Field(None, description="二次母液含量(mg/L)")
    mother_liquid_volume: float | None = Field(None, description="二次母液体积(m³)")
    mother_liquid_loss: float | None = Field(None, description="母液损失量(kg)")
    status: int = Field(default=0, description="状态")
    remarks: str | None = None

    @field_validator("single_step_yield", "cumulative_yield")
    @classmethod
    def normalize_yield_rate_field(cls, v: float | None) -> float | None:
        return normalize_yield_rate(v)


class McRefinementRecordUpdate(BaseModel):
    batch_no: str | None = None
    workshop: str | None = None
    input_date: date | None = None
    total_input_weight: float | None = None
    total_pure_qty: float | None = None
    dry_product_total: float | None = None
    dissolution_tank: str | None = None
    butyl_acetate_volume: float | None = None
    crystallization_tank: str | None = None
    wet_weight: float | None = None
    dry_weight: float | None = None
    single_step_yield: float | None = None
    cumulative_dry_product: float | None = None
    cumulative_dry_weight: float | None = None
    cumulative_yield: float | None = None
    mother_liquid_content: float | None = None
    mother_liquid_volume: float | None = None
    mother_liquid_loss: float | None = None
    status: int | None = None
    remarks: str | None = None

    @field_validator("single_step_yield", "cumulative_yield")
    @classmethod
    def normalize_yield_rate_field(cls, v: float | None) -> float | None:
        return normalize_yield_rate(v)


class McRefinementRecordResponse(BaseModel):
    id: UUID
    batch_no: str
    workshop: str
    input_date: date | None = None
    total_input_weight: float | None = None
    total_pure_qty: float | None = None
    dry_product_total: float | None = None
    dissolution_tank: str | None = None
    butyl_acetate_volume: float | None = None
    crystallization_tank: str | None = None
    wet_weight: float | None = None
    dry_weight: float | None = None
    single_step_yield: float | None = None
    cumulative_dry_product: float | None = None
    cumulative_dry_weight: float | None = None
    cumulative_yield: float | None = None
    mother_liquid_content: float | None = None
    mother_liquid_volume: float | None = None
    mother_liquid_loss: float | None = None
    status: int
    remarks: str | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class McRefinementInputCreate(BaseModel):
    refinement_batch: str = Field(..., description="二次结晶批号")
    wet_batch_no: str = Field(..., description="上游湿粉批号（6位日期）")
    input_weight: float = Field(..., description="重量(kg)")
    moisture: float = Field(..., description="水分(%)")
    content: float = Field(..., description="含量(%)")
    pure_qty: float | None = Field(None, description="折纯量(kg)")


class McRefinementInputUpdate(BaseModel):
    wet_batch_no: str | None = None
    input_weight: float | None = None
    moisture: float | None = None
    content: float | None = None
    pure_qty: float | None = None


class McRefinementInputResponse(BaseModel):
    id: UUID
    refinement_batch: str
    wet_batch_no: str
    input_weight: float
    moisture: float
    content: float
    pure_qty: float | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
