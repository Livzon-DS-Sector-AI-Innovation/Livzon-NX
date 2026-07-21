"""Calibration schemas."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

# ==================== 校准管理 ====================
CalibrationType = Literal["内部校准", "外部检定"]
CalibrationResult = Literal["合格", "不合格"]
CalibrationPlanStatus = Literal["启用", "停用"]


class CalibrationPlanCreate(BaseModel):
    """创建校准计划请求"""

    equipment_id: uuid.UUID = Field(..., description="设备ID")
    calibration_type: CalibrationType = Field(..., description="校准类型")
    cycle_months: int = Field(..., ge=1, description="校准周期（月）")
    last_calibration_date: date | None = Field(default=None, description="上次校准日期")
    responsible_person_id: uuid.UUID | None = Field(
        default=None, description="负责人ID"
    )
    remark: str | None = Field(default=None, description="备注")


class CalibrationPlanUpdate(BaseModel):
    """更新校准计划请求"""

    calibration_type: CalibrationType | None = Field(
        default=None, description="校准类型"
    )
    cycle_months: int | None = Field(default=None, ge=1, description="校准周期（月）")
    last_calibration_date: date | None = Field(default=None, description="上次校准日期")
    responsible_person_id: uuid.UUID | None = Field(
        default=None, description="负责人ID"
    )
    status: CalibrationPlanStatus | None = Field(default=None, description="状态")
    remark: str | None = Field(default=None, description="备注")


class CalibrationPlanResponse(BaseModel):
    """校准计划响应"""

    id: uuid.UUID
    equipment_id: uuid.UUID
    calibration_type: CalibrationType
    cycle_months: int
    last_calibration_date: date | None
    next_calibration_date: date | None
    responsible_person_id: uuid.UUID | None
    status: CalibrationPlanStatus
    remark: str | None
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None
    updated_by: uuid.UUID | None

    model_config = {"from_attributes": True}


class CalibrationRecordCreate(BaseModel):
    """创建校准记录请求"""

    calibration_plan_id: uuid.UUID = Field(..., description="校准计划ID")
    calibration_date: date = Field(..., description="校准日期")
    calibration_type: CalibrationType = Field(..., description="校准类型")
    result: CalibrationResult = Field(..., description="校准结果")
    certificate_no: str | None = Field(
        default=None, max_length=100, description="检定证书编号"
    )
    calibrated_by: str | None = Field(
        default=None, max_length=200, description="校准单位/人员"
    )
    remark: str | None = Field(default=None, description="备注")


class CalibrationRecordResponse(BaseModel):
    """校准记录响应"""

    id: uuid.UUID
    calibration_plan_id: uuid.UUID
    equipment_id: uuid.UUID
    calibration_date: date
    calibration_type: CalibrationType
    result: CalibrationResult
    certificate_no: str | None
    calibrated_by: str | None
    next_due_date: date
    remark: str | None
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None
    updated_by: uuid.UUID | None

    model_config = {"from_attributes": True}
