"""预处理工艺记录 schemas"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


class PretreatmentCreate(BaseModel):
    seq_no: Optional[int] = None; received_batch: str = Field(...)
    broth_volume: Optional[str] = None; acid_type: Optional[str] = None
    acid_amount: Optional[str] = None; neutralize_ph: Optional[float] = None
    dilution_water_volume: Optional[str] = None; dilution_ratio: Optional[str] = None
    target_temp: Optional[float] = None; holding_time: Optional[str] = None
    temp_curve: Optional[str] = None; settling_time: Optional[str] = None
    settling_temp: Optional[float] = None; stirring_speed: Optional[str] = None
    stirring_time: Optional[str] = None; supernatant_volume: Optional[str] = None
    sediment_weight: Optional[str] = None; titer_before: Optional[float] = None
    titer_after: Optional[float] = None; yield_rate: Optional[float] = None
    impurity_content: Optional[float] = None; loss: Optional[float] = None
    residue_titer: Optional[float] = None


class PretreatmentUpdate(BaseModel):
    seq_no: Optional[int] = None; received_batch: Optional[str] = None
    broth_volume: Optional[str] = None; acid_type: Optional[str] = None
    acid_amount: Optional[str] = None; neutralize_ph: Optional[float] = None
    dilution_water_volume: Optional[str] = None; dilution_ratio: Optional[str] = None
    target_temp: Optional[float] = None; holding_time: Optional[str] = None
    temp_curve: Optional[str] = None; settling_time: Optional[str] = None
    settling_temp: Optional[float] = None; stirring_speed: Optional[str] = None
    stirring_time: Optional[str] = None; supernatant_volume: Optional[str] = None
    sediment_weight: Optional[str] = None; titer_before: Optional[float] = None
    titer_after: Optional[float] = None; yield_rate: Optional[float] = None
    impurity_content: Optional[float] = None; loss: Optional[float] = None
    residue_titer: Optional[float] = None


class PretreatmentResponse(BaseModel):
    id: UUID; seq_no: Optional[int] = None; received_batch: str
    broth_volume: Optional[str] = None; acid_type: Optional[str] = None
    acid_amount: Optional[str] = None; neutralize_ph: Optional[float] = None
    dilution_water_volume: Optional[str] = None; dilution_ratio: Optional[str] = None
    target_temp: Optional[float] = None; holding_time: Optional[str] = None
    temp_curve: Optional[str] = None; settling_time: Optional[str] = None
    settling_temp: Optional[float] = None; stirring_speed: Optional[str] = None
    stirring_time: Optional[str] = None; supernatant_volume: Optional[str] = None
    sediment_weight: Optional[str] = None; titer_before: Optional[float] = None
    titer_after: Optional[float] = None; yield_rate: Optional[float] = None
    impurity_content: Optional[float] = None; loss: Optional[float] = None
    residue_titer: Optional[float] = None
    created_at: datetime; updated_at: datetime
    model_config = {"from_attributes": True}
