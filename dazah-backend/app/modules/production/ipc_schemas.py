"""Bounded analysis of IPC values supplied from the local production form."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class IpcSampleInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    stage: Literal["seed", "fermentation"]
    tank: str = Field(min_length=1, max_length=64)
    sampling_time: datetime
    culture_hours: float | None = Field(default=None, ge=0)
    ph: float | None = Field(default=None, ge=0, le=14)
    residual_sugar: float | None = Field(default=None, ge=0)
    absorbance: float | None = Field(default=None, ge=0)
    remarks: str | None = Field(default=None, max_length=1000)


class IpcAnalysisInput(BaseModel):
    samples: list[IpcSampleInput] = Field(min_length=1, max_length=100)


class IpcAnalysisResult(BaseModel):
    sample_count: int
    seed_count: int
    fermentation_count: int
    tank_count: int
    ph_min: float | None
    ph_max: float | None
    residual_sugar_min: float | None
    residual_sugar_max: float | None
    source: Literal["user_supplied"] = "user_supplied"
    persisted: Literal[False] = False
    limitation: str = "仅汇总提交的IPC数据；不保存台账，不作放行、染菌或放罐判断。"
