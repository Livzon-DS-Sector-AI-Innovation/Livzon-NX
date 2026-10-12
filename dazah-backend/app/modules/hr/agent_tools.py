"""HR queries preserve the same department scope as the business API."""

from datetime import date
from typing import Any, Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, Field, TypeAdapter

from app.modules.agent.tools import ToolContext, agent_tool
from app.modules.hr.agent_query_service import HrAgentQueryService
from app.modules.hr.contract_schemas import ContractManagementResponse
from app.modules.hr.new_employee_training_service import NewEmployeeTrainingService
from app.modules.hr.plan_tracking_service import PlanTrackingService
from app.modules.hr.position_training_service import PositionTrainingListService
from app.modules.hr.recruitment_service import OnboardingService, RecruitmentService
from app.modules.hr.schemas import (
    AnnualTrainingPlanResponse,
    DepartmentResponse,
    EmployeeResponse,
    OffboardingRecordResponse,
    PlanTrackingRecordResponse,
    PositionTrainingListResponse,
    PositionTransferRecordResponse,
    TrainerResponse,
    TrainingLedgerResponse,
)
from app.modules.hr.service import (
    AnnualTrainingPlanService,
    EmployeeService,
    EmployeeTrainingListService,
    OffboardingRecordService,
    PositionTransferRecordService,
    TrainingLedgerService,
)
from app.modules.hr.trainer_service import TrainerService
from app.platform.identity.data_scope import resolve_user_department_scope


