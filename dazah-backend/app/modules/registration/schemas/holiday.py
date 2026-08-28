"""Holiday schemas."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class HolidayCreate(BaseModel):
    year: int
    date: date
    type: Literal["holiday", "makeup"]
    description: str | None = None


class HolidayResponse(BaseModel):
    id: uuid.UUID
    year: int
    date: date
    type: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
