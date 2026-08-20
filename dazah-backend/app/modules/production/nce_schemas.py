"""非密事件与运行偏差 Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class NCECreate(BaseModel):
    event_time: datetime = Field(..., description="发生时间")
    restore_time: datetime | None = Field(None, description="恢复正常时间")
    impact_duration: str | None = Field(None, description="影响时间")
    event_type: str = Field(..., description="事件类型")
    workshop: str = Field(..., description="车间")
    description: str | None = Field(None, description="事件描述")
    impact_scope: str | None = Field(None, description="影响范围")
    action_taken: str | None = Field(None, description="处理措施")
    remarks: str | None = Field(None, description="备注")


class NCEUpdate(BaseModel):
    event_time: datetime | None = Field(None, description="发生时间")
    restore_time: datetime | None = Field(None, description="恢复正常时间")
    impact_duration: str | None = Field(None, description="影响时间")
    event_type: str | None = Field(None, description="事件类型")
    workshop: str | None = Field(None, description="车间")
    description: str | None = Field(None, description="事件描述")
    impact_scope: str | None = Field(None, description="影响范围")
    action_taken: str | None = Field(None, description="处理措施")
    remarks: str | None = Field(None, description="备注")


class NCEResponse(BaseModel):
    id: UUID
    event_time: datetime
    restore_time: datetime | None = None
    impact_duration: str | None = None
    event_type: str
    workshop: str
    description: str | None = None
    impact_scope: str | None = None
    action_taken: str | None = None
    remarks: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
