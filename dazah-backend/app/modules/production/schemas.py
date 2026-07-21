"""Production request and response schemas live here."""

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.platform.integrations.feishu.utils import (
    normalize_app_token,
    normalize_table_id,
)


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


class BatchStatus(str, Enum):
    """批次状态枚举"""

    DRAFT = "draft"  # 草稿
    RELEASED = "released"  # 已下达
    IN_PROGRESS = "in_progress"  # 执行中
    COMPLETED = "completed"  # 已完成
    CANCELLED = "cancelled"  # 已取消


class PlanStatus(str, Enum):
    """计划状态枚举"""

    DRAFT = "draft"  # 草稿
    APPROVED = "approved"  # 已批准
    EXECUTING = "executing"  # 执行中
    COMPLETED = "completed"  # 已完成


class ProcessSpecStatus(str, Enum):
    """工艺规程状态枚举"""

    DRAFT = "draft"  # 草稿
    APPROVED = "approved"  # 已批准
    EFFECTIVE = "effective"  # 已生效
    ARCHIVED = "archived"  # 已归档


class TaskStatus(str, Enum):
    """任务状态枚举"""

    PENDING = "pending"  # 待执行
    ASSIGNED = "assigned"  # 已分配
    IN_PROGRESS = "in_progress"  # 执行中
    COMPLETED = "completed"  # 已完成


class OperationType(str, Enum):
    """操作类型枚举"""

    MATERIAL_ADD = "material_add"  # 投料
    TRANSFER = "transfer"  # 转序
    SAMPLING = "sampling"  # 取样
    EQUIPMENT_CHECK = "equipment_check"  # 设备检查
    PARAMETER_RECORD = "parameter_record"  # 参数记录
    PACKAGING = "packaging"  # 包装


# ============ Batch Schemas ============


class BatchBase(BaseModel):
    """批次基础模式"""

    batch_no: str = Field(..., max_length=64, description="批次号")
    product_code: str = Field(..., max_length=64, description="产品编码")
    product_name: str | None = Field(None, max_length=255, description="产品名称")
    specification: str | None = Field(None, max_length=100, description="规格")
    unit: str | None = Field(None, max_length=20, description="单位")
    planned_qty: float | None = Field(None, ge=0, description="计划数量")
    process_spec_id: uuid.UUID | None = Field(None, description="工艺规程ID")
    production_line: str | None = Field(None, max_length=100, description="生产线")
    notes: str | None = Field(None, description="备注")


class BatchCreate(BatchBase):
    """创建批次"""

    pass


class BatchUpdate(BaseModel):
    """更新批次"""

    batch_no: str | None = Field(None, max_length=64, description="批次号")
    product_code: str | None = Field(None, max_length=64, description="产品编码")
    product_name: str | None = Field(None, max_length=255, description="产品名称")
    specification: str | None = Field(None, max_length=100, description="规格")
    unit: str | None = Field(None, max_length=20, description="单位")
    planned_qty: float | None = Field(None, ge=0, description="计划数量")
    process_spec_id: uuid.UUID | None = Field(None, description="工艺规程ID")
    production_line: str | None = Field(None, max_length=100, description="生产线")
    start_time: datetime | None = Field(None, description="开始时间")
    end_time: datetime | None = Field(None, description="结束时间")
    status: BatchStatus | None = Field(None, description="状态")
    notes: str | None = Field(None, description="备注")


class BatchStatusUpdate(BaseModel):
    """更新批次状态"""

    status: BatchStatus = Field(..., description="新状态")


