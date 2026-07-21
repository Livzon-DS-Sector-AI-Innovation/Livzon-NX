from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from app.modules.agent.tools import ToolContext, agent_tool
from app.modules.quality.schemas import (
    CpvBatchResponse,
    CpvBatchWideResponse,
    CpvParameterCreate,
    CpvParameterResponse,
    CpvParameterUpdate,
    CpvProductCreate,
    CpvProductListResponse,
    CpvProductResponse,
    CpvProductUpdate,
    CreateCapaRequest,
    CreateChangeActionPlanRequest,
    CreateChangeRequest,
    CreateDeviationRequest,
    CreateValidationRequest,
    SubmitInvestigationRequest,
    UpdateCapaRequest,
    UpdateChangeActionPlanRequest,
    UpdateChangeRequest,
    UpdateDeviationRequest,
    UpdateValidationRequest,
)
from app.modules.quality.schemas.external_quality import (
    ComplaintOut,
    ProductQualityRecordOut,
    ReturnRecallOut,
    SupplierOut,
)
from app.modules.quality.schemas.inspection import InspectionRecordOut
from app.modules.quality.schemas.oos_oot import OosOotRecordOut
from app.modules.quality.schemas.validation import UpdateValidationExecutionRequest
from app.modules.quality.service import (
    change_action_plan,
    cpv_batch,
    cpv_parameter,
    cpv_product,
    cpv_statistics,
    external_quality,
    feishu_capa,
    inspection,
    oos_oot,
    quality_feishu_pages,
    quality_feishu_sync,
    quality_management,
    validation,
)


class PageInput(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class InspectionRecordListInput(PageInput):
    inspection_type: str | None = None
    conclusion: str | None = None
    department: str | None = None
    keyword: str | None = None


class InspectionRecordIdInput(BaseModel):
    record_id: uuid.UUID


class OosOotRecordListInput(PageInput):
    record_type: str | None = Field(default=None, pattern="^(OOS|OOT)$")
    status: str | None = Field(
        default=None, pattern="^(open|investigating|closed)$"
    )
    keyword: str | None = None


class OosOotRecordIdInput(BaseModel):
    record_id: uuid.UUID


class SupplierListInput(PageInput):
    status: str | None = Field(
        default=None, pattern="^(active|suspended|blacklisted)$"
    )
    category: str | None = None
    keyword: str | None = None


class ComplaintListInput(PageInput):
    status: str | None = Field(
        default=None, pattern="^(pending|investigating|responded|closed)$"
    )
    complaint_category: str | None = None
    keyword: str | None = None


class ReturnRecallListInput(PageInput):
    record_type: str | None = Field(default=None, pattern="^(return|recall)$")
    status: str | None = Field(
        default=None, pattern="^(pending|assessing|processing|completed)$"
    )
    keyword: str | None = None


class ProductQualityRecordListInput(PageInput):
    record_type: str | None = Field(
        default=None, pattern="^(annual_review|customer_standard)$"
    )
    status: str | None = Field(default=None, pattern="^(draft|completed|approved)$")
    keyword: str | None = None


class DeviationListInput(PageInput):
    status: str | None = None
    level: str | None = None
    department: str | None = None
    keyword: str | None = None
    deviation_code: str | None = None
    product_keyword: str | None = None
    has_occurred_before: bool | None = None
    is_closed: bool | None = None
    investigation_completed_from: str | None = None
    investigation_completed_to: str | None = None
    root_cause_keyword: str | None = None
    corrective_actions_keyword: str | None = None


class DeviationIdInput(BaseModel):
    deviation_id: uuid.UUID


class DeviationUpdateInput(UpdateDeviationRequest):
    deviation_id: uuid.UUID


class DeviationInvestigationInput(SubmitInvestigationRequest):
    deviation_id: uuid.UUID


class CapaListInput(PageInput):
    status: str | None = None
    source: str | None = None
    category: str | None = None
    keyword: str | None = None
    capa_code: str | None = None
    affected_product: str | None = None
    source_code: str | None = None
    evaluation_result: str | None = None
    closure_date_from: str | None = None
    closure_date_to: str | None = None
    department: str | None = None
    qa_confirmer: str | None = None


class CapaIdInput(BaseModel):
    capa_id: uuid.UUID


class CapaUpdateInput(UpdateCapaRequest):
    capa_id: uuid.UUID


class CapaLinkDeviationInput(BaseModel):
    capa_id: uuid.UUID
    deviation_id: uuid.UUID


class CapaCompletePartInput(BaseModel):
    capa_id: uuid.UUID
    part: str = Field(pattern="^(a|b)$")


class CapaExecutionTrackInput(BaseModel):
    capa_id: uuid.UUID
    data: dict[str, Any] = Field(default_factory=dict)


class ChangeListInput(PageInput):
    change_code: str | None = None
    applicant_department: str | None = None
    change_object: str | None = None
    change_level: str | None = None
    application_date_from: str | None = None
    application_date_to: str | None = None
    planned_approval_date_from: str | None = None
    planned_approval_date_to: str | None = None
    execution_date_from: str | None = None
    execution_date_to: str | None = None
    closure_date_from: str | None = None
    closure_date_to: str | None = None
    content_keyword: str | None = None


class ChangeIdInput(BaseModel):
    change_id: uuid.UUID


class ChangeUpdateInput(UpdateChangeRequest):
    change_id: uuid.UUID


class ChangeActionPlanListInput(PageInput):
    change_id: uuid.UUID | None = None
    change_code: str | None = None
    project_name: str | None = None
    related_work: str | None = None
    owner_name: str | None = None
    director_name: str | None = None
    status: str | None = None
    delay_flag: str | None = None
    sync_status: str | None = None
    deadline_date_from: str | None = None
    deadline_date_to: str | None = None


class ChangeActionPlanIdInput(BaseModel):
    plan_id: uuid.UUID


class ChangeActionPlanUpdateInput(UpdateChangeActionPlanRequest):
    plan_id: uuid.UUID


class ValidationListInput(PageInput):
    validation_type: str | None = None
    status: str | None = None
    keyword: str | None = None
    record_code: str | None = None
    department: str | None = None
    planned_end_date_from: str | None = None
    planned_end_date_to: str | None = None
    drafted_at_from: str | None = None
    drafted_at_to: str | None = None


class ValidationIdInput(BaseModel):
    validation_id: uuid.UUID


class ValidationUpdateInput(UpdateValidationRequest):
    validation_id: uuid.UUID


class ValidationExecutionListInput(PageInput):
    validation_type: str
    status: str | None = None
    keyword: str | None = None
    department: str | None = None
    drafted_at_from: str | None = None
    drafted_at_to: str | None = None


class ValidationExecutionUpdateInput(UpdateValidationExecutionRequest):
    validation_type: str
    record_id: uuid.UUID


class CpvProductListInput(PageInput):
    keyword: str | None = None
    status: str | None = None


class CpvProductIdInput(BaseModel):
    product_id: uuid.UUID


class CpvProductUpdateInput(CpvProductUpdate):
    product_id: uuid.UUID


class CpvParameterListInput(BaseModel):
    product_id: uuid.UUID
    parameter_type: str | None = None
    is_enabled: bool | None = None


class CpvParameterCreateInput(CpvParameterCreate):
    product_id: uuid.UUID


class CpvParameterUpdateInput(CpvParameterUpdate):
    parameter_id: uuid.UUID


class CpvBatchListInput(PageInput):
    product_id: uuid.UUID
    data_type: str | None = None
    batch_no: str | None = None
    start_date: date | None = None
    end_date: date | None = None


class CpvWideBatchListInput(PageInput):
    product_id: uuid.UUID
    batch_no: str | None = None
    start_date: date | None = None
    end_date: date | None = None


class CpvMetricInput(BaseModel):
    product_id: uuid.UUID
    parameter_id: uuid.UUID
    batch_no: str | None = None
    start_date: date | None = None
    end_date: date | None = None


class SyncConflictListInput(BaseModel):
    limit: int = Field(default=50, ge=1, le=200)


class PullQualityRecordsInput(BaseModel):
    entity_code: str | None = None


class DeviationReportSyncInput(BaseModel):
    deviation_id: uuid.UUID
    target_record_id: str | None = None


class CapaPlanTrackIdInput(BaseModel):
    track_id: uuid.UUID


class FeishuCapaLedgerListInput(BaseModel):
    keyword: str | None = None
    department: str | None = None
    product: str | None = None
    status: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)


