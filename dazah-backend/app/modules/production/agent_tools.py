"""Production adapters for the trusted Livzon tool executor."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.exceptions import NotFoundException
from app.modules.agent.tools import ToolContext, agent_tool
from app.modules.production.ipc_schemas import IpcAnalysisInput, IpcAnalysisResult
from app.modules.production.ipc_service import IpcAnalysisService
from app.modules.production.label_verification_service import LabelVerificationService
from app.modules.production.nce_schemas import NCEResponse
from app.modules.production.nce_service import NCEService
from app.modules.production.pressure_service import PressureService
from app.modules.production.schemas import (
    BatchResponse,
    ProductionPlanResponse,
    SalesPlanDetailResponse,
)
from app.modules.production.service import ProductionService
from app.modules.production.shift_handover_schemas import ShiftHandoverResponse
from app.modules.production.shift_handover_service import ShiftHandoverService
from app.modules.production.shift_log_schemas import ShiftLogResponse
from app.modules.production.shift_log_service import ShiftLogService
from app.platform.identity.page_policy import PAGES_BY_MODULE

_BATCH_PAGES = tuple(
    p.page_key
    for p in PAGES_BY_MODULE["production"]
    if p.page_key.startswith("production:batches:")
)


class PageInput(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class BatchListInput(PageInput):
    status: str | None = None
    product_code: str | None = None
    batch_no: str | None = None
    exclude_cancelled: bool = False


class SalesPlanInput(PageInput):
    product_name: str | None = Field(default=None, max_length=255)
    month: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class ShiftLogInput(PageInput):
    workshop: str | None = Field(default=None, max_length=100)
    shift: str | None = Field(default=None, max_length=32)
    date_from: date | None = None
    date_to: date | None = None


class HandoverInput(PageInput):
    workshop: str | None = Field(default=None, max_length=100)
    position: str | None = Field(default=None, max_length=100)
    date_from: date | None = None
    date_to: date | None = None


class NceInput(PageInput):
    workshop: str | None = Field(default=None, max_length=100)
    event_type: str | None = Field(default=None, max_length=100)
    date_from: date | None = None
    date_to: date | None = None


@agent_tool(
    name="production.list_sales_plan_details",
    summary="查询销售计划与概览销售明细",
    input_model=SalesPlanInput,
    method="GET",
    path="/production/sales-plan-details",
    page_keys=("production:overview", "production:plan:sales-plan"),
    output_hint="概览查询需 sales_plan 卡片授权；多页面授权时提供明确页面上下文。",
)
async def list_sales_plan_details(
    context: ToolContext,
    data: SalesPlanInput,
) -> dict[str, Any]:
    rows, total = await ProductionService(context.db).get_sales_plan_details(
        **data.model_dump(),
    )
    return {
        "data": [
            SalesPlanDetailResponse.model_validate(row).model_dump(mode="json")
            for row in rows
        ],
        "meta": {"page": data.page, "page_size": data.page_size, "total": total},
    }


@agent_tool(
    name="production.list_nonconforming_events",
    summary="查询运行偏差与非密事件",
    input_model=NceInput,
    method="GET",
    path="/production/non-conforming-events",
    page_keys=("production:shift-log:shift-log-deviation",),
)
async def list_nonconforming_events(
    context: ToolContext,
    data: NceInput,
) -> dict[str, Any]:
    rows, total = await NCEService(context.db).list_records(
        **data.model_dump(mode="json")
    )
    return {
        "data": [
            NCEResponse.model_validate(row).model_dump(mode="json") for row in rows
        ],
        "meta": {"page": data.page, "page_size": data.page_size, "total": total},
    }


@agent_tool(
    name="production.list_shift_logs",
    summary="查询班次生产运行日志",
    input_model=ShiftLogInput,
    method="GET",
    path="/production/shift-logs",
    page_keys=("production:shift-log:shift-log-summary",),
    output_hint="返回已有生产日志；尚不包含待开发的班次物料与能耗自动配平。",
)
async def list_shift_logs(context: ToolContext, data: ShiftLogInput) -> dict[str, Any]:
    rows, total = await ShiftLogService(context.db).list_records(
        **data.model_dump(mode="json")
    )
    return {
        "data": [
            ShiftLogResponse.model_validate(row).model_dump(mode="json") for row in rows
        ],
        "meta": {"page": data.page, "page_size": data.page_size, "total": total},
    }


@agent_tool(
    name="production.list_shift_handovers",
    summary="查询班组交接记录及确认状态",
    input_model=HandoverInput,
    method="GET",
    path="/production/shift-handovers",
    page_keys=("production:shift-log:shift-log-handover",),
)
async def list_shift_handovers(
    context: ToolContext,
    data: HandoverInput,
) -> dict[str, Any]:
    rows, total = await ShiftHandoverService(context.db).list_records(
        **data.model_dump(mode="json")
    )
    return {
        "data": [
            ShiftHandoverResponse.model_validate(row).model_dump(mode="json")
            for row in rows
        ],
        "meta": {"page": data.page, "page_size": data.page_size, "total": total},
    }


@agent_tool(
    name="production.summarize_ipc_samples",
    summary="校验与汇总中间体质控输入数据",
    input_model=IpcAnalysisInput,
    page_keys=("production:shift-log:shift-log-quality",),
    output_hint="只处理用户提交的IPC样本，不读取浏览器暂存数据，不保存台账。",
)
async def summarize_ipc_samples(
    context: ToolContext,
    data: IpcAnalysisInput,
) -> IpcAnalysisResult:
    return IpcAnalysisService.summarize(data)


class BatchIdInput(BaseModel):
    batch_id: UUID


class PlanListInput(PageInput):
    product_name: str | None = None
    workshop: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


class PressureListInput(PageInput):
    area: str | None = None
    point_id: str | None = None
    input_type: str | None = None
    status: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None


class LabelListInput(PageInput):
    batch_number: str | None = None
    product_name: str | None = None
    result_status: str | None = None
    start_date: date | None = None
    end_date: date | None = None


@agent_tool(
    name="production.list_batches",
    summary="查询授权车间生产批次",
    input_model=BatchListInput,
    method="GET",
    path="/production/batches",
    page_keys=_BATCH_PAGES,
)
async def list_batches(context: ToolContext, data: BatchListInput) -> dict[str, Any]:
    rows, total = await ProductionService(context.db).get_batches(
        skip=(data.page - 1) * data.page_size,
        limit=data.page_size,
        **data.model_dump(exclude={"page", "page_size"}),
    )
    return {
        "data": [
            BatchResponse.model_validate(row).model_dump(mode="json") for row in rows
        ],
        "meta": {"page": data.page, "page_size": data.page_size, "total": total},
    }


@agent_tool(
    name="production.get_batch",
    summary="查看授权车间批次详情",
    input_model=BatchIdInput,
    method="GET",
    path="/production/batches/{batch_id}",
    page_keys=_BATCH_PAGES,
)
async def get_batch(context: ToolContext, data: BatchIdInput) -> dict[str, Any]:
    row = await ProductionService(context.db).get_batch(data.batch_id)
    if row is None:
        raise NotFoundException("当前授权范围内的批次")
    return BatchResponse.model_validate(row).model_dump(mode="json")


@agent_tool(
    name="production.list_plans",
    summary="查询生产排产计划",
    input_model=PlanListInput,
    method="GET",
    path="/production/plans",
    page_keys=("production:plan:scheduling",),
)
async def list_plans(context: ToolContext, data: PlanListInput) -> dict[str, Any]:
    rows, total = await ProductionService(context.db).get_plans(
        skip=(data.page - 1) * data.page_size,
        limit=data.page_size,
        **data.model_dump(exclude={"page", "page_size"}),
    )
    return {
        "data": [
            ProductionPlanResponse.model_validate(row).model_dump(mode="json")
            for row in rows
        ],
        "meta": {"page": data.page, "page_size": data.page_size, "total": total},
    }


@agent_tool(
    name="production.list_pressure_records",
    summary="查询压差监测记录",
    input_model=PressureListInput,
    method="GET",
    path="/production/pressure/records",
    page_keys=("production:pressure",),
)
async def list_pressure_records(
    context: ToolContext,
    data: PressureListInput,
) -> dict[str, Any]:
    rows, total = await PressureService(context.db).list_records(**data.model_dump())
    return {
        "data": [row.model_dump(mode="json") for row in rows],
        "meta": {"page": data.page, "page_size": data.page_size, "total": total},
    }


@agent_tool(
    name="production.list_label_verifications",
    summary="查询标签复核记录",
    input_model=LabelListInput,
    method="GET",
    path="/production/label-verification",
    page_keys=("production:label-verification",),
)
async def list_label_verifications(
    context: ToolContext,
    data: LabelListInput,
) -> dict[str, Any]:
    rows, total = await LabelVerificationService(context.db).list_verifications(
        **data.model_dump(),
    )
    return {
        "data": [row.model_dump(mode="json") for row in rows],
        "meta": {"page": data.page, "page_size": data.page_size, "total": total},
    }