class BatchResponse(BatchBase):
    """批次响应"""

    id: uuid.UUID
    status: BatchStatus
    actual_qty: float | None = None
    input_qty: float | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BatchMaterialBase(BaseModel):
    """批次物料基础模式"""

    material_code: str = Field(..., max_length=64, description="物料编码")
    material_name: str | None = Field(None, max_length=255, description="物料名称")
    material_type: str | None = Field(None, max_length=50, description="物料类型")
    unit: str | None = Field(None, max_length=20, description="单位")
    planned_qty: float | None = Field(None, ge=0, description="计划用量")
    lot_no: str | None = Field(None, max_length=64, description="批号/批次")
    stage: str | None = Field(None, max_length=50, description="工序阶段")
    notes: str | None = Field(None, description="备注")


class BatchMaterialCreate(BatchMaterialBase):
    """创建批次物料"""

    batch_id: uuid.UUID


class BatchMaterialUpdate(BaseModel):
    """更新批次物料"""

    material_code: str | None = Field(None, max_length=64, description="物料编码")
    material_name: str | None = Field(None, max_length=255, description="物料名称")
    material_type: str | None = Field(None, max_length=50, description="物料类型")
    unit: str | None = Field(None, max_length=20, description="单位")
    planned_qty: float | None = Field(None, ge=0, description="计划用量")
    actual_qty: float | None = Field(None, ge=0, description="实际用量")
    lot_no: str | None = Field(None, max_length=64, description="批号/批次")
    stage: str | None = Field(None, max_length=50, description="工序阶段")
    notes: str | None = Field(None, description="备注")


class BatchMaterialResponse(BatchMaterialBase):
    """批次物料响应"""

    id: uuid.UUID
    batch_id: uuid.UUID
    actual_qty: float | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============ ProductionPlan Schemas ============


class ProductionPlanBase(BaseModel):
    """生产计划基础模式"""

    plan_no: str = Field(..., max_length=64, description="计划编号")
    plan_name: str | None = Field(None, max_length=255, description="计划名称")
    plan_type: str | None = Field(None, max_length=50, description="计划类型")
    plan_month: str | None = Field(None, max_length=7, description="计划月份")
    notes: str | None = Field(None, description="备注")


class ProductionPlanCreate(ProductionPlanBase):
    """创建生产计划"""

    pass


class ProductionPlanUpdate(BaseModel):
    """更新生产计划"""

    plan_no: str | None = Field(None, max_length=64, description="计划编号")
    plan_name: str | None = Field(None, max_length=255, description="计划名称")
    plan_type: str | None = Field(None, max_length=50, description="计划类型")
    plan_month: str | None = Field(None, max_length=7, description="计划月份")
    status: PlanStatus | None = Field(None, description="状态")
    notes: str | None = Field(None, description="备注")


class ProductionPlanResponse(ProductionPlanBase):
    """生产计划响应"""

    id: uuid.UUID
    status: PlanStatus
    total_batches: int | None = None
    completed_batches: int | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============ ProductionExecutionPlan Schemas ============


class ProductionExecutionPlanBase(BaseModel):
    """车间日生产执行计划台账。"""

    workshop: str | None = Field(None, max_length=64, description="车间")
    product_name: str = Field(
        ..., min_length=1, max_length=128, description="产品名称"
    )
    plan_date: date | None = Field(None, description="计划日期")
    unit: str | None = Field(None, max_length=32, description="单位")
    planned_yield: float | None = Field(None, ge=0, description="计划产量")
    actual_completion: float | None = Field(None, ge=0, description="实际完成")
    completion_rate: float | None = Field(None, ge=0, description="完成率(%)")
    safety_status: str | None = Field(None, max_length=128, description="安环情况")
    quality_status: str | None = Field(None, max_length=128, description="质量情况")
    remarks: str | None = Field(None, description="备注")
    source: str = Field("manual", min_length=1, max_length=32, description="数据来源")
    source_record_id: str | None = Field(
        None, max_length=128, description="来源系统记录标识"
    )


class ProductionExecutionPlanCreate(ProductionExecutionPlanBase):
    """创建车间日生产执行计划。"""


