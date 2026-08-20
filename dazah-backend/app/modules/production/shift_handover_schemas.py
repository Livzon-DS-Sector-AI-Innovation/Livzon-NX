"""班组交接确认 Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ShiftHandoverCreate(BaseModel):
    position: str = Field(..., description="岗位")
    workshop: str = Field(..., description="车间")
    shift: str = Field(..., description="班次")
    handover_time: datetime = Field(..., description="交接时间")
    handover_from: str = Field(..., description="交班人")
    handover_to: str = Field(..., description="接班人")
    production_status: str | None = Field(None, description="生产工艺运行情况")
    equipment_status: str | None = Field(None, description="设备运行情况")
    equipment_inspection: str | None = Field(None, description="设备巡检情况")
    tools_handover: str | None = Field(None, description="工、器具移交")
    fire_emergency: str | None = Field(None, description="消防、应急器材情况")
    ppe_status: str | None = Field(None, description="人员劳动防护用品穿戴")
    remarks: str | None = Field(None, description="备注")


class ShiftHandoverUpdate(BaseModel):
    position: str | None = Field(None, description="岗位")
    workshop: str | None = Field(None, description="车间")
    shift: str | None = Field(None, description="班次")
    handover_time: datetime | None = Field(None, description="交接时间")
    handover_from: str | None = Field(None, description="交班人")
    handover_to: str | None = Field(None, description="接班人")
    production_status: str | None = Field(None, description="生产工艺运行情况")
    equipment_status: str | None = Field(None, description="设备运行情况")
    equipment_inspection: str | None = Field(None, description="设备巡检情况")
    tools_handover: str | None = Field(None, description="工、器具移交")
    fire_emergency: str | None = Field(None, description="消防、应急器材情况")
    ppe_status: str | None = Field(None, description="人员劳动防护用品穿戴")
    remarks: str | None = Field(None, description="备注")


class ShiftHandoverResponse(BaseModel):
    id: UUID
    position: str
    workshop: str
    shift: str
    handover_time: datetime
    handover_from: str
    handover_to: str
    production_status: str | None = None
    equipment_status: str | None = None
    equipment_inspection: str | None = None
    tools_handover: str | None = None
    fire_emergency: str | None = None
    ppe_status: str | None = None
    remarks: str | None = None
    status: str
    confirmed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
