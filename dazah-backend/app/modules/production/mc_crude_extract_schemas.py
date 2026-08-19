"""MC 霉酚酸 — 粗提工段 Pydantic Schemas"""

from datetime import date, datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator
from app.shared.validators import normalize_yield_rate


# ═══════════ 发酵液 ═══════════

class FermentationLiquidCreate(BaseModel):
    batch_no: str
    workshop: str = "101"
    year: int
    annual_seq: Optional[int] = None
    input_volume: Optional[float] = None
    potency: Optional[float] = None
    product_qty: Optional[float] = None
    create_date: Optional[date] = None
    remarks: Optional[str] = None

class FermentationLiquidResponse(BaseModel):
    id: UUID; batch_no: str; workshop: str; year: int
    annual_seq: Optional[int] = None; input_volume: Optional[float] = None
    potency: Optional[float] = None; product_qty: Optional[float] = None
    create_date: Optional[date] = None; remarks: Optional[str] = None
    created_at: datetime; updated_at: datetime
    model_config = {"from_attributes": True}


# ═══════════ 提炼批次 ═══════════

class RefiningBatchCreate(BaseModel):
    batch_no: str; workshop: str = "201-2"
    fermentation_no: str; year: int; month: int
    monthly_seq: Optional[int] = None
    produce_date: Optional[date] = None
    remarks: Optional[str] = None

class RefiningBatchResponse(BaseModel):
    id: UUID; batch_no: str; workshop: str; fermentation_no: str
    year: int; month: int; monthly_seq: Optional[int] = None
    produce_date: Optional[date] = None; remarks: Optional[str] = None
    created_at: datetime; updated_at: datetime
    model_config = {"from_attributes": True}


# ═══════════ 分罐记录 ═══════════

class SubTankRecordCreate(BaseModel):
    parent_batch: str; tank_no: int; batch_no: str
    fl_volume: Optional[float] = None; fl_potency: Optional[float] = None
    fl_product_qty: Optional[float] = None; total_input: Optional[float] = None
    cumulative_qty: Optional[float] = None
    crude_weight: Optional[float] = None; bag_weight: Optional[float] = None
    crude_content: Optional[float] = None; crude_moisture: Optional[float] = None
    crude_product_qty: Optional[float] = None; yield_rate: Optional[float] = None
    cumulative_crude_qty: Optional[float] = None; cumulative_crude_yield: Optional[float] = None
    remarks: Optional[str] = None

    @field_validator('yield_rate')
    @classmethod
    def normalize_yield_rate_field(cls, v: float | None) -> float | None:
        return normalize_yield_rate(v)

class SubTankRecordUpdate(BaseModel):
    fl_volume: Optional[float] = None; fl_potency: Optional[float] = None
    fl_product_qty: Optional[float] = None; total_input: Optional[float] = None
    cumulative_qty: Optional[float] = None
    crude_weight: Optional[float] = None; bag_weight: Optional[float] = None
    crude_content: Optional[float] = None; crude_moisture: Optional[float] = None
    crude_product_qty: Optional[float] = None; yield_rate: Optional[float] = None
    cumulative_crude_qty: Optional[float] = None; cumulative_crude_yield: Optional[float] = None
    remarks: Optional[str] = None

    @field_validator('yield_rate')
    @classmethod
    def normalize_yield_rate_field(cls, v: float | None) -> float | None:
        return normalize_yield_rate(v)

class SubTankRecordResponse(BaseModel):
    id: UUID; parent_batch: str; tank_no: int; batch_no: str
    fl_volume: Optional[float] = None; fl_potency: Optional[float] = None
    fl_product_qty: Optional[float] = None; total_input: Optional[float] = None
    cumulative_qty: Optional[float] = None
    crude_weight: Optional[float] = None; bag_weight: Optional[float] = None
    crude_content: Optional[float] = None; crude_moisture: Optional[float] = None
    crude_product_qty: Optional[float] = None; yield_rate: Optional[float] = None
    cumulative_crude_qty: Optional[float] = None; cumulative_crude_yield: Optional[float] = None
    remarks: Optional[str] = None
    created_at: datetime; updated_at: datetime
    model_config = {"from_attributes": True}


# ═══════════ 钠化步骤 ═══════════

class SodiumStepCreate(BaseModel):
    sub_tank_id: str; seq_no: int = 1
    na_before_volume: Optional[float] = None; na_after_volume: Optional[float] = None
    na_potency: Optional[float] = None; na_product_qty: Optional[float] = None
    sodium_total: Optional[float] = None; ph_value: Optional[float] = None
    alkali_usage: Optional[float] = None

class SodiumStepResponse(BaseModel):
    id: UUID; sub_tank_id: str; seq_no: int
    na_before_volume: Optional[float] = None; na_after_volume: Optional[float] = None
    na_potency: Optional[float] = None; na_product_qty: Optional[float] = None
    sodium_total: Optional[float] = None; ph_value: Optional[float] = None
    alkali_usage: Optional[float] = None
    created_at: datetime; updated_at: datetime
    model_config = {"from_attributes": True}


# ═══════════ 酸化步骤 ═══════════

class AcidStepCreate(BaseModel):
    sub_tank_id: str; seq_no: int = 1
    acid_filter_volume: Optional[float] = None; acid_potency: Optional[float] = None
    acid_product_qty: Optional[float] = None; filter_subtotal: Optional[float] = None
    ph_value: Optional[float] = None; acid_usage: Optional[float] = None
    acid_filter_content: Optional[float] = None; filter_total: Optional[float] = None
    na_to_fermentation_yield: Optional[float] = None; monthly_cumulative_yield: Optional[float] = None

class AcidStepResponse(BaseModel):
    id: UUID; sub_tank_id: str; seq_no: int
    acid_filter_volume: Optional[float] = None; acid_potency: Optional[float] = None
    acid_product_qty: Optional[float] = None; filter_subtotal: Optional[float] = None
    ph_value: Optional[float] = None; acid_usage: Optional[float] = None
    acid_filter_content: Optional[float] = None; filter_total: Optional[float] = None
    na_to_fermentation_yield: Optional[float] = None; monthly_cumulative_yield: Optional[float] = None
    created_at: datetime; updated_at: datetime
    model_config = {"from_attributes": True}


# ═══════════ 完整嵌套响应 ═══════════

class SubTankFullResponse(BaseModel):
    """分罐 + 钠化步骤 + 酸化步骤"""
    sub_tank: SubTankRecordResponse
    sodium_steps: list[SodiumStepResponse] = []
    acid_steps: list[AcidStepResponse] = []

class CrudeExtractFullResponse(BaseModel):
    """完整嵌套：发酵液 → 提炼 → 分罐 → 钠化/酸化"""
    fermentation: FermentationLiquidResponse
    refining: RefiningBatchResponse
    sub_tanks: list[SubTankFullResponse] = []
    model_config = {"from_attributes": True}