class FeishuCapaPlanTrackListInput(BaseModel):
    keyword: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)


class FeishuRecordIdInput(BaseModel):
    record_id: str


class FeishuValidationListInput(ValidationListInput):
    pass


class FeishuValidationIdInput(BaseModel):
    record_id: str
    validation_type: str | None = None


class FeishuValidationPullInput(BaseModel):
    validation_type: str | None = None


def _user_id(context: ToolContext) -> str:
    return str(context.user_id) if context.user_id else "system"


def _dump(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_dump(item) for item in value]
    if isinstance(value, tuple):
        return [_dump(item) for item in value]
    if isinstance(value, dict):
        return {key: _dump(item) for key, item in value.items()}
    return value


def _without(data: BaseModel, *fields: str) -> dict[str, Any]:
    return data.model_dump(exclude=set(fields), exclude_unset=True)


@agent_tool(
    name="quality.list_deviations",
    summary="查询质量偏差列表",
    input_model=DeviationListInput,
    method="GET",
    path="/quality/deviations",
)
async def list_deviations(context: ToolContext, data: DeviationListInput) -> dict[str, Any]:
    return _dump(await quality_management.get_deviation_list(context.db, **data.model_dump()))


@agent_tool(
    name="quality.get_deviation",
    summary="查看质量偏差详情",
    input_model=DeviationIdInput,
    method="GET",
    path="/quality/deviations/{deviation_id}",
)
async def get_deviation(context: ToolContext, data: DeviationIdInput) -> dict[str, Any]:
    return _dump(await quality_management.get_deviation_detail(context.db, data.deviation_id))


@agent_tool(
    name="quality.list_deviation_report_records",
    summary="查询偏差报告记录",
    input_model=PageInput,
    method="GET",
    path="/quality/deviations/report-records",
)
async def list_deviation_report_records(context: ToolContext, data: PageInput) -> dict[str, Any]:
    return _dump(
        await quality_management.get_deviation_report_record_list(
            context.db,
            page=data.page,
            page_size=data.page_size,
        )
    )


@agent_tool(
    name="quality.get_related_capas",
    summary="查询偏差关联CAPA",
    input_model=DeviationIdInput,
    method="GET",
    path="/quality/deviations/{deviation_id}/related-capas",
)
async def get_related_capas(context: ToolContext, data: DeviationIdInput) -> list[dict[str, Any]]:
    return _dump(await quality_management.get_related_capas_for_deviation(context.db, data.deviation_id))


@agent_tool(
    name="quality.get_deviation_statistics",
    summary="查询偏差统计",
    method="GET",
    path="/quality/statistics/deviations",
)
async def get_deviation_statistics(context: ToolContext, _: BaseModel) -> dict[str, Any]:
    return _dump(await quality_management.get_deviation_statistics(context.db))


@agent_tool(
    name="quality.create_deviation",
    summary="创建质量偏差",
    input_model=CreateDeviationRequest,
    write=True,
    risk_level="medium",
    method="POST",
    path="/quality/deviations",
)
async def create_deviation(context: ToolContext, data: CreateDeviationRequest) -> dict[str, Any]:
    return _dump(
        await quality_management.create_deviation(
            context.db,
            data,
            _user_id(context),
            current_user=context.user,
        )
    )


