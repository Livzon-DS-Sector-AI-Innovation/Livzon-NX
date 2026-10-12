from typing import Any, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.agent.tools import ToolContext, agent_tool
from app.modules.warehouse.ai_service import WarehouseAIService
from app.modules.warehouse.schemas import (
    PackagingMaterialResponse,
    ProductInventoryResponse,
    RawMaterialResponse,
    WarehouseFeishuRawRecordData,
    WarehouseFeishuTableResponse,
)
from app.modules.warehouse.service import WarehouseService
from app.platform.identity.page_policy import WAREHOUSE_MATERIAL_PAGE_ALIASES


class WarehouseSummaryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


@agent_tool(
    name="warehouse.get_inventory_summary",
    summary="查询仓储库存概览与缺货预警统计",
    risk_level="low",
    input_model=WarehouseSummaryInput,
    method="GET",
    path="/warehouse/ai/summary",
    page_keys=("warehouse:ai-analysis",),
    output_hint="按已有库存快照统计原辅料、包材及产品；不触发同步或模型调用。",
)
async def get_inventory_summary(
    context: ToolContext, _: WarehouseSummaryInput
) -> dict[str, Any]:
    return await WarehouseAIService(context.db).get_inventory_summary()


@agent_tool(
    name="warehouse.get_trend_summary",
    summary="查询物料周趋势异常统计",
    risk_level="low",
    input_model=WarehouseSummaryInput,
    method="GET",
    path="/warehouse/ai/trend-summary",
    page_keys=("warehouse:ai-analysis",),
    output_hint="返回已有规则的周趋势风险与物料分类计数，供人工分析参考。",
)
async def get_trend_summary(
    context: ToolContext, _: WarehouseSummaryInput
) -> dict[str, Any]:
    return await WarehouseAIService(context.db).get_trend_anomaly_summary()


@agent_tool(
    name="warehouse.get_hardware_cost_summary",
    summary="查询五金费用与异常车间统计",
    risk_level="low",
    input_model=WarehouseSummaryInput,
    method="GET",
    path="/warehouse/ai/hardware-cost-summary",
    page_keys=("warehouse:ai-analysis",),
    output_hint="当前月与历史均值费用采用现有异常车间口径，不代表全部车间费用总额。",
)
async def get_hardware_cost_summary(
    context: ToolContext, _: WarehouseSummaryInput
) -> dict[str, Any]:
    return await WarehouseAIService(context.db).get_hardware_cost_summary()


class WarehouseFeishuTablesInput(BaseModel):
    keyword: str | None = None


class WarehouseFeishuTableRecordsInput(BaseModel):
    table_id: UUID
    keyword: str | None = None
    field: str | None = None
    field_operator: str | None = None
    field_value: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


class WarehouseFeishuSyncInput(BaseModel):
    table_id: UUID


class WarehousePageRecordsInput(BaseModel):
    page_key: str = Field(
        min_length=1,
        max_length=100,
        description="仓储数据页别名，与 execution_context.page_key 的授权菜单一致",
        json_schema_extra={
            "enum": [
                alias for alias in sorted(set(WAREHOUSE_MATERIAL_PAGE_ALIASES.values()))
            ]
        },
    )
    keyword: str | None = Field(default=None, max_length=100)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @field_validator("page_key")
    @classmethod
    def validate_page_key(cls, value: str) -> str:
        if value not in WAREHOUSE_MATERIAL_PAGE_ALIASES.values():
            raise ValueError("仓储数据页别名不存在")
        return value


def _warehouse_service(context: ToolContext) -> WarehouseService:
    return WarehouseService(context.db)


def _raw_material(item: Any) -> dict[str, Any]:
    return RawMaterialResponse.model_validate(item).model_dump(mode="json")


def _packaging_material(item: Any) -> dict[str, Any]:
    return PackagingMaterialResponse.model_validate(item).model_dump(mode="json")


def _product(item: Any) -> dict[str, Any]:
    return ProductInventoryResponse.model_validate(item).model_dump(mode="json")


def _table(item: Any) -> dict[str, Any]:
    return WarehouseFeishuTableResponse.model_validate(item).model_dump(mode="json")


def _record_data(data: WarehouseFeishuRawRecordData) -> dict[str, Any]:
    return data.model_dump(mode="json")


@agent_tool(
    name="warehouse.list_page_records",
    summary="查询仓储原辅料、包材、五金及产品页面台账",
    input_model=WarehousePageRecordsInput,
    method="GET",
    path="/warehouse/feishu/material-pages/{page_key}",
    page_keys=tuple(WAREHOUSE_MATERIAL_PAGE_ALIASES),
    output_hint=(
        "page_key 使用仓储数据页别名；execution_context.page_key 指定授权菜单页。"
        "只查询本地镜像，保留页面和部门隔离，不触发同步。"
    ),
)
async def list_page_records(
    context: ToolContext,
    data: WarehousePageRecordsInput,
) -> dict[str, Any]:
    result = await _warehouse_service(context).get_feishu_material_page(
        data.page_key,
        keyword=data.keyword,
        page=data.page,
        page_size=data.page_size,
        source="local",
    )
    return result.model_dump(mode="json")


