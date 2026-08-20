"""Production API routes."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.response import ApiResponse
from app.modules.production.schemas import (  # noqa: E402
    BatchCreate,
    BatchMaterialCreate,
    BatchMaterialResponse,
    BatchMaterialUpdate,
    BatchResponse,
    BatchStatusUpdate,
    BatchUpdate,
    MaterialBalanceResponse,
    MaterialBalanceUpdate,
    ProcessParameterCreate,
    ProcessParameterResponse,
    ProcessParameterUpdate,
    ProcessSpecCreate,
    ProcessSpecResponse,
    ProcessSpecUpdate,
    ProcessStepCreate,
    ProcessStepResponse,
    ProcessStepUpdate,
    ProductionPlanCreate,
    ProductionPlanResponse,
    ProductionPlanUpdate,
    ProductionRecordCreate,
    ProductionRecordResponse,
    ProductionRecordUpdate,
)
from app.modules.production.service import ProductionService

router = APIRouter()


# ============ Batch Routes ============


@router.get("/batches", response_model=ApiResponse, summary="获取批次列表")
async def get_batches(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: str | None = None,
    product_code: str | None = None,
    batch_no: str | None = None,
    exclude_cancelled: str | None = Query(
        None, description="是否排除已取消的批次，传入 'true' 或 'false'"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    """获取批次列表"""
    service = ProductionService(db)
    skip = (page - 1) * page_size
    # 将字符串参数转换为布尔值
    exclude_cancelled_bool = (
        exclude_cancelled is not None and exclude_cancelled.lower() == "true"
    )
    batches, total = await service.get_batches(
        skip, page_size, status, product_code, batch_no, exclude_cancelled_bool
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
):
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
):
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
):
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
):
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
):
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
):
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
):
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
):
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
):
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
    product_name: str | None = None,
    workshop: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    """获取生产计划列表"""
    service = ProductionService(db)
    skip = (page - 1) * page_size
    plans, total = await service.get_plans(skip, page_size, product_name, workshop)
    return ApiResponse(
        data=[ProductionPlanResponse.model_validate(p) for p in plans],
        meta={"page": page, "page_size": page_size, "total": total},
    )


@router.get("/plans/{plan_id}", response_model=ApiResponse, summary="获取生产计划详情")
async def get_plan(
    plan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
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
):
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
):
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
):
    """删除生产计划"""
    service = ProductionService(db)
    result = await service.delete_plan(plan_id)
    if not result:
        return ApiResponse(code=404, message="计划不存在")
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
):
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
):
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
):
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
):
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
):
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
):
    """获取工艺步骤列表"""
    service = ProductionService(db)
    steps = await service.get_steps(spec_id)
    return ApiResponse(data=[ProcessStepResponse.model_validate(s) for s in steps])


@router.post("/steps", response_model=ApiResponse, summary="创建工艺步骤")
async def create_process_step(
    data: ProcessStepCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
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
):
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
):
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
):
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
):
    """创建工艺参数"""
    service = ProductionService(db)
    param = await service.create_process_parameter(data)
    await db.commit()
    return ApiResponse(data=ProcessParameterResponse.model_validate(param))


@router.put(
    "/parameters/{param_id}", response_model=ApiResponse, summary="更新工艺参数"
)
async def update_process_parameter(
    param_id: uuid.UUID,
    data: ProcessParameterUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    """更新工艺参数"""
    service = ProductionService(db)
    param = await service.update_process_parameter(param_id, data)
    if not param:
        return ApiResponse(code=404, message="参数不存在")
    await db.commit()
    return ApiResponse(data=ProcessParameterResponse.model_validate(param))


@router.delete(
    "/parameters/{param_id}", response_model=ApiResponse, summary="删除工艺参数"
)
async def delete_process_parameter(
    param_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
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
):
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
):
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
):
    """更新生产记录"""
    service = ProductionService(db)
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    record = await service.update_production_record(record_id, update_data)
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
):
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
):
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
):
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
):
    """更新物料平衡"""
    service = ProductionService(db)
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    balance = await service.update_material_balance(batch_id, update_data)
    if not balance:
        return ApiResponse(code=404, message="物料平衡不存在")
    await db.commit()
    return ApiResponse(data=MaterialBalanceResponse.model_validate(balance))


@router.delete(
    "/batches/{batch_id}/balance", response_model=ApiResponse, summary="删除物料平衡"
)
async def delete_material_balance(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    """软删除物料平衡"""
    service = ProductionService(db)
    result = await service.delete_material_balance(batch_id)
    if not result:
        return ApiResponse(code=404, message="物料平衡不存在")
    await db.commit()
    return ApiResponse(message="删除成功")


# ============ 压差统计路由 ============
from app.modules.production.pressure_api import router as pressure_router  # noqa: E402

router.include_router(pressure_router, tags=["压差统计"])

# ============ 发酵记录路由 ============
from app.modules.production.fermentation_api import (  # noqa: E402
    router as fermentation_router,  # noqa: E402
)

router.include_router(fermentation_router, tags=["生产管理 - 发酵记录"])

# ============ 飞书同步路由 ============
from app.modules.production.production_feishu_api import (  # noqa: E402
    router as feishu_router,  # noqa: E402
)

router.include_router(feishu_router, tags=["生产管理 - 飞书同步"])

# ============ 生产日志与交接班路由 ============
from app.modules.production.shift_log_api import (  # noqa: E402
    router as shift_log_router,  # noqa: E402
)

router.include_router(shift_log_router, tags=["生产管理 - 日志与交接班"])

# ============ 班组交接确认路由 ============
from app.modules.production.shift_handover_api import (  # noqa: E402
    router as shift_handover_router,  # noqa: E402
)

router.include_router(shift_handover_router, tags=["生产管理 - 班组交接确认"])

# ============ 种子培养记录路由 ============
from app.modules.production.seed_culture_api import (  # noqa: E402
    router as seed_culture_router,  # noqa: E402
)

router.include_router(seed_culture_router, tags=["生产管理 - 种子培养"])

# ============ 非密事件与运行偏差路由 ============
from app.modules.production.nce_api import router as nce_router  # noqa: E402

router.include_router(nce_router, tags=["生产管理 - 非密事件"])

# ============ 批次全貌路由 ============
from app.modules.production.batch_profile_api import (  # noqa: E402
    router as batch_profile_router,  # noqa: E402
)

router.include_router(batch_profile_router, tags=["生产管理 - 批次全貌"])

# ============ 发酵液接收路由 ============
from app.modules.production.broth_receive_api import (  # noqa: E402
    router as broth_receive_router,  # noqa: E402
)

router.include_router(broth_receive_router, tags=["生产管理 - 发酵液接收"])

# ============ 预处理工艺路由 ============
from app.modules.production.pretreatment_api import (  # noqa: E402
    router as pretreatment_router,  # noqa: E402
)

router.include_router(pretreatment_router, tags=["生产管理 - 预处理"])

# ============ 陶瓷膜过滤路由 ============
from app.modules.production.ceramic_api import router as ceramic_router  # noqa: E402

router.include_router(ceramic_router, tags=["生产管理 - 陶瓷膜过滤"])

# ============ 一次脱色路由 ============
from app.modules.production.decolor1_api import router as decolor1_router  # noqa: E402

router.include_router(decolor1_router, tags=["生产管理 - 一次脱色"])

# ============ 一次板框过滤路由 ============
from app.modules.production.filter1_api import router as filter1_router  # noqa: E402

router.include_router(filter1_router, tags=["生产管理 - 一次板框过滤"])

# ============ 一次浓缩路由 ============
from app.modules.production.conc1_api import router as conc1_router  # noqa: E402

router.include_router(conc1_router, tags=["生产管理 - 一次浓缩"])

# ============ 一次离心路由 ============
from app.modules.production.centrifuge1_api import (  # noqa: E402
    router as centrifuge1_router,  # noqa: E402
)

router.include_router(centrifuge1_router, tags=["生产管理 - 一次离心"])

# ============ 二次重结晶脱色路由 ============
from app.modules.production.recrystallize_api import (  # noqa: E402
    router as recrystallize_router,  # noqa: E402
)

router.include_router(recrystallize_router, tags=["生产管理 - 二次重结晶脱色"])

# ============ 二次板框过滤路由 ============
from app.modules.production.filter2_api import router as filter2_router  # noqa: E402

router.include_router(filter2_router, tags=["生产管理 - 二次板框过滤"])

# ============ 二次浓缩路由 ============
from app.modules.production.conc2_api import router as conc2_router  # noqa: E402

router.include_router(conc2_router, tags=["生产管理 - 二次浓缩"])

# ============ 二次离心路由 ============
from app.modules.production.centrifuge2_api import (  # noqa: E402
    router as centrifuge2_router,  # noqa: E402
)

router.include_router(centrifuge2_router, tags=["生产管理 - 二次离心"])

# ============ 烘干路由 ============
from app.modules.production.dry_api import router as dry_router  # noqa: E402

router.include_router(dry_router, tags=["生产管理 - 烘干"])

# ============ 包装路由 ============
from app.modules.production.pack_api import router as pack_router  # noqa: E402

router.include_router(pack_router, tags=["生产管理 - 包装"])

# ============ 批次进度总览路由 ============
from app.modules.production.batch_progress_api import (  # noqa: E402
    router as batch_progress_router,  # noqa: E402
)

router.include_router(batch_progress_router, tags=["生产管理 - 批次进度"])

# ============ MC（霉酚酸）粗提路由 ============
from app.modules.production.mc_crude_extract_api import (  # noqa: E402
    router as mc_crude_router,  # noqa: E402
)

router.include_router(mc_crude_router, tags=["生产管理 - MC粗提"])

# ============ MC（霉酚酸）提取路由 ============
from app.modules.production.mc_extraction_api import (  # noqa: E402
    router as mc_extraction_router,  # noqa: E402
)

router.include_router(mc_extraction_router, tags=["生产管理 - MC提取"])

# ============ MC（霉酚酸）二次精制路由 ============
from app.modules.production.mc_refinement_api import (  # noqa: E402
    router as mc_refinement_router,  # noqa: E402
)

router.include_router(mc_refinement_router, tags=["生产管理 - MC二次精制"])

# ============ MC（霉酚酸）混粉 + QC + 丁酯路由 ============
from app.modules.production.mc_blend_qc_ba_api import (  # noqa: E402
    router as mc_blend_qc_ba_router,  # noqa: E402
)

router.include_router(mc_blend_qc_ba_router, tags=["生产管理 - MC混粉/QC/丁酯"])

# ============ MC（霉酚酸）仪表盘路由 ============
from app.modules.production.mc_dashboard_api import (  # noqa: E402
    router as mc_dashboard_router,  # noqa: E402
)

router.include_router(mc_dashboard_router, tags=["生产管理 - MC仪表盘"])

# ============ MC（霉酚酸）飞书电子表格同步路由 ============
from app.modules.production.mc_feishu_sync_api import (  # noqa: E402
    router as mc_feishu_sync_router,  # noqa: E402
)

router.include_router(mc_feishu_sync_router, tags=["生产管理 - MC飞书同步"])

# ============ MC 批次血链表 ============
from app.modules.production.mc_lineage_api import (  # noqa: E402
    router as mc_lineage_router,  # noqa: E402
)

router.include_router(mc_lineage_router, tags=["生产管理 - MC批次血链表"])

from app.modules.production.ai_analysis_api import (  # noqa: E402
    router as ai_analysis_router,  # noqa: E402
)

router.include_router(ai_analysis_router, tags=["生产管理 - MC批次血链表"])

from app.modules.production.mc_chat_api import router as mc_chat_router  # noqa: E402

router.include_router(mc_chat_router, tags=["生产管理 - MC批次血链表"])

from app.modules.production.mc_yield_anomaly_api import (  # noqa: E402
    router as mc_anomaly_router,  # noqa: E402
)

router.include_router(mc_anomaly_router, tags=["生产管理 - MC收率异常检测"])

from app.modules.production.fa_api import router as fa_router  # noqa: E402

router.include_router(fa_router, tags=["生产管理 - FA苯丙氨酸"])

from app.modules.production.fa_lineage_api import (  # noqa: E402
    router as fa_lineage_router,  # noqa: E402
)

router.include_router(fa_lineage_router, tags=["生产管理 - FA批次血链表"])

from app.modules.production.fa_ai_analysis_api import (  # noqa: E402
    router as fa_ai_router,  # noqa: E402
)

router.include_router(fa_ai_router, tags=["生产管理 - FA AI分析"])

from app.modules.production.fa_chat_api import router as fa_chat_router  # noqa: E402

router.include_router(fa_chat_router, tags=["生产管理 - FA AI对话"])

from app.modules.production.fa_dashboard_api import (  # noqa: E402
    router as fa_dashboard_router,  # noqa: E402
)

router.include_router(fa_dashboard_router, tags=["生产管理 - FA 收率看板"])

# ============ DR（多拉菌素）路由 ============
from app.modules.production.dr_api import router as dr_router  # noqa: E402
from app.modules.production.fa_models import (  # noqa: F401, E402
    FaAcidificationRecord,
    FaDecolor1Record,
    FaFermentationBatch,
    FaFermentationSubBatch,
)

router.include_router(dr_router, tags=["生产管理 - DR多拉菌素"])

from app.modules.production.dr_lineage_api import (  # noqa: E402
    router as dr_lineage_router,  # noqa: E402
)
from app.modules.production.dr_models import (  # noqa: F401, E402
    DrExtraction,
    DrFermentationBatch,
    DrFermentationTank,
    DrFiltrate,
)

router.include_router(dr_lineage_router, tags=["生产管理 - DR批次追溯"])

from app.modules.production.dr_schedule_api import (  # noqa: E402
    router as dr_schedule_router,  # noqa: E402
)

router.include_router(dr_schedule_router, tags=["生产管理 - DR排产放罐计划"])

# ============ 销售计划明细路由 ============
from app.core.response import paginated_response  # noqa: E402
from app.modules.production.models import SalesPlanDetail  # noqa: E402
from app.modules.production.schemas import (  # noqa: E402
    SalesPlanDetailCreate,
    SalesPlanDetailResponse,
    SalesPlanDetailUpdate,
)


@router.get(
    "/sales-plan-details", response_model=ApiResponse, summary="获取销售计划明细列表"
)
async def get_sales_plan_details(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    product_name: str | None = None,
    session: AsyncSession = Depends(get_db),
):
    query = select(SalesPlanDetail).where(SalesPlanDetail.is_deleted.is_(False))
    count_q = select(func.count(SalesPlanDetail.id)).where(
        SalesPlanDetail.is_deleted.is_(False)
    )
    if product_name:
        query = query.where(SalesPlanDetail.product_name == product_name)
        count_q = count_q.where(SalesPlanDetail.product_name == product_name)
    total = (await session.execute(count_q)).scalar() or 0
    offset = (page - 1) * page_size
    rows = (
        (
            await session.execute(
                query.order_by(SalesPlanDetail.created_at.desc())
                .offset(offset)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return paginated_response(
        [SalesPlanDetailResponse.model_validate(r) for r in rows],
        page,
        page_size,
        total,
    )


@router.post(
    "/sales-plan-details", response_model=ApiResponse, summary="创建销售计划明细"
)
async def create_sales_plan_detail(
    data: SalesPlanDetailCreate,
    session: AsyncSession = Depends(get_db),
):
    detail = SalesPlanDetail(**data.model_dump(), source="manual")
    session.add(detail)
    await session.commit()
    await session.refresh(detail)
    return ApiResponse(data=SalesPlanDetailResponse.model_validate(detail))


@router.put(
    "/sales-plan-details/{detail_id}",
    response_model=ApiResponse,
    summary="更新销售计划明细",
)
async def update_sales_plan_detail(
    detail_id: uuid.UUID,
    data: SalesPlanDetailUpdate,
    session: AsyncSession = Depends(get_db),
):
    detail = await session.get(SalesPlanDetail, detail_id)
    if not detail or detail.is_deleted:
        return ApiResponse(code=404, message="记录不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(detail, k, v)
    await session.commit()
    await session.refresh(detail)
    return ApiResponse(data=SalesPlanDetailResponse.model_validate(detail))


@router.delete(
    "/sales-plan-details/{detail_id}",
    response_model=ApiResponse,
    summary="删除销售计划明细",
)
async def delete_sales_plan_detail(
    detail_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
):
    detail = await session.get(SalesPlanDetail, detail_id)
    if not detail or detail.is_deleted:
        return ApiResponse(code=404, message="记录不存在")
    detail.is_deleted = True
    await session.commit()
    return ApiResponse(message="删除成功")