@agent_tool(
    name="quality.update_deviation",
    summary="更新质量偏差",
    input_model=DeviationUpdateInput,
    write=True,
    risk_level="medium",
    method="PUT",
    path="/quality/deviations/{deviation_id}",
)
async def update_deviation(context: ToolContext, data: DeviationUpdateInput) -> dict[str, Any]:
    payload = UpdateDeviationRequest.model_validate(_without(data, "deviation_id"))
    return _dump(
        await quality_management.update_deviation(
            context.db,
            data.deviation_id,
            payload,
            _user_id(context),
        )
    )


@agent_tool(
    name="quality.submit_deviation",
    summary="提交偏差启动审核流程",
    input_model=DeviationIdInput,
    write=True,
    risk_level="medium",
    method="POST",
    path="/quality/deviations/{deviation_id}/submit",
)
async def submit_deviation(context: ToolContext, data: DeviationIdInput) -> dict[str, Any]:
    return _dump(
        await quality_management.submit_for_review(
            context.db,
            data.deviation_id,
            _user_id(context),
        )
    )


@agent_tool(
    name="quality.submit_deviation_investigation",
    summary="提交偏差调查报告",
    input_model=DeviationInvestigationInput,
    write=True,
    risk_level="medium",
    method="POST",
    path="/quality/deviations/{deviation_id}/submit-investigation",
)
async def submit_deviation_investigation(
    context: ToolContext, data: DeviationInvestigationInput
) -> dict[str, Any]:
    payload = SubmitInvestigationRequest.model_validate(_without(data, "deviation_id"))
    return _dump(
        await quality_management.submit_investigation(
            context.db,
            data.deviation_id,
            payload,
            _user_id(context),
        )
    )


@agent_tool(
    name="quality.resubmit_deviation",
    summary="重新提交偏差",
    input_model=DeviationIdInput,
    write=True,
    risk_level="medium",
    method="POST",
    path="/quality/deviations/{deviation_id}/resubmit",
)
async def resubmit_deviation(context: ToolContext, data: DeviationIdInput) -> dict[str, Any]:
    return _dump(
        await quality_management.resubmit_deviation(
            context.db,
            data.deviation_id,
            _user_id(context),
        )
    )


@agent_tool(
    name="quality.list_capas",
    summary="查询CAPA列表",
    input_model=CapaListInput,
    method="GET",
    path="/quality/capas",
)
async def list_capas(context: ToolContext, data: CapaListInput) -> dict[str, Any]:
    return _dump(await quality_management.get_capa_list(context.db, **data.model_dump()))


@agent_tool(
    name="quality.get_capa",
    summary="查看CAPA详情",
    input_model=CapaIdInput,
    method="GET",
    path="/quality/capas/{capa_id}",
)
async def get_capa(context: ToolContext, data: CapaIdInput) -> dict[str, Any]:
    return _dump(await quality_management.get_capa_detail(context.db, data.capa_id))


@agent_tool(
    name="quality.list_capa_departments",
    summary="查询CAPA部门列表",
    method="GET",
    path="/quality/capas/departments",
)
async def list_capa_departments(context: ToolContext, _: BaseModel) -> list[str]:
    return await quality_management.get_capa_departments(context.db)


@agent_tool(
    name="quality.auto_fill_capa_from_deviation",
    summary="从偏差自动填充CAPA表单",
    input_model=DeviationIdInput,
    method="GET",
    path="/quality/capas/auto-fill/{deviation_id}",
)
async def auto_fill_capa_from_deviation(context: ToolContext, data: DeviationIdInput) -> dict[str, Any]:
    return _dump(await quality_management.auto_fill_from_deviation(context.db, data.deviation_id))


@agent_tool(
    name="quality.get_capa_statistics",
    summary="查询CAPA统计",
    method="GET",
    path="/quality/statistics/capas",
)
async def get_capa_statistics(context: ToolContext, _: BaseModel) -> dict[str, Any]:
    return _dump(await quality_management.get_capa_statistics(context.db))


@agent_tool(
    name="quality.create_capa",
    summary="创建CAPA",
    input_model=CreateCapaRequest,
    write=True,
    risk_level="medium",
    method="POST",
    path="/quality/capas",
)
async def create_capa(context: ToolContext, data: CreateCapaRequest) -> dict[str, Any]:
    return _dump(await quality_management.create_capa(context.db, data, _user_id(context)))


@agent_tool(
    name="quality.update_capa",
    summary="更新CAPA",
    input_model=CapaUpdateInput,
    write=True,
    risk_level="medium",
    method="PUT",
    path="/quality/capas/{capa_id}",
)
async def update_capa(context: ToolContext, data: CapaUpdateInput) -> dict[str, Any]:
    payload = UpdateCapaRequest.model_validate(_without(data, "capa_id"))
    return _dump(
        await quality_management.update_capa(
            context.db,
            data.capa_id,
            payload,
            _user_id(context),
        )
    )


@agent_tool(
    name="quality.submit_capa",
    summary="提交CAPA审核",
    input_model=CapaIdInput,
    write=True,
    risk_level="medium",
    method="POST",
    path="/quality/capas/{capa_id}/submit",
)
async def submit_capa(context: ToolContext, data: CapaIdInput) -> dict[str, Any]:
    return _dump(await quality_management.submit_capa(context.db, data.capa_id, _user_id(context)))


@agent_tool(
    name="quality.resubmit_capa",
    summary="重新提交CAPA",
    input_model=CapaIdInput,
    write=True,
    risk_level="medium",
    method="POST",
    path="/quality/capas/{capa_id}/resubmit",
)
async def resubmit_capa(context: ToolContext, data: CapaIdInput) -> dict[str, Any]:
    return _dump(await quality_management.resubmit_capa(context.db, data.capa_id, _user_id(context)))


@agent_tool(
    name="quality.link_capa_deviation",
    summary="关联偏差到CAPA",
    input_model=CapaLinkDeviationInput,
    write=True,
    risk_level="medium",
    method="POST",
    path="/quality/capas/{capa_id}/link-deviation",
)
async def link_capa_deviation(context: ToolContext, data: CapaLinkDeviationInput) -> dict[str, Any]:
    return _dump(
        await quality_management.link_deviation(
            context.db,
            data.capa_id,
            data.deviation_id,
            _user_id(context),
        )
    )


