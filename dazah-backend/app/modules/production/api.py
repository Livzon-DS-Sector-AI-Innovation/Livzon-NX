"""Production API routes."""

import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.response import ApiResponse
from app.modules.production.feishu_service import ProductionFeishuService
from app.modules.production.operations_api import router as operations_router
from app.modules.production.pressure_api import router as pressure_router
from app.modules.production.process_api import router as process_execution_router
from app.modules.production.read_mirror_api import router as read_mirror_router
from app.modules.production.schemas import (
    BatchCreate,
    BatchMaterialCreate,
    BatchMaterialResponse,
    BatchMaterialUpdate,
    BatchResponse,
    BatchStatusUpdate,
    BatchUpdate,
    MaterialBalanceResponse,
    MaterialBalanceUpdate,
    PlanTaskCreate,
    PlanTaskResponse,
    PlanTaskUpdate,
    ProcessParameterCreate,
    ProcessParameterResponse,
    ProcessSpecCreate,
    ProcessSpecResponse,
    ProcessSpecUpdate,
    ProcessStepCreate,
    ProcessStepResponse,
    ProcessStepUpdate,
    ProductionApiResponse,
    ProductionExecutionPlanCreate,
    ProductionExecutionPlanResponse,
    ProductionExecutionPlanUpdate,
    ProductionFeishuConfigUpsert,
    ProductionFeishuSyncBindingCreate,
    ProductionFeishuSyncBindingResponse,
    ProductionFeishuSyncBindingUpdate,
    ProductionFeishuSyncExecuteRequest,
    ProductionFeishuSyncRunResponse,
    ProductionFeishuTablePreviewResponse,
    ProductionPlanCreate,
    ProductionPlanResponse,
    ProductionPlanUpdate,
    ProductionRecordCreate,
    ProductionRecordResponse,
    ProductionRecordUpdate,
    SalesPlanDetailCreate,
    SalesPlanDetailResponse,
    SalesPlanDetailUpdate,
)
from app.modules.production.service import ProductionService

router = APIRouter()
router.include_router(read_mirror_router, tags=["Production-Feishu-Read"])


# ============ Feishu Config Routes ============