class ProductionExecutionPlanUpdate(BaseModel):
    """更新车间日生产执行计划。"""

    workshop: str | None = Field(None, max_length=64)
    product_name: str | None = Field(None, min_length=1, max_length=128)
    plan_date: date | None = None
    unit: str | None = Field(None, max_length=32)
    planned_yield: float | None = Field(None, ge=0)
    actual_completion: float | None = Field(None, ge=0)
    completion_rate: float | None = Field(None, ge=0)
    safety_status: str | None = Field(None, max_length=128)
    quality_status: str | None = Field(None, max_length=128)
    remarks: str | None = None


class ProductionExecutionPlanResponse(ProductionExecutionPlanBase):
    """车间日生产执行计划响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ============ PlanTask Schemas ============


class PlanTaskBase(BaseModel):
    """计划任务基础模式"""

    product_code: str = Field(..., max_length=64, description="产品编码")
    product_name: str | None = Field(None, max_length=255, description="产品名称")
    batch_qty: int | None = Field(None, ge=0, description="批次数量")
    assigned_to: uuid.UUID | None = Field(None, description="负责人")
    due_date: datetime | None = Field(None, description="计划完成日期")
    notes: str | None = Field(None, description="备注")


class PlanTaskCreate(PlanTaskBase):
    """创建计划任务"""

    plan_id: uuid.UUID


class PlanTaskUpdate(BaseModel):
    """更新计划任务"""

    product_code: str | None = Field(None, max_length=64, description="产品编码")
    product_name: str | None = Field(None, max_length=255, description="产品名称")
    batch_qty: int | None = Field(None, ge=0, description="批次数量")
    assigned_to: uuid.UUID | None = Field(None, description="负责人")
    assigned_to_name: str | None = Field(None, max_length=100, description="负责人姓名")
    due_date: datetime | None = Field(None, description="计划完成日期")
    status: TaskStatus | None = Field(None, description="状态")
    notes: str | None = Field(None, description="备注")


class PlanTaskResponse(PlanTaskBase):
    """计划任务响应"""

    id: uuid.UUID
    plan_id: uuid.UUID
    assigned_to_name: str | None = None
    status: TaskStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============ SalesPlanDetail Schemas ============


class SalesPlanDetailBase(BaseModel):
    """销售执行明细基础模式。"""

    product_name: str = Field(..., min_length=1, max_length=128, description="产品名称")
    unit: str | None = Field(None, max_length=32, description="单位")
    last_month_delivered_uninvoiced: float | None = Field(
        None, description="上月已发货未开票"
    )
    current_year_delivered: float | None = Field(None, description="当年当月发货量")
    month_planned_delivery: float | None = Field(None, description="本月计划发货量")
    month_delivered_qty: float | None = Field(None, description="本月已发货量")
    undelivered_qty: float | None = Field(None, description="未发货量")
    month_planned_invoice: float | None = Field(None, description="本月预计开票量")
    invoiced_qty: float | None = Field(None, description="已开票量")
    delivery_completion_rate: float | None = Field(
        None, description="本月发货完成率(%)"
    )
    last_month_end_inventory: float | None = Field(None, description="上月底库存")
    month_planned_capacity: float | None = Field(None, description="本月预计产能")
    month_end_inventory: float | None = Field(None, description="本月底库存")
    remarks: str | None = Field(None, description="备注")
    source: str = Field("manual", min_length=1, max_length=32, description="数据来源")
    source_record_id: str | None = Field(
        None, max_length=128, description="来源系统记录标识"
    )


class SalesPlanDetailCreate(SalesPlanDetailBase):
    """创建销售执行明细。"""


class SalesPlanDetailUpdate(BaseModel):
    """更新销售执行明细。"""

    product_name: str | None = Field(None, min_length=1, max_length=128)
    unit: str | None = Field(None, max_length=32)
    last_month_delivered_uninvoiced: float | None = None
    current_year_delivered: float | None = None
    month_planned_delivery: float | None = None
    month_delivered_qty: float | None = None
    undelivered_qty: float | None = None
    month_planned_invoice: float | None = None
    invoiced_qty: float | None = None
    delivery_completion_rate: float | None = None
    last_month_end_inventory: float | None = None
    month_planned_capacity: float | None = None
    month_end_inventory: float | None = None
    remarks: str | None = None


class SalesPlanDetailResponse(SalesPlanDetailBase):
    """销售执行明细响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ProductionApiResponse[ResponseData](BaseModel):
    """生产模块带类型数据响应，用于 OpenAPI 与前端类型同步。"""

    code: int = 200
    message: str = "success"
    data: ResponseData | None = None
    meta: dict[str, Any] | None = None


