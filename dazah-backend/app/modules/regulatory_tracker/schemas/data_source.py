"""DataSource schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DataSourceBase(BaseModel):
    code: str
    name: str
    base_url: str | None = None
    enabled: bool = True


class DataSourceCreate(DataSourceBase):
    pass


class DataSourceUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    enabled: bool | None = None


class DataSourceRead(DataSourceBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
