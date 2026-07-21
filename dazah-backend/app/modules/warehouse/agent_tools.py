from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.agent.tools import ToolContext, agent_tool
from app.modules.warehouse.schemas import (
    PackagingMaterialResponse,
    ProductInventoryResponse,
    RawMaterialResponse,
    WarehouseFeishuRawRecordData,
    WarehouseFeishuTableBatchEnablePayload,
    WarehouseFeishuTableEnablePayload,
    WarehouseFeishuTableResponse,
)
from app.modules.warehouse.service import WarehouseService


class WarehouseFeishuTablesInput(BaseModel):
    business_domain: str | None = None
    keyword: str | None = None
    enabled: bool | None = None


class WarehouseFeishuTableRecordsInput(BaseModel):
    table_id: UUID
    keyword: str | None = None
    field: str | None = None
    field_operator: str | None = None
    field_value: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


class WarehouseFeishuDomainRecordsInput(BaseModel):
    business_domain: str
    table_id: UUID | None = None
    keyword: str | None = None
    field: str | None = None
    field_operator: str | None = None
    field_value: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


class WarehouseFeishuTableEnableInput(BaseModel):
    table_id: UUID
    is_enabled: bool


class WarehouseFeishuTablesEnableInput(BaseModel):
    table_ids: list[UUID] = Field(default_factory=list)
    is_enabled: bool


class WarehouseFeishuSyncInput(BaseModel):
    table_id: UUID


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
    name="warehouse.list_raw_materials",
    summary="查询原辅料库存",
    method="GET",
    path="/warehouse/raw-materials",
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
)
async def list_feishu_tables(
    context: ToolContext, data: WarehouseFeishuTablesInput
) -> list[dict[str, Any]]:
    items = await _warehouse_service(context).list_feishu_tables(
        business_domain=data.business_domain,
        keyword=data.keyword,
        enabled=data.enabled,
    )
    return [_table(item) for item in items]


@agent_tool(
    name="warehouse.get_feishu_table_records",
    summary="查询飞书表本地记录",
    input_model=WarehouseFeishuTableRecordsInput,
    method="GET",
    path="/warehouse/feishu/tables/{table_id}/records",
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
    name="warehouse.get_feishu_domain_records",
    summary="查询仓储飞书领域记录",
    input_model=WarehouseFeishuDomainRecordsInput,
    method="GET",
    path="/warehouse/feishu/domains/{business_domain}/records",
)
async def get_feishu_domain_records(
    context: ToolContext, data: WarehouseFeishuDomainRecordsInput
) -> dict[str, Any]:
    result = await _warehouse_service(context).get_feishu_domain_records(
        data.business_domain,  # type: ignore[arg-type]
        table_id=data.table_id,
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
)
async def get_feishu_ws_status(context: ToolContext, _: BaseModel) -> dict[str, Any]:
    from app.modules.warehouse.ws_client import get_ws_status

    return (await get_ws_status()).model_dump(mode="json")


@agent_tool(
    name="warehouse.refresh_feishu_tables",
    summary="刷新仓储飞书表目录",
    write=True,
    risk_level="low",
    method="POST",
    path="/warehouse/feishu/tables/refresh",
)
async def refresh_feishu_tables(
    context: ToolContext, _: BaseModel
) -> list[dict[str, Any]]:
    items = await _warehouse_service(context).refresh_feishu_tables()
    return [_table(item) for item in items]


@agent_tool(
    name="warehouse.set_feishu_tables_enabled",
    summary="批量启停仓储飞书表",
    input_model=WarehouseFeishuTablesEnableInput,
    write=True,
    risk_level="medium",
    method="POST",
    path="/warehouse/feishu/tables/enabled/batch",
)
async def set_feishu_tables_enabled(
    context: ToolContext, data: WarehouseFeishuTablesEnableInput
) -> list[dict[str, Any]]:
    payload = WarehouseFeishuTableBatchEnablePayload(
        table_ids=data.table_ids,
        is_enabled=data.is_enabled,
    )
    items = await _warehouse_service(context).set_feishu_tables_enabled(
        payload.table_ids,
        payload.is_enabled,
    )
    return [_table(item) for item in items]


@agent_tool(
    name="warehouse.set_feishu_table_enabled",
    summary="启停仓储飞书表",
    input_model=WarehouseFeishuTableEnableInput,
    write=True,
    risk_level="medium",
    method="PATCH",
    path="/warehouse/feishu/tables/{table_id}/enabled",
)
async def set_feishu_table_enabled(
    context: ToolContext, data: WarehouseFeishuTableEnableInput
) -> dict[str, Any]:
    payload = WarehouseFeishuTableEnablePayload(is_enabled=data.is_enabled)
    table = await _warehouse_service(context).set_feishu_table_enabled(
        data.table_id,
        payload.is_enabled,
    )
    return _table(table)


@agent_tool(
    name="warehouse.sync_feishu_table",
    summary="同步仓储飞书表",
    input_model=WarehouseFeishuSyncInput,
    write=True,
    risk_level="medium",
    method="POST",
    path="/warehouse/feishu/tables/{table_id}/sync",
)
async def sync_feishu_table(
    context: ToolContext, data: WarehouseFeishuSyncInput
) -> dict[str, Any]:
    result = await _warehouse_service(context).sync_feishu_table(data.table_id)
    return result.model_dump(mode="json")


@agent_tool(
    name="warehouse.restart_feishu_ws",
    summary="重启仓储飞书 WebSocket",
    write=True,
    risk_level="high",
    workflow_allowed=False,
    human_decision_required=True,
    method="POST",
    path="/warehouse/feishu/ws/restart",
)
async def restart_feishu_ws(context: ToolContext, _: BaseModel) -> dict[str, Any]:
    from app.modules.warehouse.ws_client import restart_ws_from_db

    return (await restart_ws_from_db()).model_dump(mode="json")