# ============ ProcessSpec Schemas ============


class ProcessSpecBase(BaseModel):
    """工艺规程基础模式"""

    spec_code: str = Field(..., max_length=64, description="规程编号")
    spec_name: str | None = Field(None, max_length=255, description="规程名称")
    product_code: str = Field(..., max_length=64, description="产品编码")
    product_name: str | None = Field(None, max_length=255, description="产品名称")
    version: str = Field("1.0", max_length=20, description="版本号")
    effective_date: datetime | None = Field(None, description="生效日期")
    supersedes_version: str | None = Field(None, max_length=20, description="替代版本")
    notes: str | None = Field(None, description="备注")


class ProcessSpecCreate(ProcessSpecBase):
    """创建工艺规程"""

    pass


class ProcessSpecUpdate(BaseModel):
    """更新工艺规程"""

    spec_code: str | None = Field(None, max_length=64, description="规程编号")
    spec_name: str | None = Field(None, max_length=255, description="规程名称")
    product_code: str | None = Field(None, max_length=64, description="产品编码")
    product_name: str | None = Field(None, max_length=255, description="产品名称")
    version: str | None = Field(None, max_length=20, description="版本号")
    effective_date: datetime | None = Field(None, description="生效日期")
    status: ProcessSpecStatus | None = Field(None, description="状态")
    approved_by: uuid.UUID | None = Field(None, description="批准人")
    approved_by_name: str | None = Field(None, max_length=100, description="批准人姓名")
    supersedes_version: str | None = Field(None, max_length=20, description="替代版本")
    notes: str | None = Field(None, description="备注")


class ProcessSpecResponse(ProcessSpecBase):
    """工艺规程响应"""

    id: uuid.UUID
    status: ProcessSpecStatus
    approved_by: uuid.UUID | None = None
    approved_by_name: str | None = None
    approved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============ ProcessStep Schemas ============


class ProcessStepBase(BaseModel):
    """工艺步骤基础模式"""

    step_no: int = Field(..., ge=1, description="步骤序号")
    step_name: str = Field(..., max_length=255, description="步骤名称")
    description: str | None = Field(None, description="步骤描述")
    equipment_type: str | None = Field(None, max_length=100, description="设备类型")
    equipment_spec: str | None = Field(None, max_length=255, description="设备规格")
    duration_minutes: int | None = Field(None, ge=0, description="持续时间(分钟)")
    sequence_order: int | None = Field(None, description="排序顺序")
    notes: str | None = Field(None, description="备注")


class ProcessStepCreate(ProcessStepBase):
    """创建工艺步骤"""

    spec_id: uuid.UUID


class ProcessStepUpdate(BaseModel):
    """更新工艺步骤"""

    step_no: int | None = Field(None, ge=1, description="步骤序号")
    step_name: str | None = Field(None, max_length=255, description="步骤名称")
    description: str | None = Field(None, description="步骤描述")
    equipment_type: str | None = Field(None, max_length=100, description="设备类型")
    equipment_spec: str | None = Field(None, max_length=255, description="设备规格")
    duration_minutes: int | None = Field(None, ge=0, description="持续时间(分钟)")
    sequence_order: int | None = Field(None, description="排序顺序")
    notes: str | None = Field(None, description="备注")