class PageInput(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class EmployeeListInput(PageInput):
    department: str | None = None
    status: str | None = None
    keyword: str | None = Field(default=None, max_length=100)


class TrainingListInput(PageInput):
    employee_number: str | None = None
    date_from: date | None = None
    date_to: date | None = None


class PlanListInput(PageInput):
    year: int | None = Field(default=None, ge=2000, le=2100)
    department: str | None = None


class KeywordInput(PageInput):
    keyword: str | None = Field(default=None, max_length=100)


class DepartmentInput(KeywordInput):
    department: str | None = Field(default=None, max_length=100)


class ContactInput(DepartmentInput):
    status: Literal["1", "2", "3", "4"] | None = None


class CandidateInput(KeywordInput):
    fit_level: str | None = Field(default=None, max_length=100)
    interview_status: str | None = Field(default=None, max_length=100)
    job_id: str | None = Field(default=None, max_length=100)


class EmployeeRecordInput(KeywordInput):
    employee_id: UUID | None = None


class TransferInput(EmployeeRecordInput):
    approval_status: str | None = Field(default=None, max_length=100)


class ContractInput(DepartmentInput):
    contract_sequence: str | None = Field(default=None, max_length=100)


class ApprovalResultInput(PageInput):
    department: str | None = Field(default=None, max_length=100)
    result: Literal["approved", "rejected"] | None = None
    start_date: date | None = None
    end_date: date | None = None


class NewTrainingInput(DepartmentInput):
    status: str | None = Field(default=None, max_length=100)


class EmployeeTrainingInput(PageInput):
    department: str = Field(min_length=1, max_length=100)
    name: str | None = Field(default=None, max_length=100)
    date_from: date | None = None
    date_to: date | None = None


class PositionTrainingInput(PageInput):
    department: str | None = Field(default=None, max_length=100)


class TrackingInput(PageInput):
    plan_id: UUID | None = None


def _page_result(
    rows: list[Any],
    total: int,
    data: PageInput,
    output_model: type[BaseModel] | None = None,
) -> dict[str, Any]:
    if output_model:
        items = [
            output_model.model_validate(row).model_dump(mode="json") for row in rows
        ]
    else:
        items = TypeAdapter(list[Any]).dump_python(rows, mode="json")
    return {
        "data": items,
        "meta": {"page": data.page, "page_size": data.page_size, "total": total},
    }


async def _department_scope(
    context: ToolContext,
    department: str | None = None,
) -> set[str] | None:
    if context.user is None:
        raise HTTPException(403, "缺少可信人事查询身份")
    scope = await resolve_user_department_scope(context.db, context.user)
    if not scope.is_all and department and not scope.allows(department):
        raise HTTPException(403, "无权查询指定部门的人事数据")
    return None if scope.is_all else scope.department_names


@agent_tool(
    name="hr.list_employees",
    summary="查询授权部门员工档案",
    input_model=EmployeeListInput,
    method="GET",
    path="/hr/employees",
    page_keys=("hr:employee-management:profile",),
    sensitivity="restricted",
)
async def list_employees(
    context: ToolContext, data: EmployeeListInput
) -> dict[str, Any]:
    scope = await _department_scope(context, data.department)
    rows, total = await EmployeeService(context.db).list_employees(
        **data.model_dump(),
        dept_alias_set=scope,
    )
    return {
        "data": [
            EmployeeResponse.model_validate(row).model_dump(mode="json") for row in rows
        ],
        "meta": {"page": data.page, "page_size": data.page_size, "total": total},
    }


@agent_tool(
    name="hr.list_training_records",
    summary="查询授权部门培训台账",
    input_model=TrainingListInput,
    method="GET",
    path="/hr/training-ledger",
    page_keys=("hr:training:training-ledger",),
    sensitivity="sensitive",
)
async def list_training_records(
    context: ToolContext,
    data: TrainingListInput,
) -> dict[str, Any]:
    scope = await _department_scope(context)
    rows, total = await TrainingLedgerService(context.db).list_records(
        **data.model_dump(),
        dept_alias_set=scope,
    )
    return {
        "data": [
            TrainingLedgerResponse.model_validate(row).model_dump(mode="json")
            for row in rows
        ],
        "meta": {"page": data.page, "page_size": data.page_size, "total": total},
    }


@agent_tool(
    name="hr.list_training_plans",
    summary="查询授权部门年度培训计划",
    input_model=PlanListInput,
    method="GET",
    path="/hr/annual-training-plans",
    page_keys=("hr:training:annual-plan",),
    sensitivity="sensitive",
)
async def list_training_plans(
    context: ToolContext,
    data: PlanListInput,
) -> dict[str, Any]:
    scope = await _department_scope(context, data.department)
    rows, total = await AnnualTrainingPlanService(context.db).list_plans(
        **data.model_dump(),
        dept_alias_set=scope,
    )
    return {
        "data": [
            AnnualTrainingPlanResponse.model_validate(row).model_dump(mode="json")
            for row in rows
        ],
        "meta": {"page": data.page, "page_size": data.page_size, "total": total},
    }


@agent_tool(
    name="hr.list_departments",
    summary="查询授权范围部门目录",
    input_model=KeywordInput,
    method="GET",
    path="/hr/departments",
    page_keys=("hr:departments",),
    risk_level="low",
)
async def list_departments(context: ToolContext, data: KeywordInput) -> dict[str, Any]:
    scope = await _department_scope(context)
    rows, total = await HrAgentQueryService(context.db).list_departments(
        **data.model_dump(), dept_alias_set=scope
    )
    return _page_result(rows, total, data, DepartmentResponse)


@agent_tool(
    name="hr.list_contacts",
    summary="查询授权部门飞书联系人工作信息",
    input_model=ContactInput,
    page_keys=("hr:employee-management:feishu-contacts",),
    risk_level="low",
    sensitivity="restricted",
    output_hint="只查询人事本地联系人缓存，返回姓名、原始部门、工号、岗位和状态；不读取配置或同步通讯录。",
)
async def list_contacts(context: ToolContext, data: ContactInput) -> dict[str, Any]:
    scope = await _department_scope(context, data.department)
    rows, total = await HrAgentQueryService(context.db).list_contacts(
        **data.model_dump(), dept_alias_set=scope
    )
    return _page_result(rows, total, data)


@agent_tool(
    name="hr.list_candidates",
    summary="查询招聘候选人",
    input_model=CandidateInput,
    method="GET",
    path="/hr/candidates",
    page_keys=("hr:recruitment",),
    risk_level="low",
    sensitivity="restricted",
)
async def list_candidates(context: ToolContext, data: CandidateInput) -> dict[str, Any]:
    rows, total = await RecruitmentService().list_candidates(**data.model_dump())
    return _page_result(rows, total, data)


@agent_tool(
    name="hr.list_onboarding",
    summary="查询授权部门入职记录",
    input_model=KeywordInput,
    method="GET",
    path="/hr/onboarding",
    page_keys=("hr:onboarding",),
    risk_level="low",
    sensitivity="restricted",
)
async def list_onboarding(context: ToolContext, data: KeywordInput) -> dict[str, Any]:
    scope = await _department_scope(context)
    rows, total = await OnboardingService().list_onboarding(
        **data.model_dump(), dept_alias_set=scope
    )
    return _page_result(rows, total, data)


@agent_tool(
    name="hr.list_offboarding",
    summary="查询授权部门离职记录",
    input_model=EmployeeRecordInput,
    method="GET",
    path="/hr/offboarding-records",
    page_keys=("hr:offboarding",),
    risk_level="low",
    sensitivity="restricted",
)
async def list_offboarding(
    context: ToolContext, data: EmployeeRecordInput
) -> dict[str, Any]:
    scope = await _department_scope(context)
    rows, total = await OffboardingRecordService(context.db).list_records(
        **data.model_dump(), dept_alias_set=scope
    )
    return _page_result(rows, total, data, OffboardingRecordResponse)


@agent_tool(
    name="hr.list_position_transfers",
    summary="查询授权部门岗位调动记录",
    input_model=TransferInput,
    method="GET",
    path="/hr/position-transfers",
    page_keys=("hr:position-transfer",),
    risk_level="low",
    sensitivity="restricted",
)
async def list_position_transfers(
    context: ToolContext, data: TransferInput
) -> dict[str, Any]:
    scope = await _department_scope(context)
    rows, total = await PositionTransferRecordService(context.db).list_records(
        **data.model_dump(), dept_alias_set=scope
    )
    return _page_result(rows, total, data, PositionTransferRecordResponse)


@agent_tool(
    name="hr.list_contracts",
    summary="查询授权部门已通过与已同步合同台账",
    input_model=ContractInput,
    method="GET",
    path="/hr/contracts",
    page_keys=("hr:contracts:contracts-ledger",),
    risk_level="low",
    sensitivity="restricted",
)
async def list_contracts(context: ToolContext, data: ContractInput) -> dict[str, Any]:
    scope = await _department_scope(context, data.department)
    rows, total = await HrAgentQueryService(context.db).list_contracts(
        **data.model_dump(), dept_alias_set=scope
    )
    return _page_result(rows, total, data, ContractManagementResponse)


@agent_tool(
    name="hr.list_contract_approval_results",
    summary="查询授权部门合同审批结果",
    input_model=ApprovalResultInput,
    method="GET",
    path="/hr/contracts/approval-results",
    page_keys=("hr:contracts:contract-approval-results",),
    risk_level="low",
    sensitivity="restricted",
    output_hint="只查询已经完成的通过或拒绝结果，不执行合同审批。",
)
async def list_contract_approval_results(
    context: ToolContext, data: ApprovalResultInput
) -> dict[str, Any]:
    scope = await _department_scope(context, data.department)
    rows, total = await HrAgentQueryService(context.db).list_contract_approval_results(
        **data.model_dump(), dept_alias_set=scope
    )
    return _page_result(rows, total, data)


@agent_tool(
    name="hr.list_new_employee_training",
    summary="查询授权部门已生成的新员工培训计划",
    input_model=NewTrainingInput,
    method="GET",
    path="/hr/new-employee-training/plans",
    page_keys=("hr:training:new-employee-training",),
    risk_level="low",
    sensitivity="sensitive",
    output_hint="只返回已有计划，不生成新计划，不包含未生成计划的待培训员工。",
)
async def list_new_employee_training(
    context: ToolContext, data: NewTrainingInput
) -> dict[str, Any]:
    scope = await _department_scope(context, data.department)
    rows, total = await NewEmployeeTrainingService(context.db).list_plans(
        **data.model_dump(), dept_alias_set=scope
    )
    return _page_result(rows, total, data)


@agent_tool(
    name="hr.list_employee_training_summary",
    summary="查询授权部门员工培训清单汇总",
    input_model=EmployeeTrainingInput,
    method="GET",
    path="/hr/training/employee-training-list",
    page_keys=("hr:training:employee-training-list",),
    risk_level="low",
    sensitivity="sensitive",
)
async def list_employee_training_summary(
    context: ToolContext, data: EmployeeTrainingInput
) -> dict[str, Any]:
    await _department_scope(context, data.department)
    rows = await EmployeeTrainingListService(context.db).list_employee_training_summary(
        **data.model_dump(exclude={"page", "page_size"})
    )
    start = (data.page - 1) * data.page_size
    return _page_result(rows[start : start + data.page_size], len(rows), data)


@agent_tool(
    name="hr.list_trainers",
    summary="查询授权部门培训师及签到表培训师候选",
    input_model=DepartmentInput,
    method="GET",
    path="/hr/trainers",
    page_keys=("hr:training:trainer", "hr:training:sign-in-sheet"),
    risk_level="low",
    sensitivity="sensitive",
)
async def list_trainers(context: ToolContext, data: DepartmentInput) -> dict[str, Any]:
    scope = await _department_scope(context, data.department)
    rows, total = await TrainerService(context.db).list_trainers(
        **data.model_dump(), dept_alias_set=scope
    )
    return _page_result(rows, total, data, TrainerResponse)


@agent_tool(
    name="hr.list_position_training",
    summary="查询授权部门岗位培训清单",
    input_model=PositionTrainingInput,
    method="GET",
    path="/hr/position-training-lists",
    page_keys=("hr:training:position-training",),
    risk_level="low",
    sensitivity="sensitive",
)
async def list_position_training(
    context: ToolContext, data: PositionTrainingInput
) -> dict[str, Any]:
    scope = await _department_scope(context, data.department)
    rows, total = await PositionTrainingListService(context.db).list_lists(
        **data.model_dump(), dept_alias_set=scope
    )
    return _page_result(rows, total, data, PositionTrainingListResponse)


@agent_tool(
    name="hr.list_training_plan_tracking",
    summary="查询授权部门培训计划实施跟踪记录",
    input_model=TrackingInput,
    method="GET",
    path="/hr/plan-tracking",
    page_keys=("hr:training:plan-tracking",),
    risk_level="low",
    sensitivity="sensitive",
    output_hint="只查询已有实施跟踪记录，不执行按月同步或修改完成状态。",
)
async def list_training_plan_tracking(
    context: ToolContext, data: TrackingInput
) -> dict[str, Any]:
    scope = await _department_scope(context)
    rows, total = await PlanTrackingService(context.db).list_records(
        **data.model_dump(), dept_alias_set=scope
    )
    return _page_result(rows, total, data, PlanTrackingRecordResponse)
