from uuid import UUID

from fastapi import Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.response import success_response
from app.modules.warehouse.schemas import (
    PackagingMaterialListResponse,
    PackagingMaterialResponse,
    ProductInventoryListResponse,
    ProductInventoryResponse,
    RawMaterialListResponse,
    RawMaterialResponse,
    WarehouseAnalysisProfileApiResponse,
    WarehouseAnalysisProfileInput,
    WarehouseAnalysisRunApiResponse,
    WarehouseAnalyticsApiResponse,
    WarehouseAnalyticsQuery,
    WarehouseDatasetApiResponse,
    WarehouseDatasetRecordApiResponse,
    WarehouseFieldValuesApiResponse,
    WarehouseFeishuConfigApiResponse,
    WarehouseFeishuConfigUpsert,
    WarehouseFeishuConnectivityApiResponse,
    WarehouseFeishuRawRecordApiResponse,
    WarehouseFeishuPageBindingReplace,
    WarehouseFeishuPageDataApiResponse,
    WarehouseFeishuSourceRootApiResponse,
    WarehouseFeishuSourceRootInput,
    WarehouseFeishuSourceRootListApiResponse,
    WarehouseFeishuTableBatchEnableApiResponse,
    WarehouseFeishuTableBatchEnablePayload,
    WarehouseFeishuTableEnableApiResponse,
    WarehouseFeishuTableEnablePayload,
    WarehouseFeishuTableListApiResponse,
    WarehouseFeishuTableResponse,
    WarehouseFeishuTableSyncApiResponse,
    WarehouseFeishuWsStatusApiResponse,
    WarehousePromptVersionApiResponse,
    WarehousePromptVersionInput,
    WarehousePromptVersionListApiResponse,
)
from app.modules.warehouse.service import WarehouseService
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["warehouse"])


def get_warehouse_service(
    session: AsyncSession = Depends(get_db),
) -> WarehouseService:
    return WarehouseService(session)


@router.get(
    "/raw-materials",
    summary="原辅料库存列表",
    response_model=RawMaterialListResponse,
)
async def list_raw_materials(
    service: WarehouseService = Depends(get_warehouse_service),
):
    items = await service.list_raw_materials()
    data = [
        RawMaterialResponse.model_validate(item).model_dump(mode="json")
        for item in items
    ]
    return success_response(data=data)


@router.get(
    "/packaging-materials",
    summary="包材库存列表",
    response_model=PackagingMaterialListResponse,
)
async def list_packaging_materials(
    service: WarehouseService = Depends(get_warehouse_service),
):
    items = await service.list_packaging_materials()
    data = [
        PackagingMaterialResponse.model_validate(item).model_dump(mode="json")
        for item in items
    ]
    return success_response(data=data)


@router.get(
    "/products",
    summary="成品库存列表",
    response_model=ProductInventoryListResponse,
)
async def list_products(
    service: WarehouseService = Depends(get_warehouse_service),
):
    items = await service.list_products()
    data = [
        ProductInventoryResponse.model_validate(item).model_dump(mode="json")
        for item in items
    ]
    return success_response(data=data)


@router.get(
    "/feishu-config",
    summary="获取仓储飞书配置",
    response_model=WarehouseFeishuConfigApiResponse,
)
async def get_feishu_config(
    service: WarehouseService = Depends(get_warehouse_service),
):
    data = await service.get_feishu_config_response()
    return success_response(data=data.model_dump(mode="json"))


@router.put(
    "/feishu-config",
    summary="保存仓储飞书配置",
    response_model=WarehouseFeishuConfigApiResponse,
)
async def save_feishu_config(
    payload: WarehouseFeishuConfigUpsert,
    service: WarehouseService = Depends(get_warehouse_service),
):
    data = await service.save_feishu_config(payload)
    return success_response(data=data.model_dump(mode="json"))


@router.post(
    "/feishu-config/test",
    summary="测试仓储飞书连通性",
    response_model=WarehouseFeishuConnectivityApiResponse,
)
async def test_feishu_config(
    payload: WarehouseFeishuConfigUpsert | None = None,
    service: WarehouseService = Depends(get_warehouse_service),
):
    data = await service.test_feishu_connectivity(payload)
    return success_response(data=data.model_dump(mode="json"))


@router.get(
    "/feishu/tables",
    summary="获取仓储飞书数据表目录",
    response_model=WarehouseFeishuTableListApiResponse,
)
async def list_feishu_tables(
    business_domain: str | None = None,
    keyword: str | None = None,
    enabled: bool | None = None,
    service: WarehouseService = Depends(get_warehouse_service),
):
    items = await service.list_feishu_tables(
        business_domain=business_domain,
        keyword=keyword,
        enabled=enabled,
    )
    data = [
        WarehouseFeishuTableResponse.model_validate(item).model_dump(mode="json")
        for item in items
    ]
    return success_response(data=data)


