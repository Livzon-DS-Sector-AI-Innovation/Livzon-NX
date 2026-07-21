"""生产工序执行与批次进度 API schemas。"""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.production.process_catalog import PROCESS_STEP_BY_CODE


class ProcessExecutionRecordBase(BaseModel):
    batch_id: uuid.UUID | None = None
    batch_no: str = Field(..., min_length=1, max_length=128)
    workshop_code: str = Field("203", min_length=1, max_length=32)
    process_code: str = Field(..., min_length=1, max_length=32)
    status: Literal["draft", "in_progress", "completed"] = "draft"
    recorded_at: datetime
    data: dict[str, Any] = Field(default_factory=dict)
    source: str = Field("manual", min_length=1, max_length=32)
    source_record_id: str | None = Field(None, max_length=128)
    remarks: str | None = None

    @field_validator(
        "batch_no", "workshop_code", "process_code", "source", mode="before"
    )
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        cleaned = str(value).strip()
        if not cleaned:
            raise ValueError("不能为空")
        return cleaned

    @field_validator("process_code")
    @classmethod
    def validate_process_code(cls, value: str) -> str:
        if value not in PROCESS_STEP_BY_CODE:
            raise ValueError("不支持的工序编码")
        return value


class ProcessExecutionRecordCreate(ProcessExecutionRecordBase):
    pass


class ProcessExecutionRecordUpdate(BaseModel):
    status: Literal["draft", "in_progress", "completed"] | None = None
    recorded_at: datetime | None = None
    data: dict[str, Any] | None = None
    remarks: str | None = None


class ProcessExecutionRecordResponse(ProcessExecutionRecordBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    step_sequence: int
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ProcessFieldDefinition(BaseModel):
    name: str
    label: str
    kind: Literal["text", "textarea", "number", "date", "boolean", "select"]
    required: bool = False


class ProcessDefinition(BaseModel):
    code: str
    label: str
    short: str
    sequence: int
    fields: list[ProcessFieldDefinition]


class ProcessStepProgress(BaseModel):
    code: str
    label: str
    short: str
    sequence: int
    has_record: bool
    completed: bool
    record_count: int


class BatchProgressItem(BaseModel):
    batch_no: str
    workshop_code: str
    completed: int
    total: int
    progress_percent: float
    steps: list[ProcessStepProgress]


class ProcessBottleneck(BaseModel):
    process_code: str
    process_label: str
    stuck_count: int
    stuck_batches: list[str]
    has_more: bool


class BatchProgressSummary(BaseModel):
    total_batches: int
    in_progress: int
    completed: int
    today_pack_count: int
    monthly_output_kg: float
    bottlenecks: list[ProcessBottleneck]


class BatchProgressResponse(BaseModel):
    batches: list[BatchProgressItem]
    steps: list[dict[str, Any]]
    summary: BatchProgressSummary


class BatchProfileResponse(BaseModel):
    batch_no: str
    batch: dict[str, Any] | None
    progress: BatchProgressItem | None
    records: dict[str, list[ProcessExecutionRecordResponse]]
