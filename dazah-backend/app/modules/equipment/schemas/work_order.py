"""Work order schemas."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.modules.equipment.schemas.work_order_image import WorkOrderImageResponse

# ==================== 维修工单 ====================
WorkOrderType = Literal["故障维修", "计划维护", "巡检", "校准", "异常处理", "日常维护"]
WorkOrderPriority = Literal["紧急", "高", "中", "低"]
WorkOrderStatus = Literal["待处理", "执行中", "待验收", "已完成", "已关闭"]
VerificationResult = Literal["合格", "不合格"]


class WorkOrderCreate(BaseModel):
    """创建工单请求"""

    equipment_id: uuid.UUID = Field(..., description="设备ID")
    order_type: WorkOrderType = Field(default="故障维修", description="工单类型")
    priority: WorkOrderPriority = Field(default="中", description="优先级")
    fault_symptom_id: uuid.UUID | None = Field(default=None, description="故障现象ID")
    fault_cause_id: uuid.UUID | None = Field(default=None, description="故障原因ID")
    fault_action_id: uuid.UUID | None = Field(default=None, description="维修措施ID")
    fault_description: str | None = Field(default=None, description="故障详细描述")
    maintenance_plan_id: uuid.UUID | None = Field(
        default=None, description="关联维护计划ID"
    )
    planned_start_date: date | None = Field(default=None, description="计划执行日期")
    checklist_template_id: uuid.UUID | None = Field(
        default=None, description="关联巡检模板ID"
    )
    responsible_person_id: uuid.UUID | None = Field(
        default=None, description="责任人ID"
    )


class WorkOrderUpdate(BaseModel):
    """更新工单请求"""

    equipment_id: uuid.UUID | None = Field(default=None, description="设备ID")
    order_type: WorkOrderType | None = Field(default=None, description="工单类型")
    priority: WorkOrderPriority | None = Field(default=None, description="优先级")
    status: WorkOrderStatus | None = Field(default=None, description="工单状态")
    fault_symptom_id: uuid.UUID | None = Field(default=None, description="故障现象ID")
    fault_cause_id: uuid.UUID | None = Field(default=None, description="故障原因ID")
    fault_action_id: uuid.UUID | None = Field(default=None, description="维修措施ID")
    fault_description: str | None = Field(default=None, description="故障详细描述")
    planned_start_date: date | None = Field(default=None, description="计划执行日期")
    responsible_person_id: uuid.UUID | None = Field(
        default=None, description="责任人ID"
    )


class WorkOrderAssign(BaseModel):
    """指派工单请求"""

    assignee_id: uuid.UUID = Field(..., description="维修人ID")


class WorkOrderComplete(BaseModel):
    """完成工单请求"""

    repair_detail: str = Field(..., min_length=1, description="维修过程描述")


class WorkOrderVerify(BaseModel):
    """验收工单请求"""

    result: VerificationResult = Field(..., description="验收结果")
    remark: str | None = Field(default=None, description="验收备注")


class WorkOrderResponse(BaseModel):
    """工单响应"""

    id: uuid.UUID
    work_order_no: str
    equipment_id: uuid.UUID
    order_type: WorkOrderType
    priority: WorkOrderPriority
    status: WorkOrderStatus
    fault_symptom_id: uuid.UUID | None
    fault_cause_id: uuid.UUID | None
    fault_action_id: uuid.UUID | None
    fault_description: str | None
    reporter_id: uuid.UUID | None
    assignee_id: uuid.UUID | None
    verified_by: uuid.UUID | None
    reported_at: datetime
    assigned_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    verified_at: datetime | None
    verification_result: VerificationResult | None
    verification_remark: str | None
    repair_detail: str | None
    actual_duration: int | None
    original_equipment_status: str | None
    maintenance_plan_id: uuid.UUID | None
    planned_start_date: date | None
    checklist_template_id: uuid.UUID | None
    check_result: str | None
    spare_parts_cost: float | None
    inspection_task_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None
    updated_by: uuid.UUID | None
    equipment_name: str | None = None
    equipment_no: str | None = None
    reporter_name: str | None = None
    assignee_name: str | None = None
    responsible_person_id: uuid.UUID | None = None
    responsible_person_name: str | None = None
    verifier_name: str | None = None
    symptom_name: str | None = None
    cause_name: str | None = None
    action_name: str | None = None
    images: list["WorkOrderImageResponse"] | None = None

    model_config = {"from_attributes": True}


WorkOrderResponse.model_rebuild()


class WorkOrderStatistics(BaseModel):
    """工单统计"""

    total: int
    by_status: dict[str, int]
    by_type: dict[str, int]
    by_priority: dict[str, int]


class EfficiencyMonthTrend(BaseModel):
    """月度趋势行"""

    month: str = Field(description="年月（YYYY-MM）")
    total: int = Field(description="当月工单数")
    completed: int = Field(description="当月已完成/已关闭数")
    urgent: int = Field(description="当月紧急工单数")
    avg_response: float = Field(description="当月平均响应时长（分钟）")
    avg_repair: float = Field(description="当月平均修复时长（分钟）")


class EfficiencyTopFault(BaseModel):
    """故障 TOP 设备行"""

    equipment_id: str = Field(description="设备ID")
    equipment_name: str = Field(description="设备名称")
    equipment_no: str = Field(description="设备编号")
    workshop_code: str = Field(description="所属车间代码")
    order_count: int = Field(description="工单数")
    avg_repair_minutes: float = Field(description="平均修复时长（分钟）")


class EfficiencyRepairerRank(BaseModel):
    """维修人员排行行"""

    assignee_id: str = Field(description="接单人ID")
    assignee_name: str = Field(description="接单人姓名")
    order_count: int = Field(description="接单数")
    avg_response_minutes: float = Field(description="平均响应时长（分钟）")
    avg_repair_minutes: float = Field(description="平均修复时长（分钟）")


class EfficiencyResponseBucket(BaseModel):
    """响应时效分布档位"""

    bucket: str = Field(description="档位（≤5分钟/5-30分钟/30-120分钟/>120分钟/未接单）")
    count: int = Field(description="档内工单数")
    ratio: float = Field(description="占全部工单比例（0~1）")


class EfficiencyStatistics(BaseModel):
    """维修效能统计"""

    avg_response_minutes: float = Field(description="期内平均响应时长（分钟）")
    avg_repair_minutes: float = Field(description="期内 MTTR（分钟）")
    urgent_total: int = Field(description="紧急工单总数")
    urgent_on_time: int = Field(description="响应≤5分钟的紧急工单数")
    urgent_5min_rate: float | None = Field(
        default=None, description="紧急 5 分钟达标率（0~1）；无紧急单为 None"
    )
    total_orders: int = Field(description="期内工单总数")
    monthly: list[EfficiencyMonthTrend] = Field(description="月度趋势")
    top_faults: list[EfficiencyTopFault] = Field(description="故障 TOP10 设备")
    repairer_ranking: list[EfficiencyRepairerRank] = Field(
        description="维修人员排行（接单数 TOP5）"
    )
    response_buckets: list[EfficiencyResponseBucket] = Field(
        description="响应时效分布（五档，含未接单）"
    )


# ==================== 领料 ====================
class MaterialConsumeItem(BaseModel):
    """单条领料项"""

    spare_part_id: uuid.UUID = Field(..., description="备件ID")
    quantity: int = Field(..., ge=1, description="领用数量")


class MaterialConsumeRequest(BaseModel):
    """领料请求"""

    items: list[MaterialConsumeItem] = Field(..., min_length=1, description="领料清单")


class MaterialConsumeResponse(BaseModel):
    """领料记录响应"""

    id: uuid.UUID
    spare_part_id: uuid.UUID
    work_order_id: uuid.UUID
    transaction_type: str
    quantity: int
    remark: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