@router.post(
    "/feishu/tables/refresh",
    summary="刷新仓储飞书数据表目录",
    response_model=WarehouseFeishuTableListApiResponse,
)
async def refresh_feishu_tables(
    service: WarehouseService = Depends(get_warehouse_service),
):
    items = await service.refresh_feishu_tables()
    data = [
        WarehouseFeishuTableResponse.model_validate(item).model_dump(mode="json")
        for item in items
    ]
    return success_response(data=data)


@router.post(
    "/feishu/tables/enabled/batch",
    summary="批量启用或停用仓储飞书数据表同步",
    response_model=WarehouseFeishuTableBatchEnableApiResponse,
)
async def set_feishu_tables_enabled(
    payload: WarehouseFeishuTableBatchEnablePayload,
    service: WarehouseService = Depends(get_warehouse_service),
):
    items = await service.set_feishu_tables_enabled(
        payload.table_ids,
        payload.is_enabled,
    )
    data = [
        WarehouseFeishuTableResponse.model_validate(item).model_dump(mode="json")
        for item in items
    ]
    return success_response(data=data)


@router.patch(
    "/feishu/tables/{table_id}/enabled",
    summary="启用或停用仓储飞书数据表同步",
    response_model=WarehouseFeishuTableEnableApiResponse,
)
async def set_feishu_table_enabled(
    table_id: UUID,
    payload: WarehouseFeishuTableEnablePayload,
    service: WarehouseService = Depends(get_warehouse_service),
):
    table = await service.set_feishu_table_enabled(table_id, payload.is_enabled)
    data = WarehouseFeishuTableResponse.model_validate(table).model_dump(mode="json")
    return success_response(data=data)


@router.post(
    "/feishu/tables/{table_id}/sync",
    summary="同步仓储飞书数据表记录快照",
    response_model=WarehouseFeishuTableSyncApiResponse,
)
async def sync_feishu_table(
    table_id: UUID,
    service: WarehouseService = Depends(get_warehouse_service),
):
    data = await service.sync_feishu_table(table_id)
    return success_response(data=data.model_dump(mode="json"))