@agent_tool(
    name="quality.complete_capa_part",
    summary="完成CAPA部分内容",
    input_model=CapaCompletePartInput,
    write=True,
    risk_level="medium",
    method="POST",
    path="/quality/capas/{capa_id}/complete-part",
)
async def complete_capa_part(context: ToolContext, data: CapaCompletePartInput) -> dict[str, Any]:
    return _dump(
        await quality_management.complete_part(
            context.db,
            data.capa_id,
            data.part,
            _user_id(context),
        )
    )


@agent_tool(
    name="quality.add_capa_execution_track",
    summary="添加CAPA执行记录",
    input_model=CapaExecutionTrackInput,
    write=True,
    risk_level="medium",
    method="POST",
    path="/quality/capas/{capa_id}/add-execution-track",
)
async def add_capa_execution_track(
    context: ToolContext, data: CapaExecutionTrackInput
) -> dict[str, Any]:
    return _dump(
        await quality_management.add_execution_track(
            context.db,
            data.capa_id,
            data.data,
            _user_id(context),
        )
    )


@agent_tool(
    name="quality.list_changes",
    summary="查询变更列表",
    input_model=ChangeListInput,
    method="GET",
    path="/quality/changes",
)
async def list_changes(context: ToolContext, data: ChangeListInput) -> dict[str, Any]:
    return _dump(await quality_management.get_change_list(context.db, **data.model_dump()))


@agent_tool(
    name="quality.get_change",
    summary="查看变更详情",
    input_model=ChangeIdInput,
    method="GET",
    path="/quality/changes/{change_id}",
)
async def get_change(context: ToolContext, data: ChangeIdInput) -> dict[str, Any]:
    return _dump(await quality_management.get_change_detail(context.db, data.change_id))


@agent_tool(
    name="quality.get_next_change_code",
    summary="获取下一个变更控制号",
    method="GET",
    path="/quality/changes/next-code",
)
async def get_next_change_code(context: ToolContext, _: BaseModel) -> dict[str, str]:
    return {"change_code": await quality_management.generate_next_change_code(context.db)}


@agent_tool(
    name="quality.get_change_statistics",
    summary="查询变更统计",
    method="GET",
    path="/quality/statistics/changes",
)
async def get_change_statistics(context: ToolContext, _: BaseModel) -> dict[str, Any]:
    return _dump(await quality_management.get_change_statistics(context.db))


@agent_tool(
    name="quality.create_change",
    summary="创建变更",
    input_model=CreateChangeRequest,
    write=True,
    risk_level="medium",
    method="POST",
    path="/quality/changes",
)
async def create_change(context: ToolContext, data: CreateChangeRequest) -> dict[str, Any]:
    return _dump(await quality_management.create_change(context.db, data, _user_id(context)))


@agent_tool(
    name="quality.update_change",
    summary="更新变更",
    input_model=ChangeUpdateInput,
    write=True,
    risk_level="medium",
    method="PUT",
    path="/quality/changes/{change_id}",
)
async def update_change(context: ToolContext, data: ChangeUpdateInput) -> dict[str, Any]:
    payload = UpdateChangeRequest.model_validate(_without(data, "change_id"))
    return _dump(
        await quality_management.update_change(
            context.db,
            data.change_id,
            payload,
            _user_id(context),
        )
    )


@agent_tool(
    name="quality.list_change_action_plans",
    summary="查询变更计划列表",
    input_model=ChangeActionPlanListInput,
    method="GET",
    path="/quality/change-action-plans",
)
async def list_change_action_plans(
    context: ToolContext, data: ChangeActionPlanListInput
) -> dict[str, Any]:
    return _dump(await change_action_plan.get_change_action_plan_list(context.db, **data.model_dump()))


@agent_tool(
    name="quality.list_change_action_plans_by_change",
    summary="查询指定变更下的变更计划",
    input_model=ChangeIdInput,
    method="GET",
    path="/quality/changes/{change_id}/action-plans",
)
async def list_change_action_plans_by_change(
    context: ToolContext, data: ChangeIdInput
) -> list[dict[str, Any]]:
    return _dump(await change_action_plan.get_change_action_plans_for_change(context.db, data.change_id))


@agent_tool(
    name="quality.create_change_action_plan",
    summary="创建变更计划",
    input_model=CreateChangeActionPlanRequest,
    write=True,
    risk_level="medium",
    method="POST",
    path="/quality/change-action-plans",
)
async def create_change_action_plan(
    context: ToolContext, data: CreateChangeActionPlanRequest
) -> dict[str, Any]:
    return _dump(
        await change_action_plan.create_change_action_plan_record(
            context.db,
            data,
            _user_id(context),
        )
    )


@agent_tool(
    name="quality.update_change_action_plan",
    summary="更新变更计划",
    input_model=ChangeActionPlanUpdateInput,
    write=True,
    risk_level="medium",
    method="PUT",
    path="/quality/change-action-plans/{plan_id}",
)
async def update_change_action_plan(
    context: ToolContext, data: ChangeActionPlanUpdateInput
) -> dict[str, Any]:
    payload = UpdateChangeActionPlanRequest.model_validate(_without(data, "plan_id"))
    return _dump(
        await change_action_plan.update_change_action_plan_record(
            context.db,
            data.plan_id,
            payload,
            _user_id(context),
        )
    )


@agent_tool(
    name="quality.sync_change_action_plan",
    summary="同步变更计划到飞书",
    input_model=ChangeActionPlanIdInput,
    write=True,
    risk_level="medium",
    method="POST",
    path="/quality/change-action-plans/{plan_id}/sync-to-feishu",
)
async def sync_change_action_plan(context: ToolContext, data: ChangeActionPlanIdInput) -> dict[str, Any]:
    return _dump(await change_action_plan.sync_change_action_plan_to_feishu(context.db, data.plan_id))