class ProcessStepResponse(ProcessStepBase):
    """工艺步骤响应"""

    id: uuid.UUID
    spec_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============ ProcessParameter Schemas ============


class ProcessParameterBase(BaseModel):
    """工艺参数基础模式"""

    param_name: str = Field(..., max_length=255, description="参数名称")
    param_code: str | None = Field(None, max_length=64, description="参数编码")
    unit: str | None = Field(None, max_length=20, description="单位")
    min_value: float | None = Field(None, description="最小值")
    max_value: float | None = Field(None, description="最大值")
    target_value: float | None = Field(None, description="目标值")
    is_critical: bool = Field(False, description="是否关键参数")
    data_type: str | None = Field(None, max_length=20, description="数据类型")
    notes: str | None = Field(None, description="备注")


class ProcessParameterCreate(ProcessParameterBase):
    """创建工艺参数"""

    step_id: uuid.UUID


class ProcessParameterUpdate(BaseModel):
    """更新工艺参数"""

    param_name: str | None = Field(None, max_length=255, description="参数名称")
    param_code: str | None = Field(None, max_length=64, description="参数编码")
    unit: str | None = Field(None, max_length=20, description="单位")
    min_value: float | None = Field(None, description="最小值")
    max_value: float | None = Field(None, description="最大值")
    target_value: float | None = Field(None, description="目标值")
    is_critical: bool | None = Field(None, description="是否关键参数")
    data_type: str | None = Field(None, max_length=20, description="数据类型")
    notes: str | None = Field(None, description="备注")


class ProcessParameterResponse(ProcessParameterBase):
    """工艺参数响应"""

    id: uuid.UUID
    step_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============ ProductionRecord Schemas ============


class ProductionRecordBase(BaseModel):
    """生产记录基础模式"""

    record_no: str = Field(..., max_length=64, description="记录编号")
    step_no: int | None = Field(None, description="步骤序号")
    step_name: str | None = Field(None, max_length=255, description="步骤名称")
    operation_type: OperationType = Field(..., description="操作类型")
    parameters: str | None = Field(None, description="参数JSON")
    result: str | None = Field(None, description="操作结果")
    remarks: str | None = Field(None, description="备注")


class ProductionRecordCreate(ProductionRecordBase):
    """创建生产记录"""

    batch_id: uuid.UUID


class ProductionRecordUpdate(BaseModel):
    """更新生产记录"""

    step_no: int | None = Field(None, description="步骤序号")
    step_name: str | None = Field(None, max_length=255, description="步骤名称")
    operation_type: OperationType | None = Field(None, description="操作类型")
    parameters: str | None = Field(None, description="参数JSON")
    result: str | None = Field(None, description="操作结果")
    remarks: str | None = Field(None, description="备注")


class ProductionRecordResponse(ProductionRecordBase):
    """生产记录响应"""

    id: uuid.UUID
    batch_id: uuid.UUID
    operator: uuid.UUID | None = None
    operator_name: str | None = None
    operation_time: datetime
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============ MaterialBalance Schemas ============


class MaterialBalanceBase(BaseModel):
    """物料平衡基础模式"""

    input_qty: float | None = Field(None, ge=0, description="投入总量")
    output_qty: float | None = Field(None, ge=0, description="产出总量")
    loss_qty: float | None = Field(None, description="损耗总量")
    balance_rate: float | None = Field(None, ge=0, le=100, description="平衡率(%)")
    min_balance_rate: float = Field(95.0, ge=0, le=100, description="最低平衡率(%)")
    notes: str | None = Field(None, description="备注")


class MaterialBalanceCreate(MaterialBalanceBase):
    """创建物料平衡"""

    batch_id: uuid.UUID


