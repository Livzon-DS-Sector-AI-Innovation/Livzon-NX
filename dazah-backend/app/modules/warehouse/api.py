import logging
from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.modules.warehouse.ai_service import WarehouseAIService
from app.modules.warehouse.feishu_material_pages import (
    FEISHU_FINISHED_PRODUCT_APP_TOKEN,
    FEISHU_HARDWARE_APP_TOKEN,
    FEISHU_WAREHOUSE_APP_TOKEN,
)
from app.modules.warehouse.schemas import (
    PackagingMaterialResponse,
    ProductInventoryResponse,
    RawMaterialResponse,
    WarehouseAnalysisProfileApiResponse,
    WarehouseAnalysisProfileInput,
    WarehouseAnalysisRunApiResponse,
    WarehouseAnalyticsApiResponse,
    WarehouseAnalyticsQuery,
    WarehouseDatasetApiResponse,
    WarehouseDatasetRecordApiResponse,
    WarehouseFeishuConfigApiResponse,
    WarehouseFeishuConfigUpsert,
    WarehouseFeishuConnectivityApiResponse,
    WarehouseFeishuMaterialPageResponse,
    WarehouseFeishuPageBindingReplace,
    WarehouseFeishuPageDataApiResponse,
    WarehouseFeishuRawRecordData,
    WarehouseFeishuSourceRootApiResponse,
    WarehouseFeishuSourceRootInput,
    WarehouseFeishuSourceRootListApiResponse,
    WarehouseFeishuTableResponse,
    WarehouseFeishuTableSyncResult,
    WarehouseFeishuWsStatusApiResponse,
    WarehouseFieldValuesApiResponse,
    WarehousePageFeishuConfig,
    WarehousePromptVersionApiResponse,
    WarehousePromptVersionInput,
    WarehousePromptVersionListApiResponse,
    WarehouseRecordDetailResponse,
    WarehouseUpdateRecordRequest,
)
from app.modules.warehouse.service import WarehouseService
from app.platform.identity.data_scope import resolve_user_department_scope
from app.platform.identity.deps import RequireUser
from app.platform.identity.rbac import resolve_user_permissions
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["warehouse"])
logger = logging.getLogger(__name__)


# 页面所属 Base → 细分编辑权限码（按飞书部门映射的子领域）
WAREHOUSE_EDIT_SCOPE_PERMISSION = {
    FEISHU_WAREHOUSE_APP_TOKEN: "warehouse:raw:write",
    FEISHU_FINISHED_PRODUCT_APP_TOKEN: "warehouse:product:write",
    FEISHU_HARDWARE_APP_TOKEN: "warehouse:hardware:write",
}


def _assert_warehouse_edit_scope(app_token: str, permissions: list[str]) -> None:
    """按页面所属 Base 校验细分编辑权限（纵深防御；中间件已放行模块级写）。

    通过条件：通配（super_admin）/ 模块级 warehouse:write / 对应子领域细分码。
    """
    if "*" in permissions or "warehouse:write" in permissions:
        return
    required = WAREHOUSE_EDIT_SCOPE_PERMISSION.get(app_token)
    if required and required in permissions:
        return
    raise HTTPException(
        status_code=403,
        detail=(
            f"无权限执行操作 {required or 'warehouse:write'}"
            "（仅可编辑本部门负责的仓储子领域）"
        ),
    )


def _assert_warehouse_write(permissions: list[str]) -> None:
    if "*" in permissions or "warehouse:write" in permissions:
        return
    raise HTTPException(status_code=403, detail="无权修改仓储飞书配置")


def get_warehouse_service(
    session: AsyncSession = Depends(get_db),
) -> WarehouseService:
    return WarehouseService(session)


def get_warehouse_ai_service(
    session: AsyncSession = Depends(get_db),
) -> WarehouseAIService:
    return WarehouseAIService(session)


class WarehouseAiChatRequest(BaseModel):
    question: str