@agent_tool(
    name="quality.sync_change_action_plans_from_feishu",
    summary="从飞书同步变更计划",
    write=True,
    risk_level="medium",
    method="POST",
    path="/quality/change-action-plans/sync-from-feishu",
)
async def sync_change_action_plans_from_feishu(context: ToolContext, _: BaseModel) -> dict[str, Any]:
    return _dump(
        await change_action_plan.sync_change_action_plans_from_feishu(
            context.db,
            _user_id(context),
        )
    )


@agent_tool(
    name="quality.run_change_action_plan_reminders",
    summary="立即执行变更计划提醒",
    write=True,
    risk_level="medium",
    method="POST",
    path="/quality/change-action-plans/reminders/run",
)
async def run_change_action_plan_reminders(context: ToolContext, _: BaseModel) -> dict[str, Any]:
    return _dump(await change_action_plan.run_change_action_plan_reminders_now(context.db))


@agent_tool(
    name="quality.send_change_action_plan_reminder",
    summary="手动发送单条变更计划提醒",
    input_model=ChangeActionPlanIdInput,
    write=True,
    risk_level="medium",
    method="POST",
    path="/quality/change-action-plans/{plan_id}/reminders/send",
)
async def send_change_action_plan_reminder(
    context: ToolContext, data: ChangeActionPlanIdInput
) -> dict[str, Any]:
    return _dump(
        await change_action_plan.send_change_action_plan_reminder_for_plan(
            context.db,
            data.plan_id,
        )
    )


@agent_tool(
    name="quality.list_validations",
    summary="查询验证列表",
    input_model=ValidationListInput,
    method="GET",
    path="/quality/validations",
)
async def list_validations(context: ToolContext, data: ValidationListInput) -> dict[str, Any]:
    return _dump(await validation.get_validation_list(context.db, **data.model_dump()))


@agent_tool(
    name="quality.get_validation",
    summary="查看验证详情",
    input_model=ValidationIdInput,
    method="GET",
    path="/quality/validations/{validation_id}",
)
async def get_validation(context: ToolContext, data: ValidationIdInput) -> dict[str, Any]:
    return _dump(await validation.get_validation_detail(context.db, data.validation_id))


@agent_tool(
    name="quality.get_validation_statistics",
    summary="查询验证统计",
    method="GET",
    path="/quality/statistics/validations",
)
async def get_validation_statistics(context: ToolContext, _: BaseModel) -> dict[str, Any]:
    return _dump(await validation.get_validation_statistics(context.db))


@agent_tool(
    name="quality.list_validation_executions",
    summary="查询验证执行列表",
    input_model=ValidationExecutionListInput,
    method="GET",
    path="/quality/validation-executions/{validation_type}",
)
async def list_validation_executions(
    context: ToolContext, data: ValidationExecutionListInput
) -> dict[str, Any]:
    return _dump(await validation.get_validation_execution_list(context.db, **data.model_dump()))


@agent_tool(
    name="quality.create_validation",
    summary="创建验证记录",
    input_model=CreateValidationRequest,
    write=True,
    risk_level="medium",
    method="POST",
    path="/quality/validations",
)
async def create_validation(context: ToolContext, data: CreateValidationRequest) -> dict[str, Any]:
    return _dump(await validation.create_validation(context.db, data, _user_id(context)))


@agent_tool(
    name="quality.update_validation",
    summary="更新验证记录",
    input_model=ValidationUpdateInput,
    write=True,
    risk_level="medium",
    method="PUT",
    path="/quality/validations/{validation_id}",
)
async def update_validation(context: ToolContext, data: ValidationUpdateInput) -> dict[str, Any]:
    payload = UpdateValidationRequest.model_validate(_without(data, "validation_id"))
    return _dump(
        await validation.update_validation(
            context.db,
            data.validation_id,
            payload,
            _user_id(context),
        )
    )


@agent_tool(
    name="quality.update_validation_execution",
    summary="更新验证执行记录",
    input_model=ValidationExecutionUpdateInput,
    write=True,
    risk_level="medium",
    method="PUT",
    path="/quality/validation-executions/{validation_type}/{record_id}",
)
async def update_validation_execution(
    context: ToolContext, data: ValidationExecutionUpdateInput
) -> dict[str, Any]:
    payload = UpdateValidationExecutionRequest.model_validate(
        _without(data, "validation_type", "record_id")
    )
    return _dump(
        await validation.update_validation_execution(
            context.db,
            validation_type=data.validation_type,
            record_id=data.record_id,
            data=payload,
            user_id=_user_id(context),
        )
    )


@agent_tool(
    name="quality.list_cpv_products",
    summary="查询CPV产品列表",
    input_model=CpvProductListInput,
    method="GET",
    path="/quality/cpv/products",
)
async def list_cpv_products(context: ToolContext, data: CpvProductListInput) -> dict[str, Any]:
    items, total = await cpv_product.get_products(
        context.db,
        keyword=data.keyword,
        status=data.status,
        page=data.page,
        page_size=data.page_size,
    )
    return {
        "items": [
            CpvProductListResponse.model_validate(item).model_dump(mode="json")
            for item in items
        ],
        "total": total,
        "page": data.page,
        "page_size": data.page_size,
    }


@agent_tool(
    name="quality.get_cpv_product",
    summary="查看CPV产品详情",
    input_model=CpvProductIdInput,
    method="GET",
    path="/quality/cpv/products/{product_id}",
)
async def get_cpv_product(context: ToolContext, data: CpvProductIdInput) -> dict[str, Any]:
    item = await cpv_product.get_product_by_id(context.db, data.product_id)
    return CpvProductResponse.model_validate(item).model_dump(mode="json")


@agent_tool(
    name="quality.create_cpv_product",
    summary="创建CPV产品",
    input_model=CpvProductCreate,
    write=True,
    risk_level="medium",
    method="POST",
    path="/quality/cpv/products",
)
async def create_cpv_product(context: ToolContext, data: CpvProductCreate) -> dict[str, Any]:
    item = await cpv_product.create_product(context.db, data)
    return CpvProductResponse.model_validate(item).model_dump(mode="json")