@router.get("/feishu-config", response_model=ApiResponse, summary="获取生产飞书配置")
async def get_production_feishu_config(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """获取生产飞书配置"""
    service = ProductionFeishuService(db)
    data = await service.get_config_response()
    return ApiResponse(data=data.model_dump(mode="json"))


@router.get(
    "/feishu-configs", response_model=ApiResponse, summary="获取生产飞书配置列表"
)
async def list_production_feishu_configs(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """获取生产飞书配置列表"""
    service = ProductionFeishuService(db)
    data = await service.list_config_responses()
    return ApiResponse(
        data=[item.model_dump(mode="json") for item in data],
        meta={"total": len(data)},
    )


@router.put("/feishu-config", response_model=ApiResponse, summary="保存生产飞书配置")
async def save_production_feishu_config(
    payload: ProductionFeishuConfigUpsert,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """保存生产飞书配置"""
    service = ProductionFeishuService(db)
    data = await service.save_config(payload)
    return ApiResponse(data=data.model_dump(mode="json"))


@router.post(
    "/feishu-config/test", response_model=ApiResponse, summary="测试生产飞书配置"
)
async def test_production_feishu_config(
    payload: ProductionFeishuConfigUpsert | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """测试生产飞书配置"""
    service = ProductionFeishuService(db)
    data = await service.test_connectivity(payload)
    return ApiResponse(data=data.model_dump(mode="json"))


@router.get(
    "/feishu-config/tables",
    response_model=ApiResponse,
    summary="读取生产飞书多维表格数据表列表",
)
async def list_production_feishu_tables(
    config_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """读取生产飞书多维表格数据表列表"""
    service = ProductionFeishuService(db)
    data = await service.list_tables(config_id=config_id)
    return ApiResponse(
        data=data.model_dump(mode="json"),
        meta={"total": data.total or 0},
    )


@router.get(
    "/feishu-config/records",
    response_model=ApiResponse,
    summary="读取生产飞书多维表格数据",
)
async def get_production_feishu_records(
    config_id: uuid.UUID | None = None,
    table_id: str | None = None,
    page_size: int = Query(20, ge=1, le=100),
    page_token: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """读取生产飞书多维表格数据"""
    service = ProductionFeishuService(db)
    data = await service.get_table_preview(
        config_id=config_id,
        table_id=table_id,
        page_size=page_size,
        page_token=page_token,
    )
    return ApiResponse(
        data=data.model_dump(mode="json"),
        meta={"page_size": data.page_size, "total": data.total or 0},
    )


@router.get(
    "/feishu-sync-bindings",
    response_model=ProductionApiResponse[list[ProductionFeishuSyncBindingResponse]],
    summary="获取生产飞书同步绑定",
)
async def list_production_feishu_sync_bindings(
    config_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """获取绑定配置；本接口不会读取或写入飞书。"""
    data = await ProductionFeishuService(db).list_sync_bindings(config_id)
    return ApiResponse(data=data, meta={"total": len(data)})


@router.post(
    "/feishu-sync-bindings",
    response_model=ProductionApiResponse[ProductionFeishuSyncBindingResponse],
    summary="创建生产飞书同步绑定",
)
async def create_production_feishu_sync_binding(
    data: ProductionFeishuSyncBindingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """创建同步绑定；实际同步能力须由业务字段映射确认后单独启用。"""
    binding = await ProductionFeishuService(db).create_sync_binding(data)
    await db.commit()
    return ApiResponse(data=binding)


@router.put(
    "/feishu-sync-bindings/{binding_id}",
    response_model=ProductionApiResponse[ProductionFeishuSyncBindingResponse],
    summary="更新生产飞书同步绑定",
)
async def update_production_feishu_sync_binding(
    binding_id: uuid.UUID,
    data: ProductionFeishuSyncBindingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    binding = await ProductionFeishuService(db).update_sync_binding(binding_id, data)
    if not binding:
        return ApiResponse(code=404, message="飞书同步绑定不存在")
    await db.commit()
    return ApiResponse(data=binding)


@router.delete(
    "/feishu-sync-bindings/{binding_id}",
    response_model=ProductionApiResponse[None],
    summary="删除生产飞书同步绑定",
)
async def delete_production_feishu_sync_binding(
    binding_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    deleted = await ProductionFeishuService(db).delete_sync_binding(binding_id)
    if not deleted:
        return ApiResponse(code=404, message="飞书同步绑定不存在")
    await db.commit()
    return ApiResponse(message="删除成功")


@router.get(
    "/feishu-sync-bindings/{binding_id}/preview",
    response_model=ProductionApiResponse[ProductionFeishuTablePreviewResponse],
    summary="预览飞书同步绑定数据",
)
async def preview_production_feishu_sync_binding(
    binding_id: uuid.UUID,
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """读取绑定表的样本数据，不写入平台业务数据。"""
    preview = await ProductionFeishuService(db).get_sync_binding_preview(
        binding_id, page_size
    )
    return ApiResponse(data=preview)


@router.get(
    "/feishu-sync-bindings/{binding_id}/runs",
    response_model=ProductionApiResponse[list[ProductionFeishuSyncRunResponse]],
    summary="获取飞书同步运行记录",
)
async def list_production_feishu_sync_runs(
    binding_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    runs = await ProductionFeishuService(db).list_sync_runs(binding_id, limit)
    return ApiResponse(data=runs, meta={"total": len(runs)})


@router.post(
    "/feishu-sync-bindings/{binding_id}/sync",
    response_model=ProductionApiResponse[ProductionFeishuSyncRunResponse],
    summary="预览或执行飞书销售执行同步",
)
async def execute_production_feishu_sync_binding(
    binding_id: uuid.UUID,
    data: ProductionFeishuSyncExecuteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """默认 dry-run；执行模式按飞书 record_id 对销售执行明细幂等 upsert。"""
    sync_run = await ProductionFeishuService(db).execute_sync_binding(binding_id, data)
    await db.commit()
    return ApiResponse(data=sync_run)


# ============ Batch Routes ============


@router.get("/batches", response_model=ApiResponse, summary="获取批次列表")
async def get_batches(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: str | None = None,
    product_code: str | None = None,
    product_name: str | None = None,
    batch_no: str | None = None,
    production_line: str | None = None,
    exclude_cancelled: str | None = Query(
        None, description="是否排除已取消的批次，传入 'true' 或 'false'"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """获取批次列表"""
    service = ProductionService(db)
    skip = (page - 1) * page_size
    # 将字符串参数转换为布尔值
    exclude_cancelled_bool = (
        exclude_cancelled is not None and exclude_cancelled.lower() == "true"
    )
    batches, total = await service.get_batches(
        skip,
        page_size,
        status,
        product_code,
        product_name,
        batch_no,
        production_line,
        exclude_cancelled_bool,
    )
    return ApiResponse(
        data=[BatchResponse.model_validate(b) for b in batches],
        meta={"page": page, "page_size": page_size, "total": total},
    )


@router.get("/batches/{batch_id}", response_model=ApiResponse, summary="获取批次详情")
async def get_batch(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """获取批次详情"""
    service = ProductionService(db)
    batch = await service.get_batch(batch_id)
    if not batch:
        return ApiResponse(code=404, message="批次不存在")
    return ApiResponse(data=BatchResponse.model_validate(batch))


@router.post("/batches", response_model=ApiResponse, summary="创建批次")
async def create_batch(
    data: BatchCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """创建批次"""
    service = ProductionService(db)
    batch = await service.create_batch(data)
    await db.commit()
    return ApiResponse(data=BatchResponse.model_validate(batch))


@router.put("/batches/{batch_id}", response_model=ApiResponse, summary="更新批次")
async def update_batch(
    batch_id: uuid.UUID,
    data: BatchUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """更新批次"""
    service = ProductionService(db)
    batch = await service.update_batch(batch_id, data)
    if not batch:
        return ApiResponse(code=404, message="批次不存在")
    await db.commit()
    return ApiResponse(data=BatchResponse.model_validate(batch))


@router.put(
    "/batches/{batch_id}/status", response_model=ApiResponse, summary="更新批次状态"
)
async def update_batch_status(
    batch_id: uuid.UUID,
    data: BatchStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """更新批次状态"""
    service = ProductionService(db)
    try:
        batch = await service.update_batch_status(batch_id, data)
        if not batch:
            return ApiResponse(code=404, message="批次不存在")
        await db.commit()
        return ApiResponse(data=BatchResponse.model_validate(batch))
    except ValueError as e:
        return ApiResponse(code=400, message=str(e))


@router.delete("/batches/{batch_id}", response_model=ApiResponse, summary="删除批次")
async def delete_batch(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """删除批次"""
    service = ProductionService(db)
    result = await service.delete_batch(batch_id)
    if not result:
        return ApiResponse(code=404, message="批次不存在")
    await db.commit()
    return ApiResponse(message="删除成功")


# ============ BatchMaterial Routes ============


@router.get(
    "/batches/{batch_id}/materials",
    response_model=ApiResponse,
    summary="获取批次物料列表",
)
async def get_batch_materials(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """获取批次物料列表"""
    service = ProductionService(db)
    materials = await service.get_batch_materials(batch_id)
    return ApiResponse(
        data=[BatchMaterialResponse.model_validate(m) for m in materials]
    )


@router.post(
    "/batches/{batch_id}/materials", response_model=ApiResponse, summary="添加批次物料"
)
async def add_batch_material(
    batch_id: uuid.UUID,
    data: BatchMaterialCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """添加批次物料"""
    service = ProductionService(db)
    material = await service.add_batch_material(batch_id, data.model_dump())
    await db.commit()
    return ApiResponse(data=BatchMaterialResponse.model_validate(material))


@router.put(
    "/materials/{material_id}", response_model=ApiResponse, summary="更新批次物料"
)
async def update_batch_material(
    material_id: uuid.UUID,
    data: BatchMaterialUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """更新批次物料"""
    service = ProductionService(db)
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    material = await service.update_batch_material(material_id, update_data)
    if not material:
        return ApiResponse(code=404, message="物料不存在")
    await db.commit()
    return ApiResponse(data=BatchMaterialResponse.model_validate(material))


@router.delete(
    "/materials/{material_id}", response_model=ApiResponse, summary="删除批次物料"
)
async def delete_batch_material(
    material_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """删除批次物料"""
    service = ProductionService(db)
    result = await service.delete_batch_material(material_id)
    if not result:
        return ApiResponse(code=404, message="物料不存在")
    await db.commit()
    return ApiResponse(message="删除成功")


# ============ ProductionPlan Routes ============


@router.get("/plans", response_model=ApiResponse, summary="获取生产计划列表")
async def get_plans(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: str | None = None,
    plan_month: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """获取生产计划列表"""
    service = ProductionService(db)
    skip = (page - 1) * page_size
    plans, total = await service.get_plans(skip, page_size, status, plan_month)
    return ApiResponse(
        data=[ProductionPlanResponse.model_validate(p) for p in plans],
        meta={"page": page, "page_size": page_size, "total": total},
    )


@router.get("/plans/{plan_id}", response_model=ApiResponse, summary="获取生产计划详情")
async def get_plan(
    plan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """获取生产计划详情"""
    service = ProductionService(db)
    plan = await service.get_plan(plan_id)
    if not plan:
        return ApiResponse(code=404, message="计划不存在")
    return ApiResponse(data=ProductionPlanResponse.model_validate(plan))


@router.post("/plans", response_model=ApiResponse, summary="创建生产计划")
async def create_plan(
    data: ProductionPlanCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """创建生产计划"""
    service = ProductionService(db)
    plan = await service.create_plan(data)
    await db.commit()
    return ApiResponse(data=ProductionPlanResponse.model_validate(plan))


@router.put("/plans/{plan_id}", response_model=ApiResponse, summary="更新生产计划")
async def update_plan(
    plan_id: uuid.UUID,
    data: ProductionPlanUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """更新生产计划"""
    service = ProductionService(db)
    plan = await service.update_plan(plan_id, data)
    if not plan:
        return ApiResponse(code=404, message="计划不存在")
    await db.commit()
    return ApiResponse(data=ProductionPlanResponse.model_validate(plan))


@router.delete("/plans/{plan_id}", response_model=ApiResponse, summary="删除生产计划")
async def delete_plan(
    plan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """删除生产计划"""
    service = ProductionService(db)
    result = await service.delete_plan(plan_id)
    if not result:
        return ApiResponse(code=404, message="计划不存在")
    await db.commit()
    return ApiResponse(message="删除成功")


# ============ ProductionExecutionPlan Routes ============


@router.get(
    "/execution-plans",
    response_model=ProductionApiResponse[list[ProductionExecutionPlanResponse]],
    summary="获取车间生产执行计划",
)
async def get_execution_plans(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    workshop: str | None = Query(default=None, max_length=64),
    product_name: str | None = Query(default=None, max_length=128),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    plans, total = await ProductionService(db).get_execution_plans(
        (page - 1) * page_size, page_size, workshop, product_name
    )
    return ApiResponse(
        data=[ProductionExecutionPlanResponse.model_validate(plan) for plan in plans],
        meta={"page": page, "page_size": page_size, "total": total},
    )


@router.post(
    "/execution-plans",
    response_model=ProductionApiResponse[ProductionExecutionPlanResponse],
    summary="创建车间生产执行计划",
)
async def create_execution_plan(
    data: ProductionExecutionPlanCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    plan = await ProductionService(db).create_execution_plan(data)
    await db.commit()
    return ApiResponse(data=ProductionExecutionPlanResponse.model_validate(plan))


@router.put(
    "/execution-plans/{plan_id}",
    response_model=ProductionApiResponse[ProductionExecutionPlanResponse],
    summary="更新车间生产执行计划",
)
async def update_execution_plan(
    plan_id: uuid.UUID,
    data: ProductionExecutionPlanUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    plan = await ProductionService(db).update_execution_plan(plan_id, data)
    if not plan:
        return ApiResponse(code=404, message="生产执行计划不存在")
    await db.commit()
    return ApiResponse(data=ProductionExecutionPlanResponse.model_validate(plan))


@router.delete(
    "/execution-plans/{plan_id}",
    response_model=ProductionApiResponse[None],
    summary="删除车间生产执行计划",
)
async def delete_execution_plan(
    plan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    deleted = await ProductionService(db).delete_execution_plan(plan_id)
    if not deleted:
        return ApiResponse(code=404, message="生产执行计划不存在")
    await db.commit()
    return ApiResponse(message="删除成功")


# ============ PlanTask Routes ============


@router.get(
    "/plans/{plan_id}/tasks", response_model=ApiResponse, summary="获取计划任务列表"
)
async def get_plan_tasks(
    plan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """获取计划任务列表"""
    service = ProductionService(db)
    tasks = await service.get_tasks(plan_id)
    return ApiResponse(data=[PlanTaskResponse.model_validate(t) for t in tasks])


@router.post("/tasks", response_model=ApiResponse, summary="创建计划任务")
async def create_task(
    data: PlanTaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """创建计划任务"""
    service = ProductionService(db)
    task = await service.create_task(data)
    await db.commit()
    return ApiResponse(data=PlanTaskResponse.model_validate(task))


@router.put("/tasks/{task_id}", response_model=ApiResponse, summary="更新计划任务")
async def update_task(
    task_id: uuid.UUID,
    data: PlanTaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """更新计划任务"""
    service = ProductionService(db)
    task = await service.update_task(task_id, data)
    if not task:
        return ApiResponse(code=404, message="任务不存在")
    await db.commit()
    return ApiResponse(data=PlanTaskResponse.model_validate(task))


@router.delete("/tasks/{task_id}", response_model=ApiResponse, summary="删除计划任务")
async def delete_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """删除计划任务"""
    service = ProductionService(db)
    result = await service.delete_task(task_id)
    if not result:
        return ApiResponse(code=404, message="任务不存在")
    await db.commit()
    return ApiResponse(message="删除成功")


# ============ SalesPlanDetail Routes ============


@router.get(
    "/sales-plan-details",
    response_model=ProductionApiResponse[list[SalesPlanDetailResponse]],
    summary="获取销售执行明细列表",
)
async def get_sales_plan_details(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    product_name: str | None = Query(default=None, max_length=128),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """获取销售执行明细列表。"""
    service = ProductionService(db)
    details, total = await service.get_sales_plan_details(
        (page - 1) * page_size, page_size, product_name
    )
    return ApiResponse(
        data=[SalesPlanDetailResponse.model_validate(detail) for detail in details],
        meta={"page": page, "page_size": page_size, "total": total},
    )


@router.get(
    "/sales-plan-details/{detail_id}",
    response_model=ProductionApiResponse[SalesPlanDetailResponse],
    summary="获取销售执行明细",
)
async def get_sales_plan_detail(
    detail_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """获取单条销售执行明细。"""
    detail = await ProductionService(db).get_sales_plan_detail(detail_id)
    if not detail:
        return ApiResponse(code=404, message="销售执行明细不存在")
    return ApiResponse(data=SalesPlanDetailResponse.model_validate(detail))


@router.post(
    "/sales-plan-details",
    response_model=ProductionApiResponse[SalesPlanDetailResponse],
    summary="创建销售执行明细",
)
async def create_sales_plan_detail(
    data: SalesPlanDetailCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """创建销售执行明细。"""
    detail = await ProductionService(db).create_sales_plan_detail(data)
    await db.commit()
    return ApiResponse(data=SalesPlanDetailResponse.model_validate(detail))


@router.put(
    "/sales-plan-details/{detail_id}",
    response_model=ProductionApiResponse[SalesPlanDetailResponse],
    summary="更新销售执行明细",
)
async def update_sales_plan_detail(
    detail_id: uuid.UUID,
    data: SalesPlanDetailUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """更新销售执行明细。"""
    detail = await ProductionService(db).update_sales_plan_detail(detail_id, data)
    if not detail:
        return ApiResponse(code=404, message="销售执行明细不存在")
    await db.commit()
    return ApiResponse(data=SalesPlanDetailResponse.model_validate(detail))


@router.delete(
    "/sales-plan-details/{detail_id}",
    response_model=ProductionApiResponse[None],
    summary="删除销售执行明细",
)
async def delete_sales_plan_detail(
    detail_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """删除销售执行明细。"""
    deleted = await ProductionService(db).delete_sales_plan_detail(detail_id)
    if not deleted:
        return ApiResponse(code=404, message="销售执行明细不存在")
    await db.commit()
    return ApiResponse(message="删除成功")


# ============ ProcessSpec Routes ============


@router.get("/process-specs", response_model=ApiResponse, summary="获取工艺规程列表")
async def get_process_specs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: str | None = None,
    product_code: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """获取工艺规程列表"""
    service = ProductionService(db)
    skip = (page - 1) * page_size
    specs, total = await service.get_process_specs(
        skip, page_size, status, product_code
    )
    return ApiResponse(
        data=[ProcessSpecResponse.model_validate(s) for s in specs],
        meta={"page": page, "page_size": page_size, "total": total},
    )


@router.get(
    "/process-specs/{spec_id}", response_model=ApiResponse, summary="获取工艺规程详情"
)
async def get_process_spec(
    spec_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """获取工艺规程详情"""
    service = ProductionService(db)
    spec = await service.get_process_spec(spec_id)
    if not spec:
        return ApiResponse(code=404, message="工艺规程不存在")
    return ApiResponse(data=ProcessSpecResponse.model_validate(spec))


@router.post("/process-specs", response_model=ApiResponse, summary="创建工艺规程")
async def create_process_spec(
    data: ProcessSpecCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """创建工艺规程"""
    service = ProductionService(db)
    spec = await service.create_process_spec(data)
    await db.commit()
    return ApiResponse(data=ProcessSpecResponse.model_validate(spec))


@router.put(
    "/process-specs/{spec_id}", response_model=ApiResponse, summary="更新工艺规程"
)
async def update_process_spec(
    spec_id: uuid.UUID,
    data: ProcessSpecUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """更新工艺规程"""
    service = ProductionService(db)
    spec = await service.update_process_spec(spec_id, data)
    if not spec:
        return ApiResponse(code=404, message="工艺规程不存在")
    await db.commit()
    return ApiResponse(data=ProcessSpecResponse.model_validate(spec))


@router.delete(
    "/process-specs/{spec_id}", response_model=ApiResponse, summary="删除工艺规程"
)
async def delete_process_spec(
    spec_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """删除工艺规程"""
    service = ProductionService(db)
    result = await service.delete_process_spec(spec_id)
    if not result:
        return ApiResponse(code=404, message="工艺规程不存在")
    await db.commit()
    return ApiResponse(message="删除成功")


# ============ ProcessStep Routes =====


@router.get(
    "/process-specs/{spec_id}/steps",
    response_model=ApiResponse,
    summary="获取工艺步骤列表",
)
async def get_process_steps(
    spec_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """获取工艺步骤列表"""
    service = ProductionService(db)
    steps = await service.get_steps(spec_id)
    return ApiResponse(data=[ProcessStepResponse.model_validate(s) for s in steps])


@router.post("/steps", response_model=ApiResponse, summary="创建工艺步骤")
async def create_process_step(
    data: ProcessStepCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """创建工艺步骤"""
    service = ProductionService(db)
    step = await service.create_process_step(data)
    await db.commit()
    return ApiResponse(data=ProcessStepResponse.model_validate(step))


@router.put("/steps/{step_id}", response_model=ApiResponse, summary="更新工艺步骤")
async def update_process_step(
    step_id: uuid.UUID,
    data: ProcessStepUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """更新工艺步骤"""
    service = ProductionService(db)
    step = await service.update_process_step(step_id, data)
    if not step:
        return ApiResponse(code=404, message="步骤不存在")
    await db.commit()
    return ApiResponse(data=ProcessStepResponse.model_validate(step))


@router.delete("/steps/{step_id}", response_model=ApiResponse, summary="删除工艺步骤")
async def delete_process_step(
    step_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """删除工艺步骤"""
    service = ProductionService(db)
    result = await service.delete_process_step(step_id)
    if not result:
        return ApiResponse(code=404, message="步骤不存在")
    await db.commit()
    return ApiResponse(message="删除成功")


# ============ ProcessParameter Routes ============


@router.get(
    "/steps/{step_id}/parameters",
    response_model=ApiResponse,
    summary="获取工艺参数列表",
)
async def get_process_parameters(
    step_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """获取工艺参数列表"""
    service = ProductionService(db)
    params = await service.get_parameters(step_id)
    return ApiResponse(
        data=[ProcessParameterResponse.model_validate(p) for p in params]
    )


@router.post("/parameters", response_model=ApiResponse, summary="创建工艺参数")
async def create_process_parameter(
    data: ProcessParameterCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """创建工艺参数"""
    service = ProductionService(db)
    param = await service.create_process_parameter(data)
    await db.commit()
    return ApiResponse(data=ProcessParameterResponse.model_validate(param))


@router.delete(
    "/parameters/{param_id}", response_model=ApiResponse, summary="删除工艺参数"
)
async def delete_process_parameter(
    param_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """删除工艺参数"""
    service = ProductionService(db)
    result = await service.delete_process_parameter(param_id)
    if not result:
        return ApiResponse(code=404, message="参数不存在")
    await db.commit()
    return ApiResponse(message="删除成功")


# ============ ProductionRecord Routes ============


@router.get(
    "/batches/{batch_id}/records",
    response_model=ApiResponse,
    summary="获取生产记录列表",
)
async def get_production_records(
    batch_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """获取生产记录列表"""
    service = ProductionService(db)
    skip = (page - 1) * page_size
    records = await service.get_records(batch_id, skip, page_size)
    return ApiResponse(
        data=[ProductionRecordResponse.model_validate(r) for r in records]
    )


@router.post("/records", response_model=ApiResponse, summary="创建生产记录")
async def create_production_record(
    data: ProductionRecordCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """创建生产记录"""
    service = ProductionService(db)
    record = await service.create_production_record(data)
    await db.commit()
    return ApiResponse(data=ProductionRecordResponse.model_validate(record))


@router.put("/records/{record_id}", response_model=ApiResponse, summary="更新生产记录")
async def update_production_record(
    record_id: uuid.UUID,
    data: ProductionRecordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """更新生产记录"""
    service = ProductionService(db)
    record = await service.update_production_record(record_id, data)
    if not record:
        return ApiResponse(code=404, message="记录不存在")
    await db.commit()
    return ApiResponse(data=ProductionRecordResponse.model_validate(record))


@router.delete(
    "/records/{record_id}", response_model=ApiResponse, summary="删除生产记录"
)
async def delete_production_record(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """删除生产记录"""
    service = ProductionService(db)
    result = await service.delete_production_record(record_id)
    if not result:
        return ApiResponse(code=404, message="记录不存在")
    await db.commit()
    return ApiResponse(message="删除成功")


# ============ MaterialBalance Routes ============


@router.get(
    "/batches/{batch_id}/balance", response_model=ApiResponse, summary="获取物料平衡"
)
async def get_material_balance(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """获取物料平衡"""
    service = ProductionService(db)
    balance = await service.get_material_balance(batch_id)
    if not balance:
        return ApiResponse(code=404, message="物料平衡不存在")
    return ApiResponse(data=MaterialBalanceResponse.model_validate(balance))


@router.post(
    "/batches/{batch_id}/balance/calculate",
    response_model=ApiResponse,
    summary="计算物料平衡",
)
async def calculate_material_balance(
    batch_id: uuid.UUID,
    min_balance_rate: float = Query(95.0, ge=0, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """计算物料平衡"""
    service = ProductionService(db)
    balance = await service.calculate_material_balance(batch_id, min_balance_rate)
    if not balance:
        return ApiResponse(code=404, message="批次不存在")
    await db.commit()
    return ApiResponse(data=MaterialBalanceResponse.model_validate(balance))


@router.put(
    "/batches/{batch_id}/balance", response_model=ApiResponse, summary="更新物料平衡"
)
async def update_material_balance(
    batch_id: uuid.UUID,
    data: MaterialBalanceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """更新物料平衡"""
    service = ProductionService(db)
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    balance = await service.update_material_balance(batch_id, update_data)
    if not balance:
        return ApiResponse(code=404, message="物料平衡不存在")
    await db.commit()
    return ApiResponse(data=MaterialBalanceResponse.model_validate(balance))


# ============ 压差统计路由 ============
router.include_router(pressure_router, tags=["压差统计"])
router.include_router(process_execution_router, tags=["生产工序执行"])
router.include_router(operations_router, tags=["发酵与生产日志"])
