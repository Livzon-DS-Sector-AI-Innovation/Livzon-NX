"""非密事件与运行偏差 Pydantic schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class NCECreate(BaseModel):
    event_time: datetime = Field(..., description="发生时间")
    restore_time: Optional[datetime] = Field(None, description="恢复正常时间")
    impact_duration: Optional[str] = Field(None, description="影响时间")
    event_type: str = Field(..., description="事件类型")
    workshop: str = Field(..., description="车间")
    description: Optional[str] = Field(None, description="事件描述")
    impact_scope: Optional[str] = Field(None, description="影响范围")
    action_taken: Optional[str] = Field(None, description="处理措施")
    remarks: Optional[str] = Field(None, description="备注")


class NCEUpdate(BaseModel):
    event_time: Optional[datetime] = Field(None, description="发生时间")
    restore_time: Optional[datetime] = Field(None, description="恢复正常时间")
    impact_duration: Optional[str] = Field(None, description="影响时间")
    event_type: Optional[str] = Field(None, description="事件类型")
    workshop: Optional[str] = Field(None, description="车间")
    description: Optional[str] = Field(None, description="事件描述")
    impact_scope: Optional[str] = Field(None, description="影响范围")
    action_taken: Optional[str] = Field(None, description="处理措施")
    remarks: Optional[str] = Field(None, description="备注")


class NCEResponse(BaseModel):
    id: UUID
    event_time: datetime
    restore_time: Optional[datetime] = None
    impact_duration: Optional[str] = None
    event_type: str
    workshop: str
    description: Optional[str] = None
    impact_scope: Optional[str] = None
    action_taken: Optional[str] = None
    remarks: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
