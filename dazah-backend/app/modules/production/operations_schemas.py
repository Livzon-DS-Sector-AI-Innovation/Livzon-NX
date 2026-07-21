"""发酵、种子培养、事件与班次业务 Schema。"""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class AuditResponse(BaseModel):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FermentationCreate(BaseModel):
    batch_no: str = Field(min_length=1, max_length=64)
    product_name: str = Field(default="L-苯丙氨酸", max_length=100)
    fermenter: str = Field(min_length=1, max_length=64)
    entry_date: date
    discharge_date: date | None = None
    cycle_data: dict[str, Any] = Field(default_factory=dict)
    tank_yield: float | None = None
    status: str = "in_progress"
    remarks: str | None = None
    attachment: str | None = None
    source: str = "manual"
    source_record_id: str | None = None


class FermentationUpdate(BaseModel):
    batch_no: str | None = None
    product_name: str | None = None
    fermenter: str | None = None
    entry_date: date | None = None
    discharge_date: date | None = None
    cycle_data: dict[str, Any] | None = None
    tank_yield: float | None = None
    status: str | None = None
    remarks: str | None = None
    attachment: str | None = None


class FermentationResponse(AuditResponse, FermentationCreate):
    pass


class SeedCultureCreate(BaseModel):
    batch_no: str = Field(min_length=1, max_length=64)
    product_name: str = Field(default="", max_length=100)
    prepare_date: date | None = None
    materials: dict[str, Any] = Field(default_factory=dict)
    quality_data: dict[str, Any] = Field(default_factory=dict)
    operation_data: dict[str, Any] = Field(default_factory=dict)
    tank_yield: float | None = None
    status: str = "in_progress"
    remarks: str | None = None
    source: str = "manual"
    source_record_id: str | None = None


class SeedCultureUpdate(BaseModel):
    batch_no: str | None = None
    product_name: str | None = None
    prepare_date: date | None = None
    materials: dict[str, Any] | None = None
    quality_data: dict[str, Any] | None = None
    operation_data: dict[str, Any] | None = None
    tank_yield: float | None = None
    status: str | None = None
    remarks: str | None = None


class SeedCultureResponse(AuditResponse, SeedCultureCreate):
    pass


class NonConformingEventCreate(BaseModel):
    event_time: datetime
    restore_time: datetime | None = None
    impact_duration: str | None = None
    event_type: str = Field(min_length=1, max_length=32)
    workshop: str = Field(min_length=1, max_length=64)
    description: str | None = None
    impact_scope: str | None = None
    action_taken: str | None = None
    status: str = "open"
    related_batch_nos: list[str] = Field(default_factory=list)
    remarks: str | None = None


class NonConformingEventUpdate(BaseModel):
    event_time: datetime | None = None
    restore_time: datetime | None = None
    impact_duration: str | None = None
    event_type: str | None = None
    workshop: str | None = None
    description: str | None = None
    impact_scope: str | None = None
    action_taken: str | None = None
    status: str | None = None
    related_batch_nos: list[str] | None = None
    remarks: str | None = None


class NonConformingEventResponse(AuditResponse, NonConformingEventCreate):
    pass


class ShiftLogCreate(BaseModel):
    log_date: date
    shift: str = Field(pattern="^(morning|afternoon|night)$")
    workshop: str = Field(min_length=1, max_length=64)
    handover_from: str = Field(min_length=1, max_length=64)
    handover_to: str = Field(min_length=1, max_length=64)
    production_summary: str | None = None
    equipment_status: str | None = None
    abnormal_events: str | None = None
    pending_tasks: str | None = None
    remarks: str | None = None


class ShiftLogUpdate(BaseModel):
    log_date: date | None = None
    shift: str | None = Field(default=None, pattern="^(morning|afternoon|night)$")
    workshop: str | None = None
    handover_from: str | None = None
    handover_to: str | None = None
    production_summary: str | None = None
    equipment_status: str | None = None
    abnormal_events: str | None = None
    pending_tasks: str | None = None
    remarks: str | None = None


class ShiftLogResponse(AuditResponse, ShiftLogCreate):
    pass


class ShiftHandoverCreate(BaseModel):
    position: str = Field(min_length=1, max_length=64)
    workshop: str = Field(min_length=1, max_length=64)
    shift: str = Field(pattern="^(morning|afternoon|night)$")
    handover_time: datetime
    handover_from: str = Field(min_length=1, max_length=64)
    handover_to: str = Field(min_length=1, max_length=64)
    production_status: str | None = None
    equipment_status: str | None = None
    equipment_inspection: str | None = None
    tools_handover: str | None = None
    fire_emergency: str | None = None
    ppe_status: str | None = None
    remarks: str | None = None


class ShiftHandoverUpdate(BaseModel):
    position: str | None = None
    workshop: str | None = None
    shift: str | None = Field(default=None, pattern="^(morning|afternoon|night)$")
    handover_time: datetime | None = None
    handover_from: str | None = None
    handover_to: str | None = None
    production_status: str | None = None
    equipment_status: str | None = None
    equipment_inspection: str | None = None
    tools_handover: str | None = None
    fire_emergency: str | None = None
    ppe_status: str | None = None
    remarks: str | None = None


class ShiftHandoverResponse(AuditResponse, ShiftHandoverCreate):
    status: str
    confirmed_at: datetime | None = None
    confirmed_by: uuid.UUID | None = None
