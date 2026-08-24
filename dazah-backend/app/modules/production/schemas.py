"""Production request and response schemas live here."""

import uuid
from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class BatchStatus(StrEnum):
    """批次状态枚举"""

    DRAFT = "draft"  # 草稿
    RELEASED = "released"  # 已下达
    IN_PROGRESS = "in_progress"  # 执行中
    COMPLETED = "completed"  # 已完成
    CANCELLED = "cancelled"  # 已取消


class ProcessSpecStatus(StrEnum):
    """工艺规程状态枚举"""

    DRAFT = "draft"  # 草稿
    APPROVED = "approved"  # 已批准
    EFFECTIVE = "effective"  # 已生效
    ARCHIVED = "archived"  # 已归档


class OperationType(StrEnum):
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

    workshop: str | None = Field(None, max_length=64, description="车间")
    product_name: str = Field(..., max_length=128, description="产品")
    plan_date: date | None = Field(None, description="日期")
    planned_yield: float | None = Field(None, ge=0, description="计划产量")
    unit: str | None = Field(None, max_length=32, description="单位")
    actual_completion: float | None = Field(None, ge=0, description="实际完成")
    completion_rate: float | None = Field(None, ge=0, le=1, description="完成率")
    safety_status: str | None = Field(None, max_length=128, description="安环情况")
    quality_status: str | None = Field(None, max_length=128, description="质量情况")
    remarks: str | None = Field(None, description="备注")


class ProductionPlanCreate(ProductionPlanBase):
    """创建生产计划"""

    pass


class ProductionPlanUpdate(BaseModel):
    """更新生产计划"""

    workshop: str | None = Field(None, max_length=64, description="车间")
    product_name: str | None = Field(None, max_length=128, description="产品")
    plan_date: date | None = Field(None, description="日期")
    planned_yield: float | None = Field(None, ge=0, description="计划产量")
    unit: str | None = Field(None, max_length=32, description="单位")
    actual_completion: float | None = Field(None, ge=0, description="实际完成")
    completion_rate: float | None = Field(None, ge=0, le=1, description="完成率")
    safety_status: str | None = Field(None, max_length=128, description="安环情况")
    quality_status: str | None = Field(None, max_length=128, description="质量情况")
    remarks: str | None = Field(None, description="备注")


class ProductionPlanResponse(ProductionPlanBase):
    """生产计划响应"""

    id: uuid.UUID
    source: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============ SalesPlanDetail Schemas ============


class SalesPlanDetailBase(BaseModel):
    """销售计划明细基础模式"""

    product_name: str = Field(..., max_length=128, description="产品名称")
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
    delivery_completion_rate: float | None = Field(None, description="本月发货完成率")
    last_month_end_inventory: float | None = Field(None, description="上月底库存")
    month_planned_capacity: float | None = Field(None, description="本月预计产能")
    month_end_inventory: float | None = Field(None, description="本月底库存")
    remarks: str | None = Field(None, description="备注")


class SalesPlanDetailCreate(SalesPlanDetailBase):
    pass


class SalesPlanDetailUpdate(BaseModel):
    product_name: str | None = Field(None, max_length=128)
    unit: str | None = Field(None, max_length=32)
    last_month_delivered_uninvoiced: float | None = Field(None)
    current_year_delivered: float | None = Field(None)
    month_planned_delivery: float | None = Field(None)
    month_delivered_qty: float | None = Field(None)
    undelivered_qty: float | None = Field(None)
    month_planned_invoice: float | None = Field(None)
    invoiced_qty: float | None = Field(None)
    delivery_completion_rate: float | None = Field(None)
    last_month_end_inventory: float | None = Field(None)
    month_planned_capacity: float | None = Field(None)
    month_end_inventory: float | None = Field(None)
    remarks: str | None = Field(None)


class SalesPlanDetailResponse(SalesPlanDetailBase):
    id: uuid.UUID
    source: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


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
    min_balance_rate: float | None = Field(
        None, ge=0, le=100, description="最低平衡率(%)"
    )
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
