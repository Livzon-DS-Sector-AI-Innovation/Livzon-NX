"""HTTP API for suppliers, complaints, return/recall and product quality."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.response import paginated_response, success_response
from app.modules.quality.schemas.external_quality import (
    ComplaintListResponse,
    ComplaintResponse,
    CompleteProductQualityRecordRequest,
    CompleteReturnRecallRequest,
    CreateComplaintRequest,
    CreateProductQualityRecordRequest,
    CreateProductQualityStandardItemRequest,
    CreateReturnRecallRequest,
    CreateSupplierQualificationRequest,
    CreateSupplierRequest,
    ExternalQualityFeishuSyncResponse,
    ProductQualityRecordListResponse,
    ProductQualityRecordOut,
    ProductQualityRecordResponse,
    ProductQualityStandardItemListResponse,
    ProductQualityStandardItemOut,
    ProductQualityStandardItemResponse,
    RespondComplaintRequest,
    ReturnRecallListResponse,
    ReturnRecallResponse,
    StartReturnRecallProcessingRequest,
    SupplierListResponse,
    SupplierOut,
    SupplierQualificationListResponse,
    SupplierQualificationOut,
    SupplierQualificationResponse,
    SupplierResponse,
    UpdateComplaintRequest,
    UpdateProductQualityRecordRequest,
    UpdateProductQualityStandardItemRequest,
    UpdateReturnRecallRequest,
    UpdateSupplierQualificationRequest,
    UpdateSupplierRequest,
)
from app.modules.quality.schemas.external_quality import (
    ExternalComplaintOut as ComplaintOut,
)
from app.modules.quality.schemas.external_quality import (
    ExternalReturnRecallOut as ReturnRecallOut,
)
from app.modules.quality.service import external_quality as external_quality_service
from app.modules.quality.service import external_quality_feishu

router = APIRouter()


def _serialize(schema: type[BaseModel], record: Any) -> dict[str, Any]:
    return schema.model_validate(record).model_dump(mode="json")


async def _list_records(
    resource_code: str,
    schema: type[BaseModel],
    *,
    filters: dict[str, Any],
    keyword: str | None,
    page: int,
    page_size: int,
    db: AsyncSession,
) -> JSONResponse:
    records, total = await external_quality_service.list_resource_records(
        db,
        resource_code,
        filters=filters,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return paginated_response(
        data=[_serialize(schema, record) for record in records],
        page=page,
        page_size=page_size,
        total=total,
    )


async def _create_record(
    resource_code: str,
    schema: type[BaseModel],
    data: BaseModel,
    db: AsyncSession,
) -> JSONResponse:
    record = await external_quality_service.create_resource_record(
        db, resource_code, data.model_dump()
    )
    return success_response(data=_serialize(schema, record), message="创建成功")


async def _get_record(
    resource_code: str,
    schema: type[BaseModel],
    record_id: uuid.UUID,
    db: AsyncSession,
) -> JSONResponse:
    record = await external_quality_service.get_resource_record(
        db, resource_code, record_id
    )
    return success_response(data=_serialize(schema, record))


async def _update_record(
    resource_code: str,
    schema: type[BaseModel],
    record_id: uuid.UUID,
    data: BaseModel,
    db: AsyncSession,
) -> JSONResponse:
    try:
        record = await external_quality_service.update_resource_record(
            db, resource_code, record_id, data.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(data=_serialize(schema, record), message="更新成功")


async def _delete_record(
    resource_code: str, record_id: uuid.UUID, db: AsyncSession
) -> JSONResponse:
    await external_quality_service.delete_resource_record(db, resource_code, record_id)
    return success_response(message="删除成功")


async def _sync_record(
    resource_code: str, record_id: uuid.UUID, db: AsyncSession
) -> JSONResponse:
    try:
        result = await external_quality_feishu.sync_external_quality_record_to_feishu(
            db, resource_code=resource_code, record_id=record_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(data=result, message="已推送至飞书")


@router.get("/suppliers", summary="获取供应商列表", response_model=SupplierListResponse)
async def list_suppliers(
    status: str | None = Query(
        default=None, pattern="^(active|suspended|blacklisted)$"
    ),
    category: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    return await _list_records(
        "suppliers",
        SupplierOut,
        filters={"status": status, "category": category},
        keyword=keyword,
        page=page,
        page_size=page_size,
        db=db,
    )


@router.post("/suppliers", summary="创建供应商", response_model=SupplierResponse)
async def create_supplier(
    data: CreateSupplierRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _create_record("suppliers", SupplierOut, data, db)


@router.get(
    "/suppliers/{supplier_id}",
    summary="获取供应商详情",
    response_model=SupplierResponse,
)
async def get_supplier(
    supplier_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> JSONResponse:
    return await _get_record("suppliers", SupplierOut, supplier_id, db)


@router.put(
    "/suppliers/{supplier_id}", summary="更新供应商", response_model=SupplierResponse
)
async def update_supplier(
    supplier_id: uuid.UUID,
    data: UpdateSupplierRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _update_record("suppliers", SupplierOut, supplier_id, data, db)


@router.delete("/suppliers/{supplier_id}", summary="删除供应商")
async def delete_supplier(
    supplier_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _delete_record("suppliers", supplier_id, db)


@router.post(
    "/suppliers/{supplier_id}/sync-to-feishu",
    summary="推送供应商至飞书",
    response_model=ExternalQualityFeishuSyncResponse,
)
async def sync_supplier_to_feishu(
    supplier_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _sync_record("suppliers", supplier_id, db)


@router.get(
    "/suppliers/{supplier_id}/qualifications",
    summary="获取供应商资质",
    response_model=SupplierQualificationListResponse,
)
async def list_supplier_qualifications(
    supplier_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> JSONResponse:
    records = await external_quality_service.list_supplier_qualifications(
        db, supplier_id
    )
    return success_response(
        data=[_serialize(SupplierQualificationOut, record) for record in records]
    )


@router.post(
    "/suppliers/{supplier_id}/qualifications",
    summary="创建供应商资质",
    response_model=SupplierQualificationResponse,
)
async def create_supplier_qualification(
    supplier_id: uuid.UUID,
    data: CreateSupplierQualificationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    record = await external_quality_service.create_supplier_qualification(
        db, supplier_id, data.model_dump()
    )
    return success_response(
        data=_serialize(SupplierQualificationOut, record), message="创建成功"
    )


@router.put(
    "/supplier-qualifications/{qualification_id}",
    summary="更新供应商资质",
    response_model=SupplierQualificationResponse,
)
async def update_supplier_qualification(
    qualification_id: uuid.UUID,
    data: UpdateSupplierQualificationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    record = await external_quality_service.update_supplier_qualification(
        db, qualification_id, data.model_dump(exclude_unset=True)
    )
    return success_response(
        data=_serialize(SupplierQualificationOut, record), message="更新成功"
    )


@router.delete("/supplier-qualifications/{qualification_id}", summary="删除供应商资质")
async def delete_supplier_qualification(
    qualification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    await external_quality_service.delete_supplier_qualification(db, qualification_id)
    return success_response(message="删除成功")


@router.post(
    "/supplier-qualifications/{qualification_id}/sync-to-feishu",
    summary="推送供应商资质至飞书",
    response_model=ExternalQualityFeishuSyncResponse,
)
async def sync_supplier_qualification_to_feishu(
    qualification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _sync_record("supplier_qualifications", qualification_id, db)


@router.get("/complaints", summary="获取投诉列表", response_model=ComplaintListResponse)
async def list_complaints(
    status: str | None = Query(
        default=None, pattern="^(pending|investigating|responded|closed)$"
    ),
    complaint_category: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    return await _list_records(
        "complaints",
        ComplaintOut,
        filters={"status": status, "complaint_category": complaint_category},
        keyword=keyword,
        page=page,
        page_size=page_size,
        db=db,
    )


@router.post("/complaints", summary="创建投诉", response_model=ComplaintResponse)
async def create_complaint(
    data: CreateComplaintRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _create_record("complaints", ComplaintOut, data, db)


@router.get(
    "/complaints/{complaint_id}",
    summary="获取投诉详情",
    response_model=ComplaintResponse,
)
async def get_complaint(
    complaint_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> JSONResponse:
    return await _get_record("complaints", ComplaintOut, complaint_id, db)


@router.put(
    "/complaints/{complaint_id}", summary="更新投诉", response_model=ComplaintResponse
)
async def update_complaint(
    complaint_id: uuid.UUID,
    data: UpdateComplaintRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _update_record("complaints", ComplaintOut, complaint_id, data, db)


@router.delete("/complaints/{complaint_id}", summary="删除投诉")
async def delete_complaint(
    complaint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _delete_record("complaints", complaint_id, db)


@router.post(
    "/complaints/{complaint_id}/start-investigation",
    summary="启动投诉调查",
    response_model=ComplaintResponse,
)
async def start_complaint_investigation(
    complaint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    try:
        record = await external_quality_service.start_complaint_investigation(
            db, complaint_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(data=_serialize(ComplaintOut, record), message="已启动调查")


@router.post(
    "/complaints/{complaint_id}/respond",
    summary="提交投诉回复",
    response_model=ComplaintResponse,
)
async def respond_to_complaint(
    complaint_id: uuid.UUID,
    data: RespondComplaintRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    try:
        record = await external_quality_service.respond_to_complaint(
            db,
            complaint_id,
            investigation_result=data.investigation_result,
            response_content=data.response_content,
            response_date=data.response_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(data=_serialize(ComplaintOut, record), message="已提交回复")


@router.post(
    "/complaints/{complaint_id}/close",
    summary="关闭投诉",
    response_model=ComplaintResponse,
)
async def close_complaint(
    complaint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    try:
        record = await external_quality_service.close_complaint(db, complaint_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(data=_serialize(ComplaintOut, record), message="已关闭")


@router.post(
    "/complaints/{complaint_id}/sync-to-feishu",
    summary="推送投诉至飞书",
    response_model=ExternalQualityFeishuSyncResponse,
)
async def sync_complaint_to_feishu(
    complaint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _sync_record("complaints", complaint_id, db)


@router.get(
    "/return-recalls",
    summary="获取退货/召回列表",
    response_model=ReturnRecallListResponse,
)
async def list_return_recalls(
    record_type: str | None = Query(default=None, pattern="^(return|recall)$"),
    status: str | None = Query(
        default=None, pattern="^(pending|assessing|processing|completed)$"
    ),
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    return await _list_records(
        "return_recalls",
        ReturnRecallOut,
        filters={"record_type": record_type, "status": status},
        keyword=keyword,
        page=page,
        page_size=page_size,
        db=db,
    )


@router.post(
    "/return-recalls", summary="创建退货/召回记录", response_model=ReturnRecallResponse
)
async def create_return_recall(
    data: CreateReturnRecallRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _create_record("return_recalls", ReturnRecallOut, data, db)


@router.get(
    "/return-recalls/{record_id}",
    summary="获取退货/召回详情",
    response_model=ReturnRecallResponse,
)
async def get_return_recall(
    record_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> JSONResponse:
    return await _get_record("return_recalls", ReturnRecallOut, record_id, db)


@router.put(
    "/return-recalls/{record_id}",
    summary="更新退货/召回记录",
    response_model=ReturnRecallResponse,
)
async def update_return_recall(
    record_id: uuid.UUID,
    data: UpdateReturnRecallRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _update_record("return_recalls", ReturnRecallOut, record_id, data, db)


@router.delete("/return-recalls/{record_id}", summary="删除退货/召回记录")
async def delete_return_recall(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _delete_record("return_recalls", record_id, db)


@router.post(
    "/return-recalls/{record_id}/start-assessment",
    summary="启动退货/召回评估",
    response_model=ReturnRecallResponse,
)
async def start_return_recall_assessment(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    try:
        record = await external_quality_service.start_return_recall_assessment(
            db, record_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(
        data=_serialize(ReturnRecallOut, record), message="已启动评估"
    )


@router.post(
    "/return-recalls/{record_id}/start-processing",
    summary="进入退货/召回处置",
    response_model=ReturnRecallResponse,
)
async def start_return_recall_processing(
    record_id: uuid.UUID,
    data: StartReturnRecallProcessingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    try:
        record = await external_quality_service.start_return_recall_processing(
            db, record_id, data.assessment_date
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(
        data=_serialize(ReturnRecallOut, record), message="已进入处置"
    )


@router.post(
    "/return-recalls/{record_id}/complete",
    summary="完成退货/召回处置",
    response_model=ReturnRecallResponse,
)
async def complete_return_recall(
    record_id: uuid.UUID,
    data: CompleteReturnRecallRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    try:
        record = await external_quality_service.complete_return_recall(
            db,
            record_id,
            disposition=data.disposition,
            completion_date=data.completion_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(
        data=_serialize(ReturnRecallOut, record), message="已完成处置"
    )


@router.post(
    "/return-recalls/{record_id}/sync-to-feishu",
    summary="推送退货/召回记录至飞书",
    response_model=ExternalQualityFeishuSyncResponse,
)
async def sync_return_recall_to_feishu(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _sync_record("return_recalls", record_id, db)


@router.get(
    "/product-quality",
    summary="获取产品质量记录",
    response_model=ProductQualityRecordListResponse,
)
async def list_product_quality_records(
    record_type: str | None = Query(
        default=None, pattern="^(annual_review|customer_standard)$"
    ),
    status: str | None = Query(default=None, pattern="^(draft|completed|approved)$"),
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    return await _list_records(
        "product_quality_records",
        ProductQualityRecordOut,
        filters={"record_type": record_type, "status": status},
        keyword=keyword,
        page=page,
        page_size=page_size,
        db=db,
    )


@router.post(
    "/product-quality",
    summary="创建产品质量记录",
    response_model=ProductQualityRecordResponse,
)
async def create_product_quality_record(
    data: CreateProductQualityRecordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _create_record(
        "product_quality_records", ProductQualityRecordOut, data, db
    )


@router.get(
    "/product-quality/{record_id}",
    summary="获取产品质量详情",
    response_model=ProductQualityRecordResponse,
)
async def get_product_quality_record(
    record_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> JSONResponse:
    return await _get_record(
        "product_quality_records", ProductQualityRecordOut, record_id, db
    )


@router.put(
    "/product-quality/{record_id}",
    summary="更新产品质量记录",
    response_model=ProductQualityRecordResponse,
)
async def update_product_quality_record(
    record_id: uuid.UUID,
    data: UpdateProductQualityRecordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _update_record(
        "product_quality_records", ProductQualityRecordOut, record_id, data, db
    )


@router.delete("/product-quality/{record_id}", summary="删除产品质量记录")
async def delete_product_quality_record(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _delete_record("product_quality_records", record_id, db)


@router.post(
    "/product-quality/{record_id}/complete",
    summary="完成产品质量记录",
    response_model=ProductQualityRecordResponse,
)
async def complete_product_quality_record(
    record_id: uuid.UUID,
    data: CompleteProductQualityRecordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    try:
        record = await external_quality_service.complete_product_quality_record(
            db,
            record_id,
            conclusion=data.conclusion,
            reviewer=data.reviewer,
            review_date=data.review_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(
        data=_serialize(ProductQualityRecordOut, record), message="已完成"
    )


@router.post(
    "/product-quality/{record_id}/approve",
    summary="批准产品质量记录",
    response_model=ProductQualityRecordResponse,
)
async def approve_product_quality_record(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    try:
        record = await external_quality_service.approve_product_quality_record(
            db, record_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(
        data=_serialize(ProductQualityRecordOut, record), message="已批准"
    )


@router.post(
    "/product-quality/{record_id}/sync-to-feishu",
    summary="推送产品质量记录至飞书",
    response_model=ExternalQualityFeishuSyncResponse,
)
async def sync_product_quality_record_to_feishu(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _sync_record("product_quality_records", record_id, db)


@router.get(
    "/product-quality/{record_id}/standard-items",
    summary="获取产品质量标准明细",
    response_model=ProductQualityStandardItemListResponse,
)
async def list_product_quality_standard_items(
    record_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> JSONResponse:
    records = await external_quality_service.list_product_quality_standard_items(
        db, record_id
    )
    return success_response(
        data=[_serialize(ProductQualityStandardItemOut, record) for record in records]
    )


@router.post(
    "/product-quality/{record_id}/standard-items",
    summary="创建产品质量标准明细",
    response_model=ProductQualityStandardItemResponse,
)
async def create_product_quality_standard_item(
    record_id: uuid.UUID,
    data: CreateProductQualityStandardItemRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    record = await external_quality_service.create_product_quality_standard_item(
        db, record_id, data.model_dump()
    )
    return success_response(
        data=_serialize(ProductQualityStandardItemOut, record), message="创建成功"
    )


@router.put(
    "/product-quality-standard-items/{item_id}",
    summary="更新产品质量标准明细",
    response_model=ProductQualityStandardItemResponse,
)
async def update_product_quality_standard_item(
    item_id: uuid.UUID,
    data: UpdateProductQualityStandardItemRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    record = await external_quality_service.update_product_quality_standard_item(
        db, item_id, data.model_dump(exclude_unset=True)
    )
    return success_response(
        data=_serialize(ProductQualityStandardItemOut, record), message="更新成功"
    )


@router.delete(
    "/product-quality-standard-items/{item_id}", summary="删除产品质量标准明细"
)
async def delete_product_quality_standard_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    await external_quality_service.delete_product_quality_standard_item(db, item_id)
    return success_response(message="删除成功")


@router.post(
    "/product-quality-standard-items/{item_id}/sync-to-feishu",
    summary="推送产品质量标准明细至飞书",
    response_model=ExternalQualityFeishuSyncResponse,
)
async def sync_product_quality_standard_item_to_feishu(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    return await _sync_record("product_quality_standard_items", item_id, db)