@agent_tool(
    name="quality.update_cpv_product",
    summary="更新CPV产品",
    input_model=CpvProductUpdateInput,
    write=True,
    risk_level="medium",
    method="PUT",
    path="/quality/cpv/products/{product_id}",
)
async def update_cpv_product(context: ToolContext, data: CpvProductUpdateInput) -> dict[str, Any]:
    payload = CpvProductUpdate.model_validate(_without(data, "product_id"))
    item = await cpv_product.update_product(context.db, data.product_id, payload)
    return CpvProductResponse.model_validate(item).model_dump(mode="json")


@agent_tool(
    name="quality.list_cpv_parameters",
    summary="查询CPV参数列表",
    input_model=CpvParameterListInput,
    method="GET",
    path="/quality/cpv/products/{product_id}/parameters",
)
async def list_cpv_parameters(
    context: ToolContext, data: CpvParameterListInput
) -> list[dict[str, Any]]:
    items = await cpv_parameter.get_parameters(
        context.db,
        data.product_id,
        parameter_type=data.parameter_type,
        is_enabled=data.is_enabled,
    )
    return [
        CpvParameterResponse.model_validate(item).model_dump(mode="json")
        for item in items
    ]


@agent_tool(
    name="quality.create_cpv_parameter",
    summary="创建CPV参数",
    input_model=CpvParameterCreateInput,
    write=True,
    risk_level="medium",
    method="POST",
    path="/quality/cpv/products/{product_id}/parameters",
)
async def create_cpv_parameter(
    context: ToolContext, data: CpvParameterCreateInput
) -> dict[str, Any]:
    payload = CpvParameterCreate.model_validate(_without(data, "product_id"))
    item = await cpv_parameter.create_parameter(context.db, data.product_id, payload)
    return CpvParameterResponse.model_validate(item).model_dump(mode="json")


@agent_tool(
    name="quality.update_cpv_parameter",
    summary="更新CPV参数",
    input_model=CpvParameterUpdateInput,
    write=True,
    risk_level="medium",
    method="PUT",
    path="/quality/cpv/parameters/{parameter_id}",
)
async def update_cpv_parameter(
    context: ToolContext, data: CpvParameterUpdateInput
) -> dict[str, Any]:
    payload = CpvParameterUpdate.model_validate(_without(data, "parameter_id"))
    item = await cpv_parameter.update_parameter(context.db, data.parameter_id, payload)
    return CpvParameterResponse.model_validate(item).model_dump(mode="json")


@agent_tool(
    name="quality.list_cpv_batches",
    summary="查询CPV批次列表",
    input_model=CpvBatchListInput,
    method="GET",
    path="/quality/cpv/products/{product_id}/batches",
)
async def list_cpv_batches(context: ToolContext, data: CpvBatchListInput) -> dict[str, Any]:
    items, total = await cpv_batch.get_batches(
        context.db,
        data.product_id,
        data_type=data.data_type,
        batch_no=data.batch_no,
        start_date=data.start_date,
        end_date=data.end_date,
        page=data.page,
        page_size=data.page_size,
    )
    return {
        "items": [
            CpvBatchResponse.model_validate(item).model_dump(mode="json")
            for item in items
        ],
        "total": total,
        "page": data.page,
        "page_size": data.page_size,
    }


async def _list_cpv_wide_batches(
    context: ToolContext,
    data: CpvWideBatchListInput,
    data_type: str,
) -> dict[str, Any]:
    items, total = await cpv_batch.get_batches_wide(
        context.db,
        data.product_id,
        data_type,
        batch_no=data.batch_no,
        start_date=data.start_date,
        end_date=data.end_date,
        page=data.page,
        page_size=data.page_size,
    )
    return {
        "items": [
            CpvBatchWideResponse.model_validate(item).model_dump(mode="json")
            for item in items
        ],
        "total": total,
        "page": data.page,
        "page_size": data.page_size,
    }


@agent_tool(
    name="quality.list_cpv_cpp_batches",
    summary="查询CPV CPP宽表批次数据",
    input_model=CpvWideBatchListInput,
    method="GET",
    path="/quality/cpv/products/{product_id}/cpp",
)
async def list_cpv_cpp_batches(
    context: ToolContext, data: CpvWideBatchListInput
) -> dict[str, Any]:
    return await _list_cpv_wide_batches(context, data, "CPP")


@agent_tool(
    name="quality.list_cpv_cqa_batches",
    summary="查询CPV CQA宽表批次数据",
    input_model=CpvWideBatchListInput,
    method="GET",
    path="/quality/cpv/products/{product_id}/cqa",
)
async def list_cpv_cqa_batches(
    context: ToolContext, data: CpvWideBatchListInput
) -> dict[str, Any]:
    return await _list_cpv_wide_batches(context, data, "CQA")


@agent_tool(
    name="quality.get_cpv_statistics",
    summary="查询CPV统计数据",
    input_model=CpvMetricInput,
    method="GET",
    path="/quality/cpv/products/{product_id}/statistics",
)
async def get_cpv_statistics(context: ToolContext, data: CpvMetricInput) -> dict[str, Any]:
    return _dump(
        await cpv_statistics.get_statistics(
            context.db,
            data.product_id,
            data.parameter_id,
            batch_no=data.batch_no,
            start_date=data.start_date,
            end_date=data.end_date,
        )
    )


@agent_tool(
    name="quality.get_cpv_trend",
    summary="查询CPV趋势数据",
    input_model=CpvMetricInput,
    method="GET",
    path="/quality/cpv/products/{product_id}/trend",
)
async def get_cpv_trend(context: ToolContext, data: CpvMetricInput) -> dict[str, Any]:
    return _dump(
        await cpv_statistics.get_trend_data(
            context.db,
            data.product_id,
            data.parameter_id,
            batch_no=data.batch_no,
            start_date=data.start_date,
            end_date=data.end_date,
        )
    )


