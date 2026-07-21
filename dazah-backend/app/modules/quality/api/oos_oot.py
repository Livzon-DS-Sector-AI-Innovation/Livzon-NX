"""HTTP API for OOS/OOT ledger lifecycle and OOT limit configuration."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.response import paginated_response, success_response
from app.modules.quality.schemas.oos_oot import (
    CloseOosOotRecordRequest,
    CreateOosOotRecordRequest,
    CreateOotLimitItemRequest,
    CreateOotLimitProductRequest,
    OosOotFeishuSyncResponse,
    OosOotRecordListResponse,
    OosOotRecordOut,
    OosOotRecordResponse,
    OotLimitItemListResponse,
    OotLimitItemOut,
    OotLimitItemResponse,
    OotLimitProductListResponse,
    OotLimitProductOut,
    OotLimitProductResponse,
    UpdateOosOotRecordRequest,
    UpdateOotLimitItemRequest,
    UpdateOotLimitProductRequest,
)
from app.modules.quality.service import oos_oot as oos_oot_service
from app.modules.quality.service import oos_oot_feishu

router = APIRouter()


def _serialize(schema: type[BaseModel], record: Any) -> dict[str, Any]:
    return schema.model_validate(record).model_dump(mode="json")


@router.get(
    "/oos-oot/records",
    summary="获取 OOS/OOT 台账",
    response_model=OosOotRecordListResponse,
)
async def list_oos_oot_records(
    record_type: str | None = Query(default=None, pattern="^(OOS|OOT)$"),
    status: str | None = Query(default=None, pattern="^(open|investigating|closed)$"),
    keyword: str | None = Query(default=None, description="关键词"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    records, total = await oos_oot_service.list_oos_oot_records(
        db,
        record_type=record_type,
        status=status,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return paginated_response(
        data=[_serialize(OosOotRecordOut, record) for record in records],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post(
    "/oos-oot/records",
    summary="创建 OOS/OOT 记录",
    response_model=OosOotRecordResponse,
)
async def create_oos_oot_record(
    data: CreateOosOotRecordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    record = await oos_oot_service.create_oos_oot_record(db, data.model_dump())
    return success_response(
        data=_serialize(OosOotRecordOut, record), message="创建成功"
    )


@router.get(
    "/oos-oot/records/{record_id}",
    summary="获取 OOS/OOT 记录详情",
    response_model=OosOotRecordResponse,
)
async def get_oos_oot_record(
    record_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> JSONResponse:
    record = await oos_oot_service.get_oos_oot_record(db, record_id)
    return success_response(data=_serialize(OosOotRecordOut, record))


@router.put(
    "/oos-oot/records/{record_id}",
    summary="更新 OOS/OOT 记录",
    response_model=OosOotRecordResponse,
)
async def update_oos_oot_record(
    record_id: uuid.UUID,
    data: UpdateOosOotRecordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    try:
        record = await oos_oot_service.update_oos_oot_record(
            db, record_id, data.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(
        data=_serialize(OosOotRecordOut, record), message="更新成功"
    )


@router.delete("/oos-oot/records/{record_id}", summary="删除 OOS/OOT 记录")
async def delete_oos_oot_record(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    await oos_oot_service.delete_oos_oot_record(db, record_id)
    return success_response(message="删除成功")


@router.post(
    "/oos-oot/records/{record_id}/start-investigation",
    summary="启动 OOS/OOT 调查",
    response_model=OosOotRecordResponse,
)
async def start_oos_oot_investigation(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    try:
        record = await oos_oot_service.start_oos_oot_investigation(db, record_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(
        data=_serialize(OosOotRecordOut, record), message="已启动调查"
    )


@router.post(
    "/oos-oot/records/{record_id}/close",
    summary="关闭 OOS/OOT 记录",
    response_model=OosOotRecordResponse,
)
async def close_oos_oot_record(
    record_id: uuid.UUID,
    data: CloseOosOotRecordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    try:
        record = await oos_oot_service.close_oos_oot_record(
            db,
            record_id,
            investigation_result=data.investigation_result,
            corrective_actions=data.corrective_actions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(data=_serialize(OosOotRecordOut, record), message="已关闭")


@router.post(
    "/oos-oot/records/{record_id}/sync-to-feishu",
    summary="推送 OOS/OOT 记录至飞书",
    response_model=OosOotFeishuSyncResponse,
)
async def sync_oos_oot_record_to_feishu(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    try:
        return success_response(
            data=await oos_oot_feishu.sync_oos_oot_record_to_feishu(
                db, record_id=record_id
            ),
            message="已推送至飞书",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/oos-oot/oot-limits/products",
    summary="获取 OOT 限度产品",
    response_model=OotLimitProductListResponse,
)
async def list_oot_limit_products(
    keyword: str | None = Query(default=None, description="关键词"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    products = await oos_oot_service.list_oot_limit_products(db, keyword=keyword)
    return success_response(
        data=[_serialize(OotLimitProductOut, product) for product in products]
    )


@router.post(
    "/oos-oot/oot-limits/products",
    summary="创建 OOT 限度产品",
    response_model=OotLimitProductResponse,
)
async def create_oot_limit_product(
    data: CreateOotLimitProductRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    product = await oos_oot_service.create_oot_limit_product(db, data.model_dump())
    return success_response(
        data=_serialize(OotLimitProductOut, product), message="创建成功"
    )


@router.get(
    "/oos-oot/oot-limits/products/{product_id}",
    summary="获取 OOT 限度产品详情",
    response_model=OotLimitProductResponse,
)
async def get_oot_limit_product(
    product_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> JSONResponse:
    product = await oos_oot_service.get_oot_limit_product(db, product_id)
    return success_response(data=_serialize(OotLimitProductOut, product))


@router.put(
    "/oos-oot/oot-limits/products/{product_id}",
    summary="更新 OOT 限度产品",
    response_model=OotLimitProductResponse,
)
async def update_oot_limit_product(
    product_id: uuid.UUID,
    data: UpdateOotLimitProductRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    product = await oos_oot_service.update_oot_limit_product(
        db, product_id, data.model_dump(exclude_unset=True)
    )
    return success_response(
        data=_serialize(OotLimitProductOut, product), message="更新成功"
    )


@router.delete("/oos-oot/oot-limits/products/{product_id}", summary="删除 OOT 限度产品")
async def delete_oot_limit_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    await oos_oot_service.delete_oot_limit_product(db, product_id)
    return success_response(message="删除成功")


@router.post(
    "/oos-oot/oot-limits/products/{product_id}/sync-to-feishu",
    summary="推送 OOT 限度产品至飞书",
    response_model=OosOotFeishuSyncResponse,
)
async def sync_oot_limit_product_to_feishu(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    try:
        return success_response(
            data=await oos_oot_feishu.sync_oot_limit_product_to_feishu(
                db, product_id=product_id
            ),
            message="已推送至飞书",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/oos-oot/oot-limits/products/{product_id}/items",
    summary="获取 OOT 限度项目",
    response_model=OotLimitItemListResponse,
)
async def list_oot_limit_items(
    product_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> JSONResponse:
    items = await oos_oot_service.list_oot_limit_items(db, product_id)
    return success_response(data=[_serialize(OotLimitItemOut, item) for item in items])


@router.post(
    "/oos-oot/oot-limits/products/{product_id}/items",
    summary="创建 OOT 限度项目",
    response_model=OotLimitItemResponse,
)
async def create_oot_limit_item(
    product_id: uuid.UUID,
    data: CreateOotLimitItemRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    item = await oos_oot_service.create_oot_limit_item(
        db, product_id, data.model_dump()
    )
    return success_response(data=_serialize(OotLimitItemOut, item), message="创建成功")


@router.put(
    "/oos-oot/oot-limits/items/{item_id}",
    summary="更新 OOT 限度项目",
    response_model=OotLimitItemResponse,
)
async def update_oot_limit_item(
    item_id: uuid.UUID,
    data: UpdateOotLimitItemRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    item = await oos_oot_service.update_oot_limit_item(
        db, item_id, data.model_dump(exclude_unset=True)
    )
    return success_response(data=_serialize(OotLimitItemOut, item), message="更新成功")


@router.delete("/oos-oot/oot-limits/items/{item_id}", summary="删除 OOT 限度项目")
async def delete_oot_limit_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    await oos_oot_service.delete_oot_limit_item(db, item_id)
    return success_response(message="删除成功")


@router.post(
    "/oos-oot/oot-limits/items/{item_id}/sync-to-feishu",
    summary="推送 OOT 限度项目至飞书",
    response_model=OosOotFeishuSyncResponse,
)
async def sync_oot_limit_item_to_feishu(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    try:
        return success_response(
            data=await oos_oot_feishu.sync_oot_limit_item_to_feishu(
                db, item_id=item_id
            ),
            message="已推送至飞书",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
