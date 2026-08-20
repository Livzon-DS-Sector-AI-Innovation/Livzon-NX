"""生产日志与交接班 Pydantic schemas."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ── Create ──
class ShiftLogCreate(BaseModel):
    log_date: date = Field(..., description="日期")
    shift: str = Field(..., description="班次（morning/afternoon/night）")
    workshop: str = Field(..., description="车间")
    handover_from: str = Field(..., description="交班人")
    handover_to: str = Field(..., description="接班人")
    production_summary: str | None = Field(None, description="本班生产情况")
    equipment_status: str | None = Field(None, description="设备运行状况")
    abnormal_events: str | None = Field(None, description="异常情况")
    pending_tasks: str | None = Field(None, description="待办事项交接")
    remarks: str | None = Field(None, description="备注")


# ── Update ──
class ShiftLogUpdate(BaseModel):
    log_date: date | None = Field(None, description="日期")
    shift: str | None = Field(None, description="班次")
    workshop: str | None = Field(None, description="车间")
    handover_from: str | None = Field(None, description="交班人")
    handover_to: str | None = Field(None, description="接班人")
    production_summary: str | None = Field(None, description="本班生产情况")
    equipment_status: str | None = Field(None, description="设备运行状况")
    abnormal_events: str | None = Field(None, description="异常情况")
    pending_tasks: str | None = Field(None, description="待办事项交接")
    remarks: str | None = Field(None, description="备注")


# ── Response ──
class ShiftLogResponse(BaseModel):
    id: UUID
    log_date: date
    shift: str
    workshop: str
    handover_from: str
    handover_to: str
    production_summary: str | None = None
    equipment_status: str | None = None
    abnormal_events: str | None = None
    pending_tasks: str | None = None
    remarks: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