@agent_tool(
    name="quality.list_quality_sync_conflicts",
    summary="查询质量飞书同步冲突",
    input_model=SyncConflictListInput,
    method="GET",
    path="/quality/feishu-sync/conflicts",
)
async def list_quality_sync_conflicts(
    context: ToolContext, data: SyncConflictListInput
) -> list[dict[str, Any]]:
    return _dump(await quality_feishu_sync.get_quality_sync_conflicts(context.db, limit=data.limit))


@agent_tool(
    name="quality.pull_quality_records_from_feishu",
    summary="从飞书回拉质量数据",
    input_model=PullQualityRecordsInput,
    write=True,
    risk_level="medium",
    method="POST",
    path="/quality/feishu-sync/pull",
)
async def pull_quality_records_from_feishu(
    context: ToolContext, data: PullQualityRecordsInput
) -> dict[str, Any]:
    return _dump(await quality_feishu_sync.pull_quality_records_from_feishu(context.db, data.entity_code))


@agent_tool(
    name="quality.sync_deviation_to_feishu",
    summary="同步偏差到飞书Base",
    input_model=DeviationIdInput,
    write=True,
    risk_level="medium",
    method="POST",
    path="/quality/feishu-sync/deviations/{deviation_id}",
)
async def sync_deviation_to_feishu(context: ToolContext, data: DeviationIdInput) -> dict[str, Any]:
    return _dump(await quality_feishu_sync.sync_deviation_to_feishu(context.db, data.deviation_id))


@agent_tool(
    name="quality.sync_deviation_report_record_to_feishu",
    summary="同步偏差报告记录到飞书Base",
    input_model=DeviationReportSyncInput,
    write=True,
    risk_level="medium",
    method="POST",
    path="/quality/feishu-sync/deviation-report-records/{deviation_id}",
)
async def sync_deviation_report_record_to_feishu(
    context: ToolContext, data: DeviationReportSyncInput
) -> dict[str, Any]:
    return _dump(
        await quality_feishu_sync.sync_deviation_report_record_to_feishu(
            context.db,
            data.deviation_id,
            target_record_id=data.target_record_id,
        )
    )


@agent_tool(
    name="quality.sync_capa_to_feishu",
    summary="同步CAPA到飞书Base",
    input_model=CapaIdInput,
    write=True,
    risk_level="medium",
    method="POST",
    path="/quality/feishu-sync/capas/{capa_id}",
)
async def sync_capa_to_feishu(context: ToolContext, data: CapaIdInput) -> dict[str, Any]:
    return _dump(await quality_feishu_sync.sync_capa_to_feishu(context.db, data.capa_id))


@agent_tool(
    name="quality.sync_capa_plan_track_to_feishu",
    summary="同步CAPA计划跟踪到飞书Base",
    input_model=CapaPlanTrackIdInput,
    write=True,
    risk_level="medium",
    method="POST",
    path="/quality/feishu-sync/capa-plan-tracks/{track_id}",
)
async def sync_capa_plan_track_to_feishu(
    context: ToolContext, data: CapaPlanTrackIdInput
) -> dict[str, Any]:
    return _dump(await quality_feishu_sync.sync_capa_plan_track_to_feishu(context.db, data.track_id))


@agent_tool(
    name="quality.list_feishu_capa_ledger",
    summary="查询飞书CAPA台账",
    input_model=FeishuCapaLedgerListInput,
    method="GET",
    path="/quality/feishu-capa/capas",
)
async def list_feishu_capa_ledger(
    context: ToolContext, data: FeishuCapaLedgerListInput
) -> dict[str, Any]:
    return _dump(await feishu_capa.list_capa_ledger(context.db, **data.model_dump()))


@agent_tool(
    name="quality.get_feishu_capa_ledger",
    summary="查看飞书CAPA台账详情",
    input_model=FeishuRecordIdInput,
    method="GET",
    path="/quality/feishu-capa/capas/{record_id}",
)
async def get_feishu_capa_ledger(
    context: ToolContext, data: FeishuRecordIdInput
) -> dict[str, Any]:
    return _dump(await feishu_capa.get_capa_ledger_record(context.db, data.record_id))


@agent_tool(
    name="quality.list_feishu_capa_plan_tracks",
    summary="查询飞书CAPA计划跟踪",
    input_model=FeishuCapaPlanTrackListInput,
    method="GET",
    path="/quality/feishu-capa/capa-plan-tracks",
)
async def list_feishu_capa_plan_tracks(
    context: ToolContext, data: FeishuCapaPlanTrackListInput
) -> dict[str, Any]:
    return _dump(await feishu_capa.list_capa_plan_tracks(context.db, **data.model_dump()))


@agent_tool(
    name="quality.get_feishu_capa_plan_track",
    summary="查看飞书CAPA计划跟踪详情",
    input_model=FeishuRecordIdInput,
    method="GET",
    path="/quality/feishu-capa/capa-plan-tracks/{record_id}",
)
async def get_feishu_capa_plan_track(
    context: ToolContext, data: FeishuRecordIdInput
) -> dict[str, Any]:
    return _dump(await feishu_capa.get_capa_plan_track_record(context.db, data.record_id))


@agent_tool(
    name="quality.list_feishu_validations",
    summary="查询飞书验证记录",
    input_model=FeishuValidationListInput,
    method="GET",
    path="/quality/feishu/validations",
)
async def list_feishu_validations(
    context: ToolContext, data: FeishuValidationListInput
) -> dict[str, Any]:
    return _dump(
        await quality_feishu_pages.list_validation_records_from_feishu(
            context.db,
            **data.model_dump(),
        )
    )


@agent_tool(
    name="quality.get_feishu_validation",
    summary="查看飞书验证记录详情",
    input_model=FeishuValidationIdInput,
    method="GET",
    path="/quality/feishu/validations/{record_id}",
)
async def get_feishu_validation(
    context: ToolContext, data: FeishuValidationIdInput
) -> dict[str, Any]:
    return _dump(
        await quality_feishu_pages.get_validation_record_from_feishu(
            context.db,
            data.record_id,
            validation_type=data.validation_type,
        )
    )


