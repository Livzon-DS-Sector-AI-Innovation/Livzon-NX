"""班组交接确认 Pydantic schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ShiftHandoverCreate(BaseModel):
    position: str = Field(..., description="岗位")
    workshop: str = Field(..., description="车间")
    shift: str = Field(..., description="班次")
    handover_time: datetime = Field(..., description="交接时间")
    handover_from: str = Field(..., description="交班人")
    handover_to: str = Field(..., description="接班人")
    production_status: Optional[str] = Field(None, description="生产工艺运行情况")
    equipment_status: Optional[str] = Field(None, description="设备运行情况")
    equipment_inspection: Optional[str] = Field(None, description="设备巡检情况")
    tools_handover: Optional[str] = Field(None, description="工、器具移交")
    fire_emergency: Optional[str] = Field(None, description="消防、应急器材情况")
    ppe_status: Optional[str] = Field(None, description="人员劳动防护用品穿戴")
    remarks: Optional[str] = Field(None, description="备注")


class ShiftHandoverUpdate(BaseModel):
    position: Optional[str] = Field(None, description="岗位")
    workshop: Optional[str] = Field(None, description="车间")
    shift: Optional[str] = Field(None, description="班次")
    handover_time: Optional[datetime] = Field(None, description="交接时间")
    handover_from: Optional[str] = Field(None, description="交班人")
    handover_to: Optional[str] = Field(None, description="接班人")
    production_status: Optional[str] = Field(None, description="生产工艺运行情况")
    equipment_status: Optional[str] = Field(None, description="设备运行情况")
    equipment_inspection: Optional[str] = Field(None, description="设备巡检情况")
    tools_handover: Optional[str] = Field(None, description="工、器具移交")
    fire_emergency: Optional[str] = Field(None, description="消防、应急器材情况")
    ppe_status: Optional[str] = Field(None, description="人员劳动防护用品穿戴")
    remarks: Optional[str] = Field(None, description="备注")


class ShiftHandoverResponse(BaseModel):
    id: UUID
    position: str
    workshop: str
    shift: str
    handover_time: datetime
    handover_from: str
    handover_to: str
    production_status: Optional[str] = None
    equipment_status: Optional[str] = None
    equipment_inspection: Optional[str] = None
    tools_handover: Optional[str] = None
    fire_emergency: Optional[str] = None
    ppe_status: Optional[str] = None
    remarks: Optional[str] = None
    status: str
    confirmed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