@agent_tool(
    name="warehouse.list_raw_materials",
    summary="查询原辅料库存",
    method="GET",
    path="/warehouse/raw-materials",
    page_keys=("warehouse:materials:raw-summary",),
    output_hint="返回原辅料库存条目列表。",
)
async def list_raw_materials(
    context: ToolContext, _: BaseModel
) -> list[dict[str, Any]]:
    items = await _warehouse_service(context).list_raw_materials()
    return [_raw_material(item) for item in items]


@agent_tool(
    name="warehouse.list_packaging_materials",
    summary="查询包材库存",
    method="GET",
    path="/warehouse/packaging-materials",
    page_keys=("warehouse:materials:packaging-summary",),
    output_hint="返回包材库存条目列表。",
)
async def list_packaging_materials(
    context: ToolContext, _: BaseModel
) -> list[dict[str, Any]]:
    items = await _warehouse_service(context).list_packaging_materials()
    return [_packaging_material(item) for item in items]


@agent_tool(
    name="warehouse.list_products",
    summary="查询产品库存",
    method="GET",
    path="/warehouse/products",
    page_keys=("warehouse:product-inventory:product-summary",),
    output_hint="返回产品库存条目列表。",
)
async def list_products(context: ToolContext, _: BaseModel) -> list[dict[str, Any]]:
    items = await _warehouse_service(context).list_products()
    return [_product(item) for item in items]


@agent_tool(
    name="warehouse.list_feishu_tables",
    summary="查询仓储飞书表目录",
    input_model=WarehouseFeishuTablesInput,
    method="GET",
    path="/warehouse/feishu/tables",
    page_keys=("warehouse:warehouse-settings",),
)
async def list_feishu_tables(
    context: ToolContext, data: WarehouseFeishuTablesInput
) -> list[dict[str, Any]]:
    items = await _warehouse_service(context).list_feishu_tables(keyword=data.keyword)
    return [_table(item) for item in items]


@agent_tool(
    name="warehouse.get_feishu_table_records",
    summary="查询飞书表本地记录",
    input_model=WarehouseFeishuTableRecordsInput,
    method="GET",
    path="/warehouse/feishu/tables/{table_id}/records",
    page_keys=("warehouse:warehouse-settings",),
)
async def get_feishu_table_records(
    context: ToolContext, data: WarehouseFeishuTableRecordsInput
) -> dict[str, Any]:
    result = await _warehouse_service(context).get_feishu_table_records(
        data.table_id,
        keyword=data.keyword,
        field=data.field,
        field_operator=data.field_operator,
        field_value=data.field_value,
        page=data.page,
        page_size=data.page_size,
    )
    return _record_data(result)


@agent_tool(
    name="warehouse.get_feishu_ws_status",
    summary="查询仓储飞书 WebSocket 状态",
    method="GET",
    path="/warehouse/feishu/ws/status",
    page_keys=("warehouse:warehouse-settings",),
)
async def get_feishu_ws_status(context: ToolContext, _: BaseModel) -> dict[str, Any]:
    from app.modules.warehouse.ws_client import get_ws_status

    return (await get_ws_status()).model_dump(mode="json")


@agent_tool(
    name="warehouse.sync_feishu_table",
    summary="同步仓储飞书表",
    input_model=WarehouseFeishuSyncInput,
    write=True,
    risk_level="medium",
    method="POST",
    path="/warehouse/feishu/tables/{table_id}/sync",
    page_keys=("warehouse:warehouse-settings",),
    sensitive_action="sync_config",
)
async def sync_feishu_table(
    context: ToolContext, data: WarehouseFeishuSyncInput
) -> dict[str, Any]:
    result = await _warehouse_service(context).sync_feishu_table(data.table_id)
    return cast(dict[str, Any], result.model_dump(mode="json"))


@agent_tool(
    name="warehouse.restart_feishu_ws",
    summary="重启仓储飞书 WebSocket",
    write=True,
    risk_level="high",
    workflow_allowed=False,
    human_decision_required=True,
    method="POST",
    path="/warehouse/feishu/ws/restart",
    page_keys=("warehouse:warehouse-settings",),
    sensitive_action="sync_config",
)
async def restart_feishu_ws(context: ToolContext, _: BaseModel) -> dict[str, Any]:
    from app.modules.warehouse.ws_client import restart_ws_from_db

    return (await restart_ws_from_db()).model_dump(mode="json")