class MaterialBalanceUpdate(BaseModel):
    """更新物料平衡"""

    input_qty: float | None = Field(None, ge=0, description="投入总量")
    output_qty: float | None = Field(None, ge=0, description="产出总量")
    loss_qty: float | None = Field(None, description="损耗总量")
    balance_rate: float | None = Field(None, ge=0, le=100, description="平衡率(%)")
    min_balance_rate: float | None = Field(None, ge=0, le=100, description="最低平衡率(%)")
    notes: str | None = Field(None, description="备注")


class MaterialBalanceResponse(MaterialBalanceBase):
    """物料平衡响应"""

    id: uuid.UUID
    batch_id: uuid.UUID
    is_balanced: bool
    deviation_rate: float | None = None
    calculated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MaterialBalanceCalculate(BaseModel):
    """物料平衡计算请求"""

    batch_id: uuid.UUID = Field(..., description="批次ID")
    min_balance_rate: float = Field(95.0, ge=0, le=100, description="最低平衡率(%)")


# ============ Feishu Config Schemas ============


class ProductionFeishuConfigBase(BaseModel):
    """生产飞书配置基础模式"""

    config_name: str = Field(default="生产飞书配置", max_length=128, description="配置名称")
    app_id: str = Field(..., max_length=128, description="飞书应用 App ID")
    bitable_app_token: str = Field(default="", max_length=512, description="兼容旧同步的多维表格 App Token")
    table_id: str | None = Field(None, max_length=512, description="默认多维表格数据表 Table ID")
    is_active: bool = Field(True, description="是否启用")
    remark: str | None = Field(None, description="备注")
    timezone: str = Field(default="Asia/Shanghai", max_length=64, description="同步时区")
    daily_sync_time: str = Field(
        default="02:00",
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
        description="每日同步时间",
    )

    @field_validator("config_name", "app_id", mode="before")
    @classmethod
    def normalize_required_text(cls, value: str | None) -> str | None:
        return _clean_text(value)

    @field_validator("bitable_app_token", mode="before")
    @classmethod
    def normalize_bitable_app_token(cls, value: str | None) -> str | None:
        return normalize_app_token(value)

    @field_validator("table_id", mode="before")
    @classmethod
    def normalize_bitable_table_id(cls, value: str | None) -> str | None:
        return normalize_table_id(value)


class ProductionFeishuConfigUpsert(ProductionFeishuConfigBase):
    """保存生产飞书配置"""

    id: uuid.UUID | None = Field(default=None, description="配置ID，留空则新增")
    app_secret: str | None = Field(default=None, max_length=500, description="飞书应用 App Secret")

    @field_validator("app_secret", mode="before")
    @classmethod
    def normalize_app_secret(cls, value: str | None) -> str | None:
        return _clean_text(value)