@router.get(
    "/feishu-config",
    summary="获取仓储飞书配置",
    response_model=WarehouseFeishuConfigApiResponse,
)
async def get_feishu_config(
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    return success_response(data=await service.get_feishu_config_response())


@router.put(
    "/feishu-config",
    summary="保存仓储飞书配置",
    response_model=WarehouseFeishuConfigApiResponse,
)
async def save_feishu_config(
    payload: WarehouseFeishuConfigUpsert,
    current_user: RequireUser,
    db: AsyncSession = Depends(get_db),
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    permissions = await resolve_user_permissions(db, current_user.id)
    _assert_warehouse_write(permissions)
    data = await service.save_feishu_config(payload)
    return success_response(data=data)


@router.post(
    "/feishu-config/test",
    summary="测试仓储飞书连通性",
    response_model=WarehouseFeishuConnectivityApiResponse,
)
async def test_feishu_config(
    current_user: RequireUser,
    payload: WarehouseFeishuConfigUpsert | None = None,
    db: AsyncSession = Depends(get_db),
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    permissions = await resolve_user_permissions(db, current_user.id)
    _assert_warehouse_write(permissions)
    return success_response(data=await service.test_feishu_connectivity(payload))


@router.get(
    "/feishu/roots",
    summary="查询仓储飞书数据入口",
    response_model=WarehouseFeishuSourceRootListApiResponse,
)
async def list_feishu_roots(
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    return success_response(data=await service.list_feishu_source_roots())


@router.post(
    "/feishu/roots",
    summary="新增仓储飞书数据入口",
    response_model=WarehouseFeishuSourceRootApiResponse,
)
async def create_feishu_root(
    payload: WarehouseFeishuSourceRootInput,
    current_user: RequireUser,
    db: AsyncSession = Depends(get_db),
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    permissions = await resolve_user_permissions(db, current_user.id)
    _assert_warehouse_write(permissions)
    return success_response(data=await service.create_feishu_source_root(payload))


@router.delete("/feishu/roots/{root_id}", summary="停用仓储飞书数据入口")
async def delete_feishu_root(
    root_id: UUID,
    current_user: RequireUser,
    db: AsyncSession = Depends(get_db),
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    permissions = await resolve_user_permissions(db, current_user.id)
    _assert_warehouse_write(permissions)
    return success_response(data=await service.delete_feishu_source_root(root_id))


@router.post("/feishu/roots/{root_id}/discover", summary="发现仓储飞书数据入口")
async def discover_feishu_root(
    root_id: UUID,
    current_user: RequireUser,
    db: AsyncSession = Depends(get_db),
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    permissions = await resolve_user_permissions(db, current_user.id)
    _assert_warehouse_write(permissions)
    return success_response(data=await service.discover_feishu_source_root(root_id))


@router.get(
    "/page-data/{page_key}",
    summary="获取仓储页面数据表映射",
    response_model=WarehouseFeishuPageDataApiResponse,
)
async def get_warehouse_page_data(
    page_key: str,
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    return success_response(data=await service.get_page_data(page_key))


@router.put(
    "/page-data/{page_key}",
    summary="发布仓储页面数据表映射",
    response_model=WarehouseFeishuPageDataApiResponse,
)
async def replace_warehouse_page_data(
    page_key: str,
    payload: WarehouseFeishuPageBindingReplace,
    current_user: RequireUser,
    db: AsyncSession = Depends(get_db),
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    permissions = await resolve_user_permissions(db, current_user.id)
    _assert_warehouse_write(permissions)
    return success_response(data=await service.replace_page_bindings(page_key, payload))


@router.get(
    "/page-data/{page_key}/{binding_id}/records",
    summary="查询仓储页面数据表记录",
    response_model=WarehouseDatasetApiResponse,
)
async def get_warehouse_page_dataset(
    page_key: str,
    binding_id: UUID,
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=1000),
    filter_field: list[str] | None = Query(None),
    filter_operator: list[str] | None = Query(None),
    filter_value: list[str] | None = Query(None),
    sort_field: str | None = Query(None),
    sort_direction: str | None = Query(None, pattern="^(asc|desc)$"),
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    return success_response(
        data=await service.get_page_dataset(
            page_key,
            binding_id,
            keyword=keyword,
            page=page,
            page_size=page_size,
            filter_fields=filter_field,
            filter_operators=filter_operator,
            filter_values=filter_value,
            sort_field=sort_field,
            sort_direction=sort_direction,
        )
    )


@router.get(
    "/page-data/{page_key}/{binding_id}/field-values/{field_id}",
    summary="查询仓储页面字段值",
    response_model=WarehouseFieldValuesApiResponse,
)
async def get_warehouse_field_values(
    page_key: str,
    binding_id: UUID,
    field_id: str,
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    return success_response(
        data=await service.get_page_field_values(page_key, binding_id, field_id)
    )


@router.get(
    "/page-data/{page_key}/{binding_id}/record/{record_id}",
    summary="查询仓储页面单条记录",
    response_model=WarehouseDatasetRecordApiResponse,
)
async def get_warehouse_page_record(
    page_key: str,
    binding_id: UUID,
    record_id: str,
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    return success_response(
        data=await service.get_page_record(page_key, binding_id, record_id)
    )


@router.get(
    "/page-data/{page_key}/{binding_id}/record/{record_id}/attachments/{field_id}/{file_token}",
    summary="下载仓储页面附件",
)
async def download_warehouse_attachment(
    page_key: str,
    binding_id: UUID,
    record_id: str,
    field_id: str,
    file_token: str,
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    content, media_type, disposition = await service.download_page_attachment(
        page_key, binding_id, record_id, field_id, file_token
    )
    headers = {"Content-Disposition": disposition} if disposition else None
    return Response(content=content, media_type=media_type, headers=headers)


@router.post(
    "/analytics/query",
    summary="查询仓储数据分析",
    response_model=WarehouseAnalyticsApiResponse,
)
async def query_warehouse_analytics(
    payload: WarehouseAnalyticsQuery,
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    return success_response(data=await service.aggregate_page_dataset(payload))


@router.get(
    "/feishu/ws/status",
    summary="获取仓储飞书 WebSocket 状态",
    response_model=WarehouseFeishuWsStatusApiResponse,
)
async def get_warehouse_ws_status() -> Any:
    from app.modules.warehouse.ws_client import get_ws_status

    return success_response(data=await get_ws_status())


@router.post(
    "/feishu/ws/restart",
    summary="重启仓储飞书 WebSocket",
    response_model=WarehouseFeishuWsStatusApiResponse,
)
async def restart_warehouse_ws(
    current_user: RequireUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    permissions = await resolve_user_permissions(db, current_user.id)
    _assert_warehouse_write(permissions)
    from app.modules.warehouse.ws_client import restart_ws_from_db

    return success_response(data=await restart_ws_from_db())


@router.post(
    "/analysis/profiles",
    summary="创建仓储分析配置",
    response_model=WarehouseAnalysisProfileApiResponse,
)
async def create_warehouse_analysis_profile(
    payload: WarehouseAnalysisProfileInput,
    current_user: RequireUser,
    db: AsyncSession = Depends(get_db),
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    permissions = await resolve_user_permissions(db, current_user.id)
    _assert_warehouse_write(permissions)
    return success_response(data=await service.create_analysis_profile(payload))


@router.get(
    "/analysis/profiles/{profile_id}",
    summary="获取仓储分析配置",
    response_model=WarehouseAnalysisProfileApiResponse,
)
async def get_warehouse_analysis_profile(
    profile_id: UUID,
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    return success_response(data=await service.get_analysis_profile(profile_id))


@router.get(
    "/analysis/profiles/{profile_id}/prompts",
    summary="查询仓储分析提示词版本",
    response_model=WarehousePromptVersionListApiResponse,
)
async def list_warehouse_analysis_prompts(
    profile_id: UUID,
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    return success_response(data=await service.list_prompt_versions(profile_id))


@router.post(
    "/analysis/profiles/{profile_id}/prompts",
    summary="创建仓储分析提示词草稿",
    response_model=WarehousePromptVersionApiResponse,
)
async def create_warehouse_analysis_prompt(
    profile_id: UUID,
    payload: WarehousePromptVersionInput,
    current_user: RequireUser,
    db: AsyncSession = Depends(get_db),
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    permissions = await resolve_user_permissions(db, current_user.id)
    _assert_warehouse_write(permissions)
    return success_response(data=await service.create_prompt_draft(profile_id, payload))


@router.post(
    "/analysis/profiles/{profile_id}/prompts/{prompt_id}/publish",
    summary="发布仓储分析提示词",
    response_model=WarehousePromptVersionApiResponse,
)
async def publish_warehouse_analysis_prompt(
    profile_id: UUID,
    prompt_id: UUID,
    current_user: RequireUser,
    db: AsyncSession = Depends(get_db),
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    permissions = await resolve_user_permissions(db, current_user.id)
    _assert_warehouse_write(permissions)
    return success_response(
        data=await service.publish_prompt_version(profile_id, prompt_id)
    )


@router.post(
    "/analysis/profiles/{profile_id}/run",
    summary="运行仓储分析",
    response_model=WarehouseAnalysisRunApiResponse,
)
async def run_warehouse_analysis(
    profile_id: UUID,
    current_user: RequireUser,
    db: AsyncSession = Depends(get_db),
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    permissions = await resolve_user_permissions(db, current_user.id)
    _assert_warehouse_write(permissions)
    return success_response(data=await service.run_analysis(profile_id))


@router.get(
    "/analysis/runs/{run_id}",
    summary="获取仓储分析运行结果",
    response_model=WarehouseAnalysisRunApiResponse,
)
async def get_warehouse_analysis_run(
    run_id: UUID,
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    return success_response(data=await service.get_analysis_run_response(run_id))


@router.get(
    "/feishu/tables",
    summary="查询仓储飞书数据表目录（兼容入口）",
    response_model=list[WarehouseFeishuTableResponse],
)
async def list_legacy_feishu_tables(
    keyword: str | None = Query(None),
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    """保留当前 Agent/旧客户端使用的表目录入口，数据来自页面配置镜像。"""

    return await service.list_feishu_tables(keyword=keyword)


@router.get(
    "/feishu/tables/{table_id}/records",
    summary="查询仓储飞书表本地记录（兼容入口）",
    response_model=WarehouseFeishuRawRecordData,
)
async def get_legacy_feishu_table_records(
    table_id: UUID,
    keyword: str | None = Query(None),
    field: str | None = Query(None),
    field_operator: str | None = Query(None),
    field_value: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    return await service.get_feishu_table_records(
        table_id,
        keyword=keyword,
        field=field,
        field_operator=field_operator,
        field_value=field_value,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/feishu/tables/{table_id}/sync",
    summary="同步仓储飞书表（兼容入口）",
    response_model=WarehouseFeishuTableSyncResult,
)
async def sync_legacy_feishu_table(
    table_id: UUID,
    current_user: RequireUser,
    db: AsyncSession = Depends(get_db),
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    permissions = await resolve_user_permissions(db, current_user.id)
    if "*" not in permissions and "warehouse:write" not in permissions:
        raise HTTPException(status_code=403, detail="无权同步仓储飞书数据表")
    return await service.sync_feishu_table(table_id)


@router.get(
    "/raw-materials", summary="原辅料库存列表", response_model=list[RawMaterialResponse]
)
async def list_raw_materials(
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    items = await service.list_raw_materials()
    data = [
        RawMaterialResponse.model_validate(item).model_dump(mode="json")
        for item in items
    ]
    return success_response(data=data)


@router.get(
    "/packaging-materials",
    summary="包材库存列表",
    response_model=list[PackagingMaterialResponse],
)
async def list_packaging_materials(
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    items = await service.list_packaging_materials()
    data = [
        PackagingMaterialResponse.model_validate(item).model_dump(mode="json")
        for item in items
    ]
    return success_response(data=data)


@router.get(
    "/products", summary="成品库存列表", response_model=list[ProductInventoryResponse]
)
async def list_products(
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    items = await service.list_products()
    data = [
        ProductInventoryResponse.model_validate(item).model_dump(mode="json")
        for item in items
    ]
    return success_response(data=data)


@router.get("/dashboard", summary="仓储仪表盘数据（按分组）")
async def get_warehouse_dashboard(
    current_user: RequireUser,
    group: str = Query(
        "raw", description="raw=原辅料及包材 / hardware=五金 / product=成品"
    ),
    force: bool = Query(False, description="强制绕过缓存拉取最新数据"),
    detail: bool = Query(False, description="附加 KPI 明细行（供卡片点击查看）"),
    db: AsyncSession = Depends(get_db),
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    """返回对应分组多维表格仪表盘的数据（安全库存/质量批数/出库趋势/金额分布等）。

    五金组按当前用户可见部门（后台可配置）过滤部门聚合数据。
    """
    scope = await resolve_user_department_scope(db, current_user)
    try:
        data = await service.get_dashboard_data(
            group, force=force, detail=detail, scope=scope
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("warehouse dashboard read failed")
        raise HTTPException(
            status_code=502,
            detail="仓储仪表盘数据读取失败，请稍后重试",
        ) from exc
    return success_response(data=data)


@router.get(
    "/page-feishu-configs",
    summary="获取页面飞书配置列表",
    response_model=list[WarehousePageFeishuConfig],
)
async def list_page_feishu_configs(
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    """返回所有页面的飞书多维表格配置（首次访问自动补齐硬编码映射）"""
    configs = await service.get_all_page_feishu_configs()
    return success_response(data=configs)


@router.put("/page-feishu-configs/{page_key}", summary="更新页面飞书配置")
async def update_page_feishu_config(
    page_key: str,
    payload: WarehousePageFeishuConfig,
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    """更新指定页面的飞书多维表格配置（支持动态切换数据源）"""
    await service.update_page_feishu_config(page_key, payload.model_dump())
    return success_response(message="配置已更新")


@router.get(
    "/material-pages/{page_key}",
    summary="仓储页面数据",
    response_model=WarehouseFeishuMaterialPageResponse,
)
async def get_material_page(
    current_user: RequireUser,
    page_key: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=1000),
    keyword: str | None = None,
    start_date: str | None = Query(None, description="开始日期，格式 YYYY-MM-DD"),
    end_date: str | None = Query(None, description="结束日期，格式 YYYY-MM-DD"),
    date_field: str | None = Query(None, description="日期筛选字段名"),
    product: str | None = Query(None, description="使用产品或类别"),
    area: str | None = Query(None, description="库区或出库库区"),
    quality_status: str | None = Query(None, description="质量状态"),
    warning_status: str | None = Query(None, description="预警状态"),
    material_category: str | None = Query(None, description="物料类别"),
    filters: str | None = Query(None, description="高级筛选 JSON 数组"),
    source: str | None = Query(
        None, description="可选 feishu 或 local；不传时由后端默认配置决定"
    ),
    force: bool = Query(False, description="强制绕过缓存从飞书拉取最新数据"),
    db: AsyncSession = Depends(get_db),
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    """仓储页面数据（五金车间明细页按当前用户可见部门做行级过滤）。"""
    scope = await resolve_user_department_scope(db, current_user)
    data: WarehouseFeishuMaterialPageResponse = await service.get_feishu_material_page(
        page_key,
        page=page,
        page_size=page_size,
        keyword=keyword,
        source=source,
        force=force,
        start_date=start_date,
        end_date=end_date,
        date_field=date_field,
        product=product,
        area=area,
        quality_status=quality_status,
        warning_status=warning_status,
        material_category=material_category,
        filters=filters,
        scope=scope,
    )
    return success_response(data=data.model_dump(mode="json"))


@router.get(
    "/material-pages/{page_key}/records/{record_id}",
    summary="仓储记录详情（含全部字段）",
    response_model=WarehouseRecordDetailResponse,
)
async def get_material_page_record_detail(
    page_key: str,
    record_id: str,
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    """获取单条记录在多维表格中的全部字段，含列表未展示字段与可写性信息。"""
    try:
        data = await service.get_material_page_record_detail(page_key, record_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("warehouse record detail read failed")
        raise HTTPException(
            status_code=502,
            detail="仓储记录详情读取失败，请稍后重试",
        ) from exc
    return success_response(data=data)


@router.put(
    "/material-pages/{page_key}/records/{record_id}",
    summary="更新仓储记录（写回飞书多维表格）",
)
async def update_material_page_record(
    page_key: str,
    record_id: str,
    request: WarehouseUpdateRecordRequest,
    current_user: RequireUser,
    db: AsyncSession = Depends(get_db),
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    """将页面编辑结果写回对应飞书多维表格。

    编辑权限按页面所属子领域（成品/五金/原辅料及包材）校验，
    由后台部门角色映射决定用户可编辑的子领域。
    """
    from app.platform.identity.rbac import resolve_user_permissions

    permissions = await resolve_user_permissions(db, current_user.id)
    page_config = await service._get_material_page_config(page_key)
    _assert_warehouse_edit_scope(page_config.app_token, permissions)
    try:
        record = await service.update_material_page_record(
            page_key, record_id, request.fields
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("warehouse record update failed")
        raise HTTPException(
            status_code=502,
            detail="同步更新到飞书失败，请稍后重试",
        ) from exc
    return success_response(data=record)


@router.delete(
    "/material-pages/{page_key}/records/{record_id}",
    summary="删除仓储记录（同步删除飞书多维表格）",
)
async def delete_material_page_record(
    page_key: str,
    record_id: str,
    current_user: RequireUser,
    db: AsyncSession = Depends(get_db),
    service: WarehouseService = Depends(get_warehouse_service),
) -> Any:
    """从对应飞书多维表格删除该记录（编辑权限按子领域校验）。"""
    from app.platform.identity.rbac import resolve_user_permissions

    permissions = await resolve_user_permissions(db, current_user.id)
    page_config = await service._get_material_page_config(page_key)
    _assert_warehouse_edit_scope(page_config.app_token, permissions)
    try:
        await service.delete_material_page_record(page_key, record_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("warehouse record delete failed")
        raise HTTPException(
            status_code=502,
            detail="同步删除到飞书失败，请稍后重试",
        ) from exc
    return success_response(data={"deleted": True, "record_id": record_id})


@router.get("/ai/anomalies", summary="AI异常检测")
async def detect_anomalies(
    ai_service: WarehouseAIService = Depends(get_warehouse_ai_service),
) -> Any:
    """Run anomaly detection on warehouse data."""
    anomalies = await ai_service.run_anomaly_detection()
    data = [anomaly.to_dict() for anomaly in anomalies]
    return success_response(data=data)


@router.get("/ai/summary", summary="库存概览统计")
async def get_inventory_summary(
    ai_service: WarehouseAIService = Depends(get_warehouse_ai_service),
) -> Any:
    """Get inventory summary statistics."""
    data = await ai_service.get_inventory_summary()
    return success_response(data=data)


@router.get("/ai/trend-summary", summary="物料周趋势异常概览")
async def get_trend_summary(
    ai_service: WarehouseAIService = Depends(get_warehouse_ai_service),
) -> Any:
    """Get weekly material trend anomaly summary."""
    data = await ai_service.get_trend_anomaly_summary()
    return success_response(data=data)


@router.get("/ai/trend-anomalies", summary="物料周趋势异常明细")
async def get_trend_anomalies(
    ai_service: WarehouseAIService = Depends(get_warehouse_ai_service),
) -> Any:
    """Get weekly material trend anomaly detail list."""
    data = await ai_service.get_material_trend_anomalies()
    return success_response(data=data)


@router.get("/ai/trend-product-lines", summary="产品线周趋势概览")
async def get_trend_product_lines(
    ai_service: WarehouseAIService = Depends(get_warehouse_ai_service),
) -> Any:
    """Get product line trend overview."""
    data = await ai_service.get_product_line_trend_overview()
    return success_response(data=data)


@router.get("/ai/hardware-cost-anomalies", summary="五金费用异常车间")
async def get_hardware_cost_anomalies(
    ai_service: WarehouseAIService = Depends(get_warehouse_ai_service),
) -> Any:
    """Get hardware cost anomalies by workshop."""
    data = await ai_service.get_hardware_cost_anomalies()
    return success_response(data=data)


@router.get("/ai/hardware-cost-summary", summary="五金费用概览")
async def get_hardware_cost_summary(
    ai_service: WarehouseAIService = Depends(get_warehouse_ai_service),
) -> Any:
    """Get hardware cost summary."""
    data = await ai_service.get_hardware_cost_summary()
    return success_response(data=data)


@router.post("/ai/chat", summary="AI智能问答")
async def ai_chat(
    request: WarehouseAiChatRequest,
    ai_service: WarehouseAIService = Depends(get_warehouse_ai_service),
) -> Any:
    """Chat with AI about warehouse data."""
    response = await ai_service.chat_with_ai(request.question)
    return success_response(data={"response": response})


@router.get("/ai/report", summary="AI分析报告")
async def generate_report(
    ai_service: WarehouseAIService = Depends(get_warehouse_ai_service),
) -> Any:
    """Generate comprehensive analysis report."""
    data = await ai_service.generate_analysis_report()
    return success_response(data=data)
