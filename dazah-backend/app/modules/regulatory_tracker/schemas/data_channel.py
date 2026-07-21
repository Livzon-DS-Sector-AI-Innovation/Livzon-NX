"""DataChannel schemas."""

import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class DataChannelBase(BaseModel):
    source_id: uuid.UUID
    code: str
    name: str
    list_url: str | None = None
    adapter_name: str | None = None
    enabled: bool = True


class DataChannelCreate(DataChannelBase):
    pass


class DataChannelUpdate(BaseModel):
    name: str | None = None
    list_url: str | None = None
    adapter_name: str | None = None
    enabled: bool | None = None


class DataChannelRead(DataChannelBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