@router.get(
    "/feishu/tables/{table_id}/records",
    summary="读取仓储飞书数据表本地记录快照",
    response_model=WarehouseFeishuRawRecordApiResponse,
)
async def get_feishu_table_records(
    table_id: UUID,
    keyword: str | None = None,
    field: str | None = None,
    field_operator: str | None = Query(
        default=None,
        description="字段筛选条件：contains/eq/ne/gt/gte/lt/lte",
    ),
    field_value: str | None = Query(default=None, description="字段筛选值"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    service: WarehouseService = Depends(get_warehouse_service),
):
    data = await service.get_feishu_table_records(
        table_id,
        keyword=keyword,
        field=field,
        field_operator=field_operator,
        field_value=field_value,
        page=page,
        page_size=page_size,
    )
    return success_response(data=data.model_dump(mode="json"))


@router.get(
    "/feishu/domains/{business_domain}/records",
    summary="读取仓储业务域启用表本地记录快照",
    response_model=WarehouseFeishuRawRecordApiResponse,
)
async def get_feishu_domain_records(
    business_domain: str,
    table_id: UUID | None = None,
    keyword: str | None = None,
    field: str | None = None,
    field_operator: str | None = Query(
        default=None,
        description="字段筛选条件：contains/eq/ne/gt/gte/lt/lte",
    ),
    field_value: str | None = Query(default=None, description="字段筛选值"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    service: WarehouseService = Depends(get_warehouse_service),
):
    data = await service.get_feishu_domain_records(
        business_domain,  # type: ignore[arg-type]
        table_id=table_id,
        keyword=keyword,
        field=field,
        field_operator=field_operator,
        field_value=field_value,
        page=page,
        page_size=page_size,
    )
    return success_response(data=data.model_dump(mode="json"))


@router.get(
    "/feishu/roots",
    summary="列出仓储飞书 Wiki/Base 数据入口",
    response_model=WarehouseFeishuSourceRootListApiResponse,
)
async def list_feishu_source_roots(
    service: WarehouseService = Depends(get_warehouse_service),
):
    items = await service.list_feishu_source_roots()
    return success_response(data=[item.model_dump(mode="json") for item in items])


@router.post(
    "/feishu/roots",
    summary="新增仓储飞书 Wiki/Base 数据入口",
    response_model=WarehouseFeishuSourceRootApiResponse,
)
async def create_feishu_source_root(
    payload: WarehouseFeishuSourceRootInput,
    service: WarehouseService = Depends(get_warehouse_service),
):
    item = await service.create_feishu_source_root(payload)
    return success_response(data=item.model_dump(mode="json"))


@router.delete(
    "/feishu/roots/{root_id}",
    summary="停用并删除仓储飞书数据入口",
)
async def delete_feishu_source_root(
    root_id: UUID,
    service: WarehouseService = Depends(get_warehouse_service),
):
    await service.delete_feishu_source_root(root_id)
    return success_response(data={"id": str(root_id)})


@router.post(
    "/feishu/roots/{root_id}/discover",
    summary="递归发现仓储飞书数据入口中的数据表",
    response_model=WarehouseFeishuTableListApiResponse,
)
async def discover_feishu_source_root(
    root_id: UUID,
    service: WarehouseService = Depends(get_warehouse_service),
):
    items = await service.discover_feishu_source_root(root_id)
    return success_response(
        data=[
            WarehouseFeishuTableResponse.model_validate(item).model_dump(mode="json")
            for item in items
        ]
    )


@router.get(
    "/page-data/{page_key}",
    summary="获取仓储菜单页面的数据表绑定",
    response_model=WarehouseFeishuPageDataApiResponse,
)
async def get_page_data(
    page_key: str,
    service: WarehouseService = Depends(get_warehouse_service),
):
    data = await service.get_page_data(page_key)
    return success_response(data=data.model_dump(mode="json"))


@router.put(
    "/page-data/{page_key}",
    summary="发布仓储菜单页面的数据表绑定",
    response_model=WarehouseFeishuPageDataApiResponse,
)
async def replace_page_data_bindings(
    page_key: str,
    payload: WarehouseFeishuPageBindingReplace,
    service: WarehouseService = Depends(get_warehouse_service),
):
    data = await service.replace_page_bindings(page_key, payload.bindings)
    return success_response(data=data.model_dump(mode="json"))


@router.get(
    "/page-data/{page_key}/{binding_id}/records",
    summary="分页读取仓储页面已绑定的本地飞书镜像",
    response_model=WarehouseDatasetApiResponse,
)
async def get_page_dataset_records(
    page_key: str,
    binding_id: UUID,
    keyword: str | None = None,
    field: str | None = None,
    field_operator: str | None = Query(default=None),
    field_value: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    filter_field: list[str] | None = Query(default=None),
    filter_operator: list[str] | None = Query(default=None),
    filter_value: list[str] | None = Query(default=None),
    sort_field: str | None = None,
    sort_direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    service: WarehouseService = Depends(get_warehouse_service),
):
    filter_fields = filter_field or []
    filter_operators = filter_operator or []
    filter_values = filter_value or []
    if not (
        len(filter_fields) == len(filter_operators) == len(filter_values)
    ):
        raise AppException(message="筛选字段、操作符和值的数量必须一致")
    data = await service.get_page_dataset(
        page_key=page_key,
        binding_id=binding_id,
        keyword=keyword,
        field=field,
        field_operator=field_operator,
        field_value=field_value,
        page=page,
        page_size=page_size,
        filters=list(zip(filter_fields, filter_operators, filter_values, strict=True)),
        sort_field_id=sort_field,
        sort_direction=sort_direction,
    )
    return success_response(data=data.model_dump(mode="json"))


@router.get(
    "/page-data/{page_key}/{binding_id}/field-values",
    summary="读取已登记字段的候选值",
    response_model=WarehouseFieldValuesApiResponse,
)
async def get_page_dataset_field_values(
    page_key: str,
    binding_id: UUID,
    field_id: str,
    keyword: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    service: WarehouseService = Depends(get_warehouse_service),
):
    data = await service.get_page_field_values(
        page_key=page_key,
        binding_id=binding_id,
        field_id=field_id,
        keyword=keyword,
        limit=limit,
    )
    return success_response(data=data.model_dump(mode="json"))


@router.get(
    "/page-data/{page_key}/{binding_id}/record/{record_id}",
    summary="读取单条本地镜像记录",
    response_model=WarehouseDatasetRecordApiResponse,
)
async def get_page_dataset_record(
    page_key: str,
    binding_id: UUID,
    record_id: str,
    service: WarehouseService = Depends(get_warehouse_service),
):
    data = await service.get_page_record(
        page_key=page_key,
        binding_id=binding_id,
        record_id=record_id,
    )
    return success_response(data=data.model_dump(mode="json"))


@router.get(
    "/page-data/{page_key}/{binding_id}/record/{record_id}/attachments/{field_id}/{file_token}",
    summary="经页面权限校验下载飞书附件",
)
async def download_page_dataset_attachment(
    page_key: str,
    binding_id: UUID,
    record_id: str,
    field_id: str,
    file_token: str,
    service: WarehouseService = Depends(get_warehouse_service),
):
    content, content_type, content_disposition = await service.download_page_attachment(
        page_key=page_key,
        binding_id=binding_id,
        record_id=record_id,
        field_id=field_id,
        file_token=file_token,
    )
    headers = {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    }
    if content_disposition and "\r" not in content_disposition and "\n" not in content_disposition:
        headers["Content-Disposition"] = content_disposition
    return Response(content=content, media_type=content_type, headers=headers)


@router.post(
    "/analytics/query",
    summary="聚合查询仓储本地飞书镜像",
    response_model=WarehouseAnalyticsApiResponse,
)
async def query_warehouse_analytics(
    payload: WarehouseAnalyticsQuery,
    service: WarehouseService = Depends(get_warehouse_service),
):
    data = await service.aggregate_page_dataset(payload)
    return success_response(data=data.model_dump(mode="json"))


@router.post(
    "/analysis/profiles",
    summary="创建仓储飞书数据分析配置及首个 Prompt 版本",
    response_model=WarehouseAnalysisProfileApiResponse,
)
async def create_warehouse_analysis_profile(
    payload: WarehouseAnalysisProfileInput,
    service: WarehouseService = Depends(get_warehouse_service),
):
    data = await service.create_analysis_profile(payload)
    return success_response(data=data.model_dump(mode="json"))


@router.get(
    "/analysis/profiles/{profile_id}/prompts",
    summary="查询分析 Prompt 版本历史",
    response_model=WarehousePromptVersionListApiResponse,
)
async def list_warehouse_prompt_versions(
    profile_id: UUID,
    service: WarehouseService = Depends(get_warehouse_service),
):
    data = await service.list_prompt_versions(profile_id)
    return success_response(data=[item.model_dump(mode="json") for item in data])


@router.post(
    "/analysis/profiles/{profile_id}/prompts",
    summary="创建分析 Prompt 草稿版本",
    response_model=WarehousePromptVersionApiResponse,
)
async def create_warehouse_prompt_draft(
    profile_id: UUID,
    payload: WarehousePromptVersionInput,
    service: WarehouseService = Depends(get_warehouse_service),
):
    data = await service.create_prompt_draft(profile_id, payload)
    return success_response(data=data.model_dump(mode="json"))


@router.post(
    "/analysis/profiles/{profile_id}/prompts/{prompt_id}/publish",
    summary="发布或回滚到指定 Prompt 版本",
    response_model=WarehousePromptVersionApiResponse,
)
async def publish_warehouse_prompt_version(
    profile_id: UUID,
    prompt_id: UUID,
    service: WarehouseService = Depends(get_warehouse_service),
):
    data = await service.publish_prompt_version(profile_id, prompt_id)
    return success_response(data=data.model_dump(mode="json"))


@router.post(
    "/analysis/profiles/{profile_id}/run",
    summary="运行仓储飞书数据算法与 AI 分析",
    response_model=WarehouseAnalysisRunApiResponse,
)
async def run_warehouse_analysis(
    profile_id: UUID,
    service: WarehouseService = Depends(get_warehouse_service),
):
    data = await service.enqueue_analysis(profile_id)
    return success_response(data=data.model_dump(mode="json"))


@router.get(
    "/analysis/runs/{run_id}",
    summary="查询仓储飞书数据分析结果",
    response_model=WarehouseAnalysisRunApiResponse,
)
async def get_warehouse_analysis_run(
    run_id: UUID,
    service: WarehouseService = Depends(get_warehouse_service),
):
    data = await service.get_analysis_run(run_id)
    return success_response(data=data.model_dump(mode="json"))


@router.get(
    "/feishu/ws/status",
    summary="查询仓储飞书 WebSocket 状态",
    response_model=WarehouseFeishuWsStatusApiResponse,
)
async def get_feishu_ws_status():
    from app.modules.warehouse.ws_client import get_ws_status

    return success_response(data=(await get_ws_status()).model_dump(mode="json"))


@router.post(
    "/feishu/ws/restart",
    summary="重启仓储飞书 WebSocket 长连接",
    response_model=WarehouseFeishuWsStatusApiResponse,
)
async def restart_feishu_ws():
    from app.modules.warehouse.ws_client import restart_ws_from_db

    return success_response(data=(await restart_ws_from_db()).model_dump(mode="json"))
