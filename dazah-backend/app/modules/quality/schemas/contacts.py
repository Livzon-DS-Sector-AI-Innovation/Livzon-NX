"""Department weekly confirmation Pydantic schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DepartmentWeeklyConfirmationOut(BaseModel):
    id: uuid.UUID
    department: str
    week_key: str
    production_status: str
    deviation_status: str
    confirmed_by_id: uuid.UUID | None = None
    confirmed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConfirmProductionStatusRequest(BaseModel):
    department: str
    week_key: str
    production_status: str
    deviation_status: str = "unsubmitted"
