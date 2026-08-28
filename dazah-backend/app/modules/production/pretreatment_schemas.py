"""预处理工艺记录 schemas"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PretreatmentCreate(BaseModel):
    seq_no: int | None = None
    received_batch: str = Field(...)
    broth_volume: str | None = None
    acid_type: str | None = None
    acid_amount: str | None = None
    neutralize_ph: float | None = None
    dilution_water_volume: str | None = None
    dilution_ratio: str | None = None
    target_temp: float | None = None
    holding_time: str | None = None
    temp_curve: str | None = None
    settling_time: str | None = None
    settling_temp: float | None = None
    stirring_speed: str | None = None
    stirring_time: str | None = None
    supernatant_volume: str | None = None
    sediment_weight: str | None = None
    titer_before: float | None = None
    titer_after: float | None = None
    yield_rate: float | None = None
    impurity_content: float | None = None
    loss: float | None = None
    residue_titer: float | None = None


class PretreatmentUpdate(BaseModel):
    seq_no: int | None = None
    received_batch: str | None = None
    broth_volume: str | None = None
    acid_type: str | None = None
    acid_amount: str | None = None
    neutralize_ph: float | None = None
    dilution_water_volume: str | None = None
    dilution_ratio: str | None = None
    target_temp: float | None = None
    holding_time: str | None = None
    temp_curve: str | None = None
    settling_time: str | None = None
    settling_temp: float | None = None
    stirring_speed: str | None = None
    stirring_time: str | None = None
    supernatant_volume: str | None = None
    sediment_weight: str | None = None
    titer_before: float | None = None
    titer_after: float | None = None
    yield_rate: float | None = None
    impurity_content: float | None = None
    loss: float | None = None
    residue_titer: float | None = None


class PretreatmentResponse(BaseModel):
    id: UUID
    seq_no: int | None = None
    received_batch: str
    broth_volume: str | None = None
    acid_type: str | None = None
    acid_amount: str | None = None
    neutralize_ph: float | None = None
    dilution_water_volume: str | None = None
    dilution_ratio: str | None = None
    target_temp: float | None = None
    holding_time: str | None = None
    temp_curve: str | None = None
    settling_time: str | None = None
    settling_temp: float | None = None
    stirring_speed: str | None = None
    stirring_time: str | None = None
    supernatant_volume: str | None = None
    sediment_weight: str | None = None
    titer_before: float | None = None
    titer_after: float | None = None
    yield_rate: float | None = None
    impurity_content: float | None = None
    loss: float | None = None
    residue_titer: float | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
