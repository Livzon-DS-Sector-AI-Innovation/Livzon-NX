"""Drug schemas."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class DrugNodeCreate(BaseModel):
    node_index: int = Field(ge=1, le=10)
    actual_date: date | None = None


class DrugNodeUpdate(BaseModel):
    node_index: int = Field(ge=1, le=10)
    actual_date: date | None = None


class DrugCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    type: Literal["仿制药", "创新药", "原料药"]
    acceptance_date: date


class DrugUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    type: Literal["仿制药", "创新药", "原料药"] | None = None
    acceptance_date: date | None = None
    nodes: list[DrugNodeUpdate] | None = None


class DrugNodeResponse(BaseModel):
    id: uuid.UUID
    drug_id: uuid.UUID
    node_index: int
    actual_date: date | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DrugResponse(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    acceptance_date: date
    current_node: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DrugWithNodesResponse(DrugResponse):
    nodes: list[DrugNodeResponse]