class ProductionFeishuConfigResponse(ProductionFeishuConfigBase):
    """生产飞书配置响应"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID | None = None
    app_secret_configured: bool = False
    app_secret_masked: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("config_name", "app_id", mode="before")
    @classmethod
    def normalize_required_text(cls, value: str | None) -> str:
        return value or ""

    @field_validator("bitable_app_token", mode="before")
    @classmethod
    def normalize_bitable_app_token(cls, value: str | None) -> str:
        return value or ""


class ProductionFeishuSyncBindingBase(BaseModel):
    """生产飞书同步绑定基础模式。"""

    config_id: uuid.UUID = Field(..., description="生产飞书配置 ID")
    binding_name: str = Field(..., min_length=1, max_length=128, description="绑定名称")
    sync_target: str = Field(..., min_length=1, max_length=64, description="同步业务目标")
    product_name: str | None = Field(None, max_length=128, description="适用产品")
    workshop_code: str | None = Field(None, max_length=64, description="适用车间或生产线编码")
    table_id: str = Field(..., max_length=512, description="飞书多维表格数据表 Table ID")
    field_mapping: dict[str, str] = Field(
        default_factory=dict, description="平台字段到飞书字段的映射"
    )
    is_active: bool = Field(False, description="是否允许进入同步队列")
    remark: str | None = Field(None, description="备注")

    @field_validator(
        "binding_name", "sync_target", "product_name", "workshop_code", "remark", mode="before"
    )
    @classmethod
    def normalize_binding_text(cls, value: str | None) -> str | None:
        return _clean_text(value)

    @field_validator("table_id", mode="before")
    @classmethod
    def normalize_binding_table_id(cls, value: str | None) -> str | None:
        return normalize_table_id(value)


class ProductionFeishuSyncBindingCreate(ProductionFeishuSyncBindingBase):
    """创建生产飞书同步绑定。"""


class ProductionFeishuSyncBindingUpdate(BaseModel):
    """更新生产飞书同步绑定。"""

    config_id: uuid.UUID | None = None
    binding_name: str | None = Field(None, min_length=1, max_length=128)
    sync_target: str | None = Field(None, min_length=1, max_length=64)
    product_name: str | None = Field(None, max_length=128)
    workshop_code: str | None = Field(None, max_length=64)
    table_id: str | None = Field(None, max_length=512)
    field_mapping: dict[str, str] | None = None
    is_active: bool | None = None
    remark: str | None = None

    @field_validator(
        "binding_name", "sync_target", "product_name", "workshop_code", "remark", mode="before"
    )
    @classmethod
    def normalize_optional_binding_text(cls, value: str | None) -> str | None:
        return _clean_text(value)

    @field_validator("table_id", mode="before")
    @classmethod
    def normalize_optional_binding_table_id(cls, value: str | None) -> str | None:
        return normalize_table_id(value)


class ProductionFeishuSyncBindingResponse(ProductionFeishuSyncBindingBase):
    """生产飞书同步绑定响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    last_status: str
    last_run_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class ProductionFeishuSyncExecuteRequest(BaseModel):
    """执行或预览飞书同步请求。"""

    dry_run: bool = Field(True, description="仅预览和校验，不写入业务表")
    idempotency_key: str | None = Field(
        None, min_length=1, max_length=128, description="调用方幂等标识"
    )

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def normalize_idempotency_key(cls, value: str | None) -> str | None:
        return _clean_text(value)


class ProductionFeishuSyncRunResponse(BaseModel):
    """生产飞书同步运行记录响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    binding_id: uuid.UUID
    run_mode: str
    status: str
    idempotency_key: str
    started_at: datetime
    finished_at: datetime | None = None
    created_count: int
    updated_count: int
    skipped_count: int
    failed_count: int
    error_summary: str | None = None
    created_at: datetime
    updated_at: datetime


class ProductionFeishuConnectivityStep(BaseModel):
    """生产飞书连通性步骤"""

    name: str
    status: str
    message: str


class ProductionFeishuConnectivityResult(BaseModel):
    """生产飞书连通性结果"""

    ok: bool
    steps: list[ProductionFeishuConnectivityStep]


class ProductionFeishuFieldPreview(BaseModel):
    """飞书多维表格字段预览"""

    field_id: str
    field_name: str
    type: int | None = None
    property: dict[str, Any] | None = None


class ProductionFeishuTableItem(BaseModel):
    """飞书多维表格数据表"""

    table_id: str
    name: str
    revision: int | None = None


class ProductionFeishuTableListResponse(BaseModel):
    """生产飞书多维表格数据表列表"""

    app_token: str
    tables: list[ProductionFeishuTableItem]
    total: int | None = None


class ProductionFeishuRecordPreview(BaseModel):
    """飞书多维表格记录预览"""

    record_id: str
    fields: dict[str, Any]
    created_time: int | None = None
    last_modified_time: int | None = None


class ProductionFeishuTablePreviewResponse(BaseModel):
    """生产飞书多维表格预览响应"""

    app_token: str
    table_id: str
    fields: list[ProductionFeishuFieldPreview]
    records: list[ProductionFeishuRecordPreview]
    page_size: int = 20
    has_more: bool = False
    page_token: str | None = None
    total: int | None = None
