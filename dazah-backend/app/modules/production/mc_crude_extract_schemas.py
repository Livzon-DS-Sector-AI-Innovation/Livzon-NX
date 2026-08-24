"""MC 霉酚酸 — 粗提工段 Pydantic Schemas"""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

from app.shared.validators import normalize_yield_rate

# ═══════════ 发酵液 ═══════════


class FermentationLiquidCreate(BaseModel):
    batch_no: str
    workshop: str = "101"
    year: int
    annual_seq: int | None = None
    input_volume: float | None = None
    potency: float | None = None
    product_qty: float | None = None
    create_date: date | None = None
    remarks: str | None = None


class FermentationLiquidResponse(BaseModel):
    id: UUID
    batch_no: str
    workshop: str
    year: int
    annual_seq: int | None = None
    input_volume: float | None = None
    potency: float | None = None
    product_qty: float | None = None
    create_date: date | None = None
    remarks: str | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


# ═══════════ 提炼批次 ═══════════


class RefiningBatchCreate(BaseModel):
    batch_no: str
    workshop: str = "201-2"
    fermentation_no: str
    year: int
    month: int
    monthly_seq: int | None = None
    produce_date: date | None = None
    remarks: str | None = None


class RefiningBatchResponse(BaseModel):
    id: UUID
    batch_no: str
    workshop: str
    fermentation_no: str
    year: int
    month: int
    monthly_seq: int | None = None
    produce_date: date | None = None
    remarks: str | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


# ═══════════ 分罐记录 ═══════════


class SubTankRecordCreate(BaseModel):
    parent_batch: str
    tank_no: int
    batch_no: str
    fl_volume: float | None = None
    fl_potency: float | None = None
    fl_product_qty: float | None = None
    total_input: float | None = None
    cumulative_qty: float | None = None
    crude_weight: float | None = None
    bag_weight: float | None = None
    crude_content: float | None = None
    crude_moisture: float | None = None
    crude_product_qty: float | None = None
    yield_rate: float | None = None
    cumulative_crude_qty: float | None = None
    cumulative_crude_yield: float | None = None
    remarks: str | None = None

    @field_validator("yield_rate")
    @classmethod
    def normalize_yield_rate_field(cls, v: float | None) -> float | None:
        return normalize_yield_rate(v)


class SubTankRecordUpdate(BaseModel):
    fl_volume: float | None = None
    fl_potency: float | None = None
    fl_product_qty: float | None = None
    total_input: float | None = None
    cumulative_qty: float | None = None
    crude_weight: float | None = None
    bag_weight: float | None = None
    crude_content: float | None = None
    crude_moisture: float | None = None
    crude_product_qty: float | None = None
    yield_rate: float | None = None
    cumulative_crude_qty: float | None = None
    cumulative_crude_yield: float | None = None
    remarks: str | None = None

    @field_validator("yield_rate")
    @classmethod
    def normalize_yield_rate_field(cls, v: float | None) -> float | None:
        return normalize_yield_rate(v)


class SubTankRecordResponse(BaseModel):
    id: UUID
    parent_batch: str
    tank_no: int
    batch_no: str
    fl_volume: float | None = None
    fl_potency: float | None = None
    fl_product_qty: float | None = None
    total_input: float | None = None
    cumulative_qty: float | None = None
    crude_weight: float | None = None
    bag_weight: float | None = None
    crude_content: float | None = None
    crude_moisture: float | None = None
    crude_product_qty: float | None = None
    yield_rate: float | None = None
    cumulative_crude_qty: float | None = None
    cumulative_crude_yield: float | None = None
    remarks: str | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


# ═══════════ 钠化步骤 ═══════════


class SodiumStepCreate(BaseModel):
    sub_tank_id: str
    seq_no: int = 1
    na_before_volume: float | None = None
    na_after_volume: float | None = None
    na_potency: float | None = None
    na_product_qty: float | None = None
    sodium_total: float | None = None
    ph_value: float | None = None
    alkali_usage: float | None = None


class SodiumStepResponse(BaseModel):
    id: UUID
    sub_tank_id: str
    seq_no: int
    na_before_volume: float | None = None
    na_after_volume: float | None = None
    na_potency: float | None = None
    na_product_qty: float | None = None
    sodium_total: float | None = None
    ph_value: float | None = None
    alkali_usage: float | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


# ═══════════ 酸化步骤 ═══════════


class AcidStepCreate(BaseModel):
    sub_tank_id: str
    seq_no: int = 1
    acid_filter_volume: float | None = None
    acid_potency: float | None = None
    acid_product_qty: float | None = None
    filter_subtotal: float | None = None
    ph_value: float | None = None
    acid_usage: float | None = None
    acid_filter_content: float | None = None
    filter_total: float | None = None
    na_to_fermentation_yield: float | None = None
    monthly_cumulative_yield: float | None = None


class AcidStepResponse(BaseModel):
    id: UUID
    sub_tank_id: str
    seq_no: int
    acid_filter_volume: float | None = None
    acid_potency: float | None = None
    acid_product_qty: float | None = None
    filter_subtotal: float | None = None
    ph_value: float | None = None
    acid_usage: float | None = None
    acid_filter_content: float | None = None
    filter_total: float | None = None
    na_to_fermentation_yield: float | None = None
    monthly_cumulative_yield: float | None = None
    created_at: datetime
    updated_at: datetime
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
