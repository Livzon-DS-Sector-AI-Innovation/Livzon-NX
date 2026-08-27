"""Lab instrument schemas."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LabInstrumentBase(BaseModel):
    name: str = Field(..., description="仪器名称")
    model: str | None = Field(default=None, description="型号")
    serial_no: str | None = Field(default=None, description="序列号")
    manufacturer: str | None = Field(default=None, description="生产厂家")
    department: str | None = Field(default=None, description="所属部门")
    location: str | None = Field(default=None, description="放置位置")
    calibration_date: date | None = Field(default=None, description="最近校准日期")
    next_calibration_date: date | None = Field(default=None, description="下次校准日期")
    status: str = Field(
        default="normal",
        description="状态：normal/maintenance/calibration_due/scrapped",
    )
    remark: str | None = Field(default=None, description="备注")


class CreateLabInstrumentRequest(LabInstrumentBase):
    pass


class UpdateLabInstrumentRequest(BaseModel):
    name: str | None = None
    model: str | None = None
    serial_no: str | None = None
    manufacturer: str | None = None
    department: str | None = None
    location: str | None = None
    calibration_date: date | None = None
    next_calibration_date: date | None = None
    status: str | None = None
    remark: str | None = None


class LabInstrumentOut(LabInstrumentBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
