"""HTTP API for quality inspection foundation resources."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.response import paginated_response, success_response
from app.modules.quality.schemas.inspection import (
    CreateFinishedProductInspectionRequest,
    CreateInspectionRecordRequest,
    CreateLabInstrumentRequest,
    CreateLabItemRequest,
    CreateLiquidMaterialInspectionRequest,
    CreateSolidMaterialInspectionRequest,
    FinishedProductInspectionOut,
    InspectionRecordOut,
    LabInstrumentOut,
    LabItemOut,
    LiquidMaterialInspectionOut,
    SolidMaterialInspectionOut,
    UpdateFinishedProductInspectionRequest,
    UpdateInspectionRecordRequest,
    UpdateLabInstrumentRequest,
    UpdateLabItemRequest,
    UpdateLiquidMaterialInspectionRequest,
    UpdateSolidMaterialInspectionRequest,
)
from app.modules.quality.schemas.inspection_dashboard import (
    InspectionDashboardResponse,
    InspectionFeishuSyncResponse,
    InspectionTrendResponse,
)
from app.modules.quality.service import inspection as inspection_service
from app.modules.quality.service import inspection_dashboard, inspection_feishu

router = APIRouter()


def _serialize(schema: type[BaseModel], record: Any) -> dict[str, Any]:
    return schema.model_validate(record).model_dump(mode="json")


async def _list_records(
    resource_code: str,
    schema: type[BaseModel],
    *,
    db: AsyncSession,
    keyword: str | None,
    page: int,
    page_size: int,
    filters: dict[str, Any] | None = None,
) -> JSONResponse:
    records, total = await inspection_service.list_resource_records(
        db,
        resource_code,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters=filters,
    )
    return paginated_response(
        data=[_serialize(schema, record) for record in records],
        page=page,
        page_size=page_size,
        total=total,
    )


async def _get_record(
    resource_code: str,
    schema: type[BaseModel],
    record_id: uuid.UUID,
    db: AsyncSession,
) -> JSONResponse:
    record = await inspection_service.get_resource_record(db, resource_code, record_id)
    return success_response(data=_serialize(schema, record))


async def _create_record(
    resource_code: str,
    schema: type[BaseModel],
    data: BaseModel,
    db: AsyncSession,
) -> JSONResponse:
    record = await inspection_service.create_resource_record(
        db,
        resource_code,
        data.model_dump(),
    )
    return success_response(data=_serialize(schema, record), message="创建成功")


async def _update_record(
    resource_code: str,
    schema: type[BaseModel],
    record_id: uuid.UUID,
    data: BaseModel,
    db: AsyncSession,
) -> JSONResponse:
    record = await inspection_service.update_resource_record(
        db,
        resource_code,
        record_id,
        data.model_dump(exclude_unset=True),
    )
    return success_response(data=_serialize(schema, record), message="更新成功")


async def _delete_record(
    resource_code: str,
    record_id: uuid.UUID,
    db: AsyncSession,
) -> JSONResponse:
    await inspection_service.delete_resource_record(db, resource_code, record_id)
    return success_response(message="删除成功")


@router.get(
    "/inspection-dashboard",
    summary="获取检验管理概览",
    response_model=InspectionDashboardResponse,
)
async def get_inspection_dashboard(
    db: AsyncSession = Depends(get_db),
) -> InspectionDashboardResponse:
    return await inspection_dashboard.get_inspection_dashboard(db)


@router.get(
    "/inspection-trends",
    summary="获取检验结果趋势",
    response_model=InspectionTrendResponse,
)
async def get_inspection_trend(
    resource_code: str = Query(description="检验资源编码"),
    subject: str | None = Query(default=None, description="产品或物料名称"),
    inspection_item: str | None = Query(default=None, description="检验项目"),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> InspectionTrendResponse:
    try:
        return await inspection_dashboard.get_inspection_trend(
            db,
            resource_code=resource_code,
            subject=subject,
            inspection_item=inspection_item,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/inspection-resources/{resource_code}/{record_id}/sync-to-feishu",
    summary="将单条检验记录推送至飞书",
    response_model=InspectionFeishuSyncResponse,
)
async def sync_inspection_record_to_feishu(
    resource_code: str,
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> InspectionFeishuSyncResponse:
    try:
        return InspectionFeishuSyncResponse(
            **await inspection_feishu.sync_inspection_record_to_feishu(
                db,
                resource_code=resource_code,
                record_id=record_id,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/inspections", summary="获取检验记录列表")
async def list_inspection_records(
    inspection_type: str | None = Query(default=None, description="检验类型"),
    conclusion: str | None = Query(default=None, description="检验结论"),
    department: str | None = Query(default=None, description="检验部门"),
    keyword: str | None = Query(default=None, description="关键词"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    return await _list_records(
        "inspection_records",
        InspectionRecordOut,
        db=db,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters={
            "inspection_type": inspection_type,
            "conclusion": conclusion,
            "department": department,
        },
    )


@router.get("/inspections/{record_id}", summary="获取检验记录详情")
async def get_inspection_record(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    return await _get_record("inspection_records", InspectionRecordOut, record_id, db)


@router.post("/inspections", summary="创建检验记录")
async def create_inspection_record(
    data: CreateInspectionRecordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _create_record("inspection_records", InspectionRecordOut, data, db)


@router.put("/inspections/{record_id}", summary="更新检验记录")
async def update_inspection_record(
    record_id: uuid.UUID,
    data: UpdateInspectionRecordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _update_record(
        "inspection_records", InspectionRecordOut, record_id, data, db
    )


@router.delete("/inspections/{record_id}", summary="删除检验记录")
async def delete_inspection_record(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _delete_record("inspection_records", record_id, db)


@router.get("/lab-items", summary="获取实验室物品列表")
async def list_lab_items(
    status: str | None = Query(default=None, description="物品状态"),
    keyword: str | None = Query(default=None, description="关键词"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    return await _list_records(
        "lab_items",
        LabItemOut,
        db=db,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters={"status": status},
    )


@router.get("/lab-items/{record_id}", summary="获取实验室物品详情")
async def get_lab_item(
    record_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> JSONResponse:
    return await _get_record("lab_items", LabItemOut, record_id, db)


@router.post("/lab-items", summary="创建实验室物品")
async def create_lab_item(
    data: CreateLabItemRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _create_record("lab_items", LabItemOut, data, db)


@router.put("/lab-items/{record_id}", summary="更新实验室物品")
async def update_lab_item(
    record_id: uuid.UUID,
    data: UpdateLabItemRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _update_record("lab_items", LabItemOut, record_id, data, db)


@router.delete("/lab-items/{record_id}", summary="删除实验室物品")
async def delete_lab_item(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _delete_record("lab_items", record_id, db)


@router.get("/lab-instruments", summary="获取实验室仪器列表")
async def list_lab_instruments(
    status: str | None = Query(default=None, description="仪器状态"),
    keyword: str | None = Query(default=None, description="关键词"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    return await _list_records(
        "lab_instruments",
        LabInstrumentOut,
        db=db,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters={"status": status},
    )


@router.get("/lab-instruments/{record_id}", summary="获取实验室仪器详情")
async def get_lab_instrument(
    record_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> JSONResponse:
    return await _get_record("lab_instruments", LabInstrumentOut, record_id, db)


@router.post("/lab-instruments", summary="创建实验室仪器")
async def create_lab_instrument(
    data: CreateLabInstrumentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _create_record("lab_instruments", LabInstrumentOut, data, db)


@router.put("/lab-instruments/{record_id}", summary="更新实验室仪器")
async def update_lab_instrument(
    record_id: uuid.UUID,
    data: UpdateLabInstrumentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _update_record(
        "lab_instruments", LabInstrumentOut, record_id, data, db
    )


@router.delete("/lab-instruments/{record_id}", summary="删除实验室仪器")
async def delete_lab_instrument(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _delete_record("lab_instruments", record_id, db)


@router.get("/finished-product-inspections", summary="获取成品检验记录列表")
async def list_finished_product_inspections(
    conclusion: str | None = Query(default=None, description="检验结论"),
    keyword: str | None = Query(default=None, description="关键词"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    return await _list_records(
        "finished_product_inspections",
        FinishedProductInspectionOut,
        db=db,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters={"conclusion": conclusion},
    )


@router.get("/finished-product-inspections/{record_id}", summary="获取成品检验记录详情")
async def get_finished_product_inspection(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    return await _get_record(
        "finished_product_inspections", FinishedProductInspectionOut, record_id, db
    )


@router.post("/finished-product-inspections", summary="创建成品检验记录")
async def create_finished_product_inspection(
    data: CreateFinishedProductInspectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _create_record(
        "finished_product_inspections", FinishedProductInspectionOut, data, db
    )


@router.put("/finished-product-inspections/{record_id}", summary="更新成品检验记录")
async def update_finished_product_inspection(
    record_id: uuid.UUID,
    data: UpdateFinishedProductInspectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _update_record(
        "finished_product_inspections",
        FinishedProductInspectionOut,
        record_id,
        data,
        db,
    )


@router.delete("/finished-product-inspections/{record_id}", summary="删除成品检验记录")
async def delete_finished_product_inspection(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _delete_record("finished_product_inspections", record_id, db)


@router.get("/solid-material-inspections", summary="获取固体物料检验记录列表")
async def list_solid_material_inspections(
    conclusion: str | None = Query(default=None, description="检验结论"),
    keyword: str | None = Query(default=None, description="关键词"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    return await _list_records(
        "solid_material_inspections",
        SolidMaterialInspectionOut,
        db=db,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters={"conclusion": conclusion},
    )


@router.get(
    "/solid-material-inspections/{record_id}", summary="获取固体物料检验记录详情"
)
async def get_solid_material_inspection(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    return await _get_record(
        "solid_material_inspections", SolidMaterialInspectionOut, record_id, db
    )


@router.post("/solid-material-inspections", summary="创建固体物料检验记录")
async def create_solid_material_inspection(
    data: CreateSolidMaterialInspectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _create_record(
        "solid_material_inspections", SolidMaterialInspectionOut, data, db
    )


@router.put("/solid-material-inspections/{record_id}", summary="更新固体物料检验记录")
async def update_solid_material_inspection(
    record_id: uuid.UUID,
    data: UpdateSolidMaterialInspectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _update_record(
        "solid_material_inspections", SolidMaterialInspectionOut, record_id, data, db
    )


@router.delete(
    "/solid-material-inspections/{record_id}", summary="删除固体物料检验记录"
)
async def delete_solid_material_inspection(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _delete_record("solid_material_inspections", record_id, db)


@router.get("/liquid-material-inspections", summary="获取液体物料检验记录列表")
async def list_liquid_material_inspections(
    conclusion: str | None = Query(default=None, description="检验结论"),
    keyword: str | None = Query(default=None, description="关键词"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    return await _list_records(
        "liquid_material_inspections",
        LiquidMaterialInspectionOut,
        db=db,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters={"conclusion": conclusion},
    )


@router.get(
    "/liquid-material-inspections/{record_id}", summary="获取液体物料检验记录详情"
)
async def get_liquid_material_inspection(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    return await _get_record(
        "liquid_material_inspections", LiquidMaterialInspectionOut, record_id, db
    )


@router.post("/liquid-material-inspections", summary="创建液体物料检验记录")
async def create_liquid_material_inspection(
    data: CreateLiquidMaterialInspectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _create_record(
        "liquid_material_inspections", LiquidMaterialInspectionOut, data, db
    )


@router.put("/liquid-material-inspections/{record_id}", summary="更新液体物料检验记录")
async def update_liquid_material_inspection(
    record_id: uuid.UUID,
    data: UpdateLiquidMaterialInspectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _update_record(
        "liquid_material_inspections", LiquidMaterialInspectionOut, record_id, data, db
    )


@router.delete(
    "/liquid-material-inspections/{record_id}", summary="删除液体物料检验记录"
)
async def delete_liquid_material_inspection(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _delete_record("liquid_material_inspections", record_id, db)
