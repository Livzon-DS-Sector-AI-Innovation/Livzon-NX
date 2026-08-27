from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, model_validator

from app.modules.agent.tools import ToolContext, agent_tool
from app.modules.energy.schemas import (
    EnergyFeishuConfigResponse,
    EnergyFeishuConnectivityResult,
    EnergyFeishuSourceRootInput,
    EnergyFeishuSourceRootResponse,
    EnergyFeishuSourceRootUpdate,
    EnergyOverviewResponse,
    EnergySheetMappingResponse,
    EnergySnapshotResponse,
    EnergySnapshotRowResponse,
    EnergySourceBatchRequest,
    EnergySourceDeleteResult,
    EnergySourceDocumentResponse,
    EnergySourceSheetResponse,
    EnergySyncRunResponse,
)
from app.modules.energy.wiki_service import EnergyWikiService


class EnergyPageInput(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class EnergySourceFilterInput(BaseModel):
    period_month: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    mapping_status: str | None = None


class EnergyDocumentFilterInput(BaseModel):
    period_month: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")


class EnergySheetInput(BaseModel):
    sheet_id: UUID


class EnergySnapshotRowsInput(BaseModel):
    snapshot_id: UUID
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


class EnergyOverviewInput(BaseModel):
    start_time: datetime
    end_time: datetime
    energy_type: str | None = None
    group_by: str | None = None
    source_scope: Literal["detail", "daily_summary", "energy_summary"] = "detail"
    workshop: str | None = Field(default=None, max_length=128)
    source_sheet_title: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def validate_time_range(self) -> EnergyOverviewInput:
        timezone = ZoneInfo("Asia/Shanghai")
        start_time = (
            self.start_time
            if self.start_time.tzinfo is not None
            else self.start_time.replace(tzinfo=timezone)
        )
        end_time = (
            self.end_time
            if self.end_time.tzinfo is not None
            else self.end_time.replace(tzinfo=timezone)
        )
        if end_time < start_time:
            raise ValueError("end_time 不能早于 start_time")
        return self


class EnergySyncInput(BaseModel):
    force: bool = False


class EnergySourceRootCreateInput(EnergyFeishuSourceRootInput):
    pass


class EnergySourceRootUpdateInput(EnergyFeishuSourceRootUpdate):
    root_id: UUID


class EnergySourceRootDeleteInput(BaseModel):
    root_id: UUID


def _service(context: ToolContext) -> EnergyWikiService:
    return EnergyWikiService(context.db)


def _dump(item: BaseModel) -> dict[str, Any]:
    return item.model_dump(mode="json")


@agent_tool(
    name="energy.get_feishu_config",
    summary="读取能源模块飞书配置摘要",
    required_roles=("admin",),
    method="GET",
    path="/energy/feishu-config",
    sensitivity="sensitive",
    output_hint="返回能源飞书配置、同步状态和密钥配置状态；不会返回飞书应用密钥明文。",
)
async def get_feishu_config(context: ToolContext, _: BaseModel) -> dict[str, Any]:
    result = await _service(context).get_config()
    return _dump(EnergyFeishuConfigResponse.model_validate(result))


@agent_tool(
    name="energy.list_feishu_source_roots",
    summary="查询能源模块飞书数据入口",
    required_roles=("admin",),
    method="GET",
    path="/energy/feishu/roots",
    sensitivity="sensitive",
    output_hint="返回能源模块已配置的 Wiki、电子表格或多维表格入口。",
)
async def list_feishu_source_roots(
    context: ToolContext, _: BaseModel
) -> list[dict[str, Any]]:
    items = await _service(context).list_source_roots()
    return [
        _dump(EnergyFeishuSourceRootResponse.model_validate(item)) for item in items
    ]


@agent_tool(
    name="energy.create_feishu_source_root",
    summary="新增能源飞书数据表入口",
    input_model=EnergySourceRootCreateInput,
    write=True,
    risk_level="medium",
    required_roles=("admin",),
    workflow_allowed=False,
    method="POST",
    path="/energy/feishu/roots",
    sensitivity="sensitive",
    output_hint=(
        "生成待确认项；确认后新增一个 Wiki、电子表格或多维表格入口，"
        "不会创建或修改飞书原表。"
    ),
)
async def create_feishu_source_root(
    context: ToolContext,
    data: EnergySourceRootCreateInput,
) -> dict[str, Any]:
    item = await _service(context).create_source_root(
        EnergyFeishuSourceRootInput.model_validate(data.model_dump())
    )
    return _dump(item)


@agent_tool(
    name="energy.update_feishu_source_root",
    summary="修改能源飞书数据表入口配置",
    input_model=EnergySourceRootUpdateInput,
    write=True,
    risk_level="medium",
    required_roles=("admin",),
    workflow_allowed=False,
    method="PUT",
    path="/energy/feishu/roots/{root_id}",
    sensitivity="sensitive",
    output_hint=(
        "生成待确认项；确认后修改入口名称、类型、链接或启用状态，不会修改飞书原表内容。"
    ),
)
async def update_feishu_source_root(
    context: ToolContext,
    data: EnergySourceRootUpdateInput,
) -> dict[str, Any]:
    item = await _service(context).update_source_root(
        data.root_id,
        EnergyFeishuSourceRootUpdate.model_validate(
            data.model_dump(exclude={"root_id"})
        ),
    )
    return _dump(item)


@agent_tool(
    name="energy.delete_feishu_source_root",
    summary="删除能源飞书数据表入口配置",
    input_model=EnergySourceRootDeleteInput,
    write=True,
    risk_level="high",
    required_roles=("admin",),
    workflow_allowed=False,
    method="DELETE",
    path="/energy/feishu/roots/{root_id}",
    sensitivity="sensitive",
    output_hint=(
        "生成高风险待确认项；确认后停用并移除本地入口配置，"
        "不会删除飞书原表，也不会自动清除已同步快照。"
    ),
)
async def delete_feishu_source_root(
    context: ToolContext,
    data: EnergySourceRootDeleteInput,
) -> dict[str, Any]:
    await _service(context).delete_source_root(data.root_id)
    return {"id": str(data.root_id), "deleted": True}


@agent_tool(
    name="energy.delete_source_sheets",
    summary="删除能源飞书资源目录中的数据表及本地数据",
    input_model=EnergySourceBatchRequest,
    write=True,
    risk_level="high",
    required_roles=("admin",),
    workflow_allowed=False,
    method="DELETE",
    path="/energy/sources/batch",
    sensitivity="sensitive",
    output_hint=(
        "生成高风险待确认项；确认后永久删除所选数据表在 Dazah 中的"
        "页面映射、字段映射、指标事实、快照和数据库记录，不删除飞书原表。"
    ),
)
async def delete_source_sheets(
    context: ToolContext,
    data: EnergySourceBatchRequest,
) -> dict[str, Any]:
    result = await _service(context).delete_sources(data.sheet_ids)
    return _dump(EnergySourceDeleteResult.model_validate(result))


@agent_tool(
    name="energy.test_feishu_connectivity",
    summary="检查能源模块飞书配置连通性",
    required_roles=("admin",),
    method="POST",
    path="/energy/feishu-config/test",
    sensitivity="sensitive",
    workflow_allowed=False,
    timeout_seconds=60,
    output_hint="返回飞书应用、入口和数据表读取能力的分步检查结果。",
)
async def test_feishu_connectivity(
    context: ToolContext, _: BaseModel
) -> dict[str, Any]:
    result = await _service(context).test_connectivity()
    return _dump(EnergyFeishuConnectivityResult.model_validate(result))


@agent_tool(
    name="energy.list_sync_runs",
    summary="查询能源飞书同步记录",
    input_model=EnergyPageInput,
    method="GET",
    path="/energy/sync-runs",
    output_hint="分页返回能源飞书同步运行记录和处理数量。",
)
async def list_sync_runs(context: ToolContext, data: EnergyPageInput) -> dict[str, Any]:
    items, total = await _service(context).list_sync_runs(
        page=data.page,
        page_size=data.page_size,
    )
    return {
        "items": [_dump(EnergySyncRunResponse.model_validate(item)) for item in items],
        "total": total,
        "page": data.page,
        "page_size": data.page_size,
    }


@agent_tool(
    name="energy.list_source_documents",
    summary="查询能源飞书来源文档",
    input_model=EnergyDocumentFilterInput,
    method="GET",
    path="/energy/sources/documents",
    output_hint="返回已发现的能源 Wiki、电子表格或多维表格来源文档。",
)
async def list_source_documents(
    context: ToolContext, data: EnergyDocumentFilterInput
) -> list[dict[str, Any]]:
    items = await _service(context).list_documents(period_month=data.period_month)
    return [_dump(EnergySourceDocumentResponse.model_validate(item)) for item in items]


@agent_tool(
    name="energy.list_source_sheets",
    summary="查询能源飞书数据表信息",
    input_model=EnergySourceFilterInput,
    method="GET",
    path="/energy/sources",
    output_hint="返回能源数据表、表头、映射状态、来源文档和最新快照信息。",
)
async def list_source_sheets(
    context: ToolContext, data: EnergySourceFilterInput
) -> list[dict[str, Any]]:
    service = _service(context)
    rows = await service.list_sources(
        period_month=data.period_month,
        mapping_status=data.mapping_status,
    )
    result: list[dict[str, Any]] = []
    for sheet, document in rows:
        mapping = await service.get_mapping(sheet.id)
        result.append(
            _dump(
                EnergySourceSheetResponse(
                    **EnergySourceSheetResponse.model_validate(sheet).model_dump(
                        exclude={
                            "source_role",
                            "document_title",
                            "period_month",
                        }
                    ),
                    source_role=mapping.source_role if mapping else None,
                    document_title=document.title,
                    period_month=document.period_month,
                )
            )
        )
    return result


@agent_tool(
    name="energy.list_sheet_snapshots",
    summary="查询能源数据表快照",
    input_model=EnergySheetInput,
    method="GET",
    path="/energy/sources/{sheet_id}/snapshots",
    output_hint="返回指定能源数据表的历史快照。",
)
async def list_sheet_snapshots(
    context: ToolContext, data: EnergySheetInput
) -> list[dict[str, Any]]:
    items = await _service(context).list_snapshots(data.sheet_id)
    return [_dump(EnergySnapshotResponse.model_validate(item)) for item in items]


@agent_tool(
    name="energy.get_sheet_mapping",
    summary="读取能源数据表字段映射",
    input_model=EnergySheetInput,
    method="GET",
    path="/energy/sources/{sheet_id}/mapping",
    output_hint="返回指定能源数据表当前生效的字段映射；未配置时返回空值。",
)
async def get_sheet_mapping(
    context: ToolContext, data: EnergySheetInput
) -> dict[str, Any] | None:
    item = await _service(context).get_mapping(data.sheet_id)
    if item is None:
        return None
    return _dump(EnergySheetMappingResponse.model_validate(item))


@agent_tool(
    name="energy.list_snapshot_rows",
    summary="分页读取能源数据表快照行",
    input_model=EnergySnapshotRowsInput,
    method="GET",
    path="/energy/snapshots/{snapshot_id}/rows",
    output_hint="分页返回指定能源数据表快照中的原始行数据。",
)
async def list_snapshot_rows(
    context: ToolContext, data: EnergySnapshotRowsInput
) -> dict[str, Any]:
    snapshot, rows, total = await _service(context).list_snapshot_rows(
        snapshot_id=data.snapshot_id,
        page=data.page,
        page_size=data.page_size,
    )
    return {
        "snapshot": _dump(EnergySnapshotResponse.model_validate(snapshot)),
        "rows": [
            _dump(EnergySnapshotRowResponse.model_validate(item)) for item in rows
        ],
        "total": total,
        "page": data.page,
        "page_size": data.page_size,
    }


@agent_tool(
    name="energy.get_overview",
    summary="查询能源分析总览",
    input_model=EnergyOverviewInput,
    method="GET",
    path="/energy/overview",
    output_hint="返回指定时间范围的能源汇总、趋势、分布和最新指标。",
)
async def get_overview(
    context: ToolContext, data: EnergyOverviewInput
) -> dict[str, Any]:
    result = await _service(context).get_overview(
        start=data.start_time,
        end=data.end_time,
        energy_type=data.energy_type,
        group_by=data.group_by,
        source_scope=data.source_scope,
        workshop=data.workshop,
        source_sheet_title=data.source_sheet_title,
    )
    return _dump(EnergyOverviewResponse.model_validate(result))


@agent_tool(
    name="energy.trigger_sync",
    summary="手动触发能源飞书数据同步",
    input_model=EnergySyncInput,
    write=True,
    risk_level="medium",
    required_roles=("admin",),
    method="POST",
    path="/energy/sync-runs",
    timeout_seconds=120,
    output_hint="生成待确认项；确认执行后返回本次能源飞书同步运行结果。",
)
async def trigger_sync(context: ToolContext, data: EnergySyncInput) -> dict[str, Any]:
    item = await _service(context).trigger_sync(force=data.force)
    return _dump(EnergySyncRunResponse.model_validate(item))