@agent_tool(
    name="quality.pull_feishu_validations",
    summary="从飞书回拉验证记录",
    input_model=FeishuValidationPullInput,
    write=True,
    risk_level="medium",
    method="POST",
    path="/quality/feishu-sync/validations/pull",
)
async def pull_feishu_validations(
    context: ToolContext, data: FeishuValidationPullInput
) -> dict[str, Any]:
    return _dump(
        await quality_feishu_pages.pull_validation_records_from_feishu(
            context.db,
            validation_type=data.validation_type,
        )
    )


def _page_result(
    items: list[Any],
    total: int,
    page: int,
    page_size: int,
    output_model: type[BaseModel],
) -> dict[str, Any]:
    return {
        "items": [
            output_model.model_validate(item).model_dump(mode="json") for item in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@agent_tool(
    name="quality.list_inspection_records",
    summary="查询质量检验记录",
    input_model=InspectionRecordListInput,
    method="GET",
    path="/quality/inspections",
)
async def list_inspection_records(
    context: ToolContext, data: InspectionRecordListInput
) -> dict[str, Any]:
    items, total = await inspection.list_resource_records(
        context.db,
        "inspection_records",
        keyword=data.keyword,
        page=data.page,
        page_size=data.page_size,
        filters={
            "inspection_type": data.inspection_type,
            "conclusion": data.conclusion,
            "department": data.department,
        },
    )
    return _page_result(
        items, total, data.page, data.page_size, InspectionRecordOut
    )


@agent_tool(
    name="quality.get_inspection_record",
    summary="查看质量检验记录详情",
    input_model=InspectionRecordIdInput,
    method="GET",
    path="/quality/inspections/{record_id}",
)
async def get_inspection_record(
    context: ToolContext, data: InspectionRecordIdInput
) -> dict[str, Any]:
    record = await inspection.get_resource_record(
        context.db, "inspection_records", data.record_id
    )
    return InspectionRecordOut.model_validate(record).model_dump(mode="json")


@agent_tool(
    name="quality.list_oos_oot_records",
    summary="查询OOS/OOT质量事件",
    input_model=OosOotRecordListInput,
    method="GET",
    path="/quality/oos-oot/records",
)
async def list_oos_oot_records(
    context: ToolContext, data: OosOotRecordListInput
) -> dict[str, Any]:
    items, total = await oos_oot.list_oos_oot_records(
        context.db,
        record_type=data.record_type,
        status=data.status,
        keyword=data.keyword,
        page=data.page,
        page_size=data.page_size,
    )
    return _page_result(items, total, data.page, data.page_size, OosOotRecordOut)


@agent_tool(
    name="quality.get_oos_oot_record",
    summary="查看OOS/OOT质量事件详情",
    input_model=OosOotRecordIdInput,
    method="GET",
    path="/quality/oos-oot/records/{record_id}",
)
async def get_oos_oot_record(
    context: ToolContext, data: OosOotRecordIdInput
) -> dict[str, Any]:
    record = await oos_oot.get_oos_oot_record(context.db, data.record_id)
    return OosOotRecordOut.model_validate(record).model_dump(mode="json")


async def _list_external_quality_records(
    context: ToolContext,
    *,
    resource_code: str,
    filters: dict[str, Any],
    keyword: str | None,
    page: int,
    page_size: int,
    output_model: type[BaseModel],
) -> dict[str, Any]:
    items, total = await external_quality.list_resource_records(
        context.db,
        resource_code,
        filters=filters,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return _page_result(items, total, page, page_size, output_model)


@agent_tool(
    name="quality.list_suppliers",
    summary="查询质量供应商台账",
    input_model=SupplierListInput,
    method="GET",
    path="/quality/suppliers",
)
async def list_suppliers(
    context: ToolContext, data: SupplierListInput
) -> dict[str, Any]:
    return await _list_external_quality_records(
        context,
        resource_code="suppliers",
        filters={"status": data.status, "category": data.category},
        keyword=data.keyword,
        page=data.page,
        page_size=data.page_size,
        output_model=SupplierOut,
    )


@agent_tool(
    name="quality.list_complaints",
    summary="查询客户投诉台账",
    input_model=ComplaintListInput,
    method="GET",
    path="/quality/complaints",
)
async def list_complaints(
    context: ToolContext, data: ComplaintListInput
) -> dict[str, Any]:
    return await _list_external_quality_records(
        context,
        resource_code="complaints",
        filters={
            "status": data.status,
            "complaint_category": data.complaint_category,
        },
        keyword=data.keyword,
        page=data.page,
        page_size=data.page_size,
        output_model=ComplaintOut,
    )


@agent_tool(
    name="quality.list_return_recalls",
    summary="查询退货与召回台账",
    input_model=ReturnRecallListInput,
    method="GET",
    path="/quality/return-recalls",
)
async def list_return_recalls(
    context: ToolContext, data: ReturnRecallListInput
) -> dict[str, Any]:
    return await _list_external_quality_records(
        context,
        resource_code="return_recalls",
        filters={"record_type": data.record_type, "status": data.status},
        keyword=data.keyword,
        page=data.page,
        page_size=data.page_size,
        output_model=ReturnRecallOut,
    )


@agent_tool(
    name="quality.list_product_quality_records",
    summary="查询产品质量记录与客户标准",
    input_model=ProductQualityRecordListInput,
    method="GET",
    path="/quality/product-quality",
)
async def list_product_quality_records(
    context: ToolContext, data: ProductQualityRecordListInput
) -> dict[str, Any]:
    return await _list_external_quality_records(
        context,
        resource_code="product_quality_records",
        filters={"record_type": data.record_type, "status": data.status},
        keyword=data.keyword,
        page=data.page,
        page_size=data.page_size,
        output_model=ProductQualityRecordOut,
    )
