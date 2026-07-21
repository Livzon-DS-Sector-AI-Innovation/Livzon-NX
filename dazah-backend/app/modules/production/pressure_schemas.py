"""Pressure differential inspection request/response schemas."""

import uuid
from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


# ─── Enums ───


AREA_OPTIONS = ["无菌区", "精洗区", "配液区", "走廊", "更衣室", "其他"]


class AreaType(str, Enum):
    STERILE = "无菌区"
    WASH = "精洗区"
    PREP = "配液区"
    CORRIDOR = "走廊"
    CHANGING = "更衣室"
    OTHER = "其他"


class InputType(str, Enum):
    MANUAL = "manual"
    OCR = "ocr"


class AuditStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class OcrTaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SUBMITTED = "submitted"


class DataSource(str, Enum):
    MANUAL = "manual"
    OCR = "ocr"


# ─── Dashboard ───


class DashboardStats(BaseModel):
    today_count: int = Field(0, description="今日记录数")
    pending_count: int = Field(0, description="待审核数")
    last_record_time: datetime | None = Field(None, description="最后记录时间")


# ─── PointMapping ───


class PointMappingBase(BaseModel):
    point_id: str = Field(..., max_length=50, description="位点编号")
    area: str = Field(..., max_length=50, description="区域")
    standard_pressure: int = Field(..., description="标准压差值 (Pa)")


class PointMappingCreate(PointMappingBase):
    pass


class PointMappingUpdate(BaseModel):
    area: str | None = Field(None, max_length=50)
    standard_pressure: int | None = None


class PointMappingResponse(PointMappingBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CheckUniqueResponse(BaseModel):
    exists: bool = Field(..., description="位点编号是否已存在")


# ─── PressureRecord ───


class PressureRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    point_id: str
    area: str
    pressure_value: int
    standard_pressure: int
    record_time: datetime
    input_type: str
    status: str
    reject_reason: str | None = None
    creator: str | None = None
    image_url: str | None = None
    remark: str | None = None
    batch_id: str | None = None
    time_slot: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CreateManualRecordRequest(BaseModel):
    record_time: datetime = Field(..., description="记录时间")
    point_id: str = Field(..., description="位点编号")
    pressure_value: int = Field(..., description="压差值")
    time_slot: str | None = Field(None, description="时段")
    remark: str | None = None


class BatchManualEntryRow(BaseModel):
    date: str = Field(..., description="日期 YYYY-MM-DD")
    values: dict[str, float | None] = Field(
        default_factory=dict,
        description="key=位点编号[::时段], value=压差值",
    )


class BatchManualEntryRequest(BaseModel):
    area: str = Field(..., description="区域")
    rows: list[BatchManualEntryRow] = Field(default_factory=list)
    time_slots: list[str] | None = Field(None, description="自定义时段列表")
    remark: str | None = None


class BatchManualEntryResponse(BaseModel):
    success_count: int = 0
    fail_count: int = 0
    batch_id: str = ""


# ─── OCR ───


class OcrResultRecord(BaseModel):
    point_id: str
    pressure_value: int
    record_time: str
    recorder: str
    time_slot: str | None = None


class OcrResultData(BaseModel):
    records: list[OcrResultRecord] = Field(default_factory=list)


class OcrTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    image_url: str
    result: dict | None = None
    error_message: str | None = None
    batch_id: str | None = None
    created_at: datetime | None = None


class CreateOcrTaskRequest(BaseModel):
    image_url: str = Field(..., description="图片地址")


class CreateOcrRecordRequest(BaseModel):
    records: list[dict] = Field(default_factory=list)
    image_url: str = Field(..., description="图片地址")
    task_id: str | None = None


class OcrSubmitResponse(BaseModel):
    success_count: int = 0
    fail_count: int = 0
    success: bool = True
    batch_id: str | None = None


class SubmitOcrTaskResultRequest(BaseModel):
    records: list[dict] = Field(default_factory=list)


# ─── Audit ───


class AuditRequest(BaseModel):
    status: str = Field(..., description="approved 或 rejected")
    reject_reason: str | None = None


class BatchAuditRequest(BaseModel):
    ids: list[uuid.UUID] = Field(default_factory=list)
    status: str = Field(..., description="approved 或 rejected")
    reject_reason: str | None = None


class BatchAuditResponse(BaseModel):
    success_count: int = 0
    fail_count: int = 0
    success: bool = True


class AuditStats(BaseModel):
    pending_count: int = 0
    today_approved_count: int = 0
    rejected_count: int = 0


# ─── Delete ───


class DeleteRecordsRequest(BaseModel):
    ids: list[uuid.UUID] = Field(default_factory=list)


class DeleteRecordsResponse(BaseModel):
    success_count: int = 0
    fail_count: int = 0
    success: bool = True


# ─── Merged View ───


class MergedPressureRow(BaseModel):
    point_id: str
    area: str
    date: str
    time_slot_values: dict[str, float | None] = Field(default_factory=dict)
    standard_pressure: int
    record_ids: list[uuid.UUID] = Field(default_factory=list)
    status: str = "pending"
    input_type: str = "manual"


class MergedPressureResponse(BaseModel):
    items: list[MergedPressureRow] = Field(default_factory=list)
    total: int = 0


class DeleteMergedRowRequest(BaseModel):
    point_id: str
    date: str


class BatchDeleteMergedRowsRequest(BaseModel):
    rows: list[DeleteMergedRowRequest] = Field(default_factory=list)


class UpdateMergedRowRequest(BaseModel):
    point_id: str
    date: str
    time_slot_values: dict[str, float | None] = Field(default_factory=dict)


class UpdateMergedRowResponse(BaseModel):
    success_count: int = 0
    success: bool = True


# ─── Export ───


class TemplateExportRow(BaseModel):
    date: str
    point_id: str
    standard_pressure: str
    values: dict[str, float | None] = Field(default_factory=dict)


class AreaExportData(BaseModel):
    area: str
    time_slots: list[str] = Field(default_factory=list)
    rows: list[TemplateExportRow] = Field(default_factory=list)


# ─── DataMaster ───


class DataMasterBase(BaseModel):
    record_date: date = Field(..., description="记录日期")
    material_name: str = Field(..., max_length=255, description="物料名称")
    spec_model: str = Field("", max_length=255, description="规格型号")
    quantity: float = Field(0, ge=0, description="数量")
    unit: str = Field("", max_length=50, description="单位")
    supplier: str = Field("", max_length=255, description="供应商")
    remark: str | None = None
    source: str = Field("manual", description="来源")


class DataMasterCreate(DataMasterBase):
    creator_name: str = Field("", description="创建人姓名")


class DataMasterUpdate(BaseModel):
    record_date: date | None = None
    material_name: str | None = None
    spec_model: str | None = None
    quantity: float | None = None
    unit: str | None = None
    supplier: str | None = None
    remark: str | None = None


class DataMasterResponse(DataMasterBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    creator_name: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class BatchCreateDataMasterRequest(BaseModel):
    items: list[DataMasterCreate] = Field(default_factory=list)


# ─── Notification ───


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    title: str
    message: str
    is_read: bool
    related_id: str | None = None
    related_type: str | None = None
    created_at: datetime | None = None


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse] = Field(default_factory=list)
    unread_count: int = 0
