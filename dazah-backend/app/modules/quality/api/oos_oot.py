"""OOS/OOT API endpoints."""

from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException
from app.core.response import error_response, paginated_response, success_response
from app.modules.quality.api.deps import require_user as _require_user
from app.modules.quality.models.oos_oot import (
    OosOotRecord,
)
from app.modules.quality.schemas.oos_oot import (
    CreateOosOotRequest,
    OosOotRecordOut,
    UpdateOosOotRequest,
)
from app.modules.quality.schemas.oot_limit import OotLimitItemOut, OotLimitProductOut
from app.modules.quality.service import oos_oot as oos_oot_service
from app.modules.quality.service import oos_oot_feishu
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)

router = APIRouter()


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _legacy_oos_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    if "batch_number" not in normalized and "batch_no" in normalized:
        normalized["batch_number"] = normalized.pop("batch_no")
    if "discovery_date" not in normalized and "discovered_date" in normalized:
        normalized["discovery_date"] = normalized.pop("discovered_date")
    if isinstance(normalized.get("discovery_date"), str):
        normalized["discovery_date"] = date.fromisoformat(normalized["discovery_date"])
    return normalized


def _legacy_product_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["document_title"] = (
        normalized.get("document_title") or normalized.get("document_no") or ""
    )
    normalized.pop("document_no", None)
    return normalized


def _legacy_item_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized.setdefault("standard_value", normalized.get("specification") or "")
    normalized.setdefault("oot_limit_value", normalized.get("oot_limit") or "")
    normalized.pop("specification", None)
    normalized.pop("oot_limit", None)
    return normalized


@router.get(
    "/oos-oot/records",
    summary="兼容旧版 OOS/OOT 台账列表",
    response_model=ApiResponseEnvelope[list[OosOotRecordOut]],
)
async def list_legacy_oos_oot_records(
    record_type: str | None = Query(None),
    status: str | None = Query(None),
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    rows, total = await oos_oot_service.list_oos_oot_records(
        db,
        record_type=record_type,
        status=status,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return paginated_response(
        data=[
            OosOotRecordOut.model_validate(row).model_dump(mode="json") for row in rows
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post(
    "/oos-oot/records",
    summary="兼容旧版 OOS/OOT 台账创建",
    response_model=ApiResponseEnvelope[OosOotRecordOut],
)
async def create_legacy_oos_oot_record(
    payload: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    record = await oos_oot_service.create_oos_oot_record(
        db, _legacy_oos_payload(payload)
    )
    await db.commit()
    return success_response(
        data=OosOotRecordOut.model_validate(record).model_dump(mode="json"),
        message="创建成功",
    )


@router.post(
    "/oos-oot/records/{record_id}/start-investigation",
    summary="兼容旧版启动 OOS/OOT 调查",
    response_model=ApiResponseEnvelope[OosOotRecordOut],
)
async def start_legacy_oos_oot_investigation(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    record = await oos_oot_service.start_oos_oot_investigation(db, record_id)
    await db.commit()
    return success_response(
        data=OosOotRecordOut.model_validate(record).model_dump(mode="json")
    )


@router.post(
    "/oos-oot/records/{record_id}/close",
    summary="兼容旧版关闭 OOS/OOT 台账",
    response_model=ApiResponseEnvelope[OosOotRecordOut],
)
async def close_legacy_oos_oot_record(
    record_id: uuid.UUID,
    payload: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        record = await oos_oot_service.close_oos_oot_record(
            db,
            record_id,
            investigation_result=str(payload.get("investigation_result") or ""),
            corrective_actions=payload.get("corrective_actions"),
        )
    except ValueError as exc:
        raise AppException(message=str(exc), status_code=400) from exc
    await db.commit()
    return success_response(
        data=OosOotRecordOut.model_validate(record).model_dump(mode="json")
    )


@router.post(
    "/oos-oot/oot-limits/products",
    summary="兼容旧版创建 OOT 限度产品",
    response_model=ApiResponseEnvelope[OotLimitProductOut],
)
async def create_legacy_oot_limit_product(
    payload: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    normalized = _legacy_product_payload(payload)
    product = await oos_oot_service.create_oot_limit_product(db, normalized)
    await db.commit()
    return success_response(
        data=OotLimitProductOut.model_validate(product).model_dump(mode="json"),
        message="创建成功",
    )


@router.post(
    "/oos-oot/oot-limits/products/{product_id}/items",
    summary="兼容旧版创建 OOT 限度项目",
    response_model=ApiResponseEnvelope[OotLimitItemOut],
)
async def create_legacy_oot_limit_item(
    product_id: uuid.UUID,
    payload: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    normalized = _legacy_item_payload(payload)
    normalized["product_id"] = product_id
    item = await oos_oot_service.create_oot_limit_item(db, product_id, normalized)
    await db.commit()
    return success_response(
        data=OotLimitItemOut.model_validate(item).model_dump(mode="json"),
        message="创建成功",
    )


@router.post(
    "/oos-oot/records/{record_id}/sync-to-feishu",
    summary="兼容旧版显式推送 OOS/OOT 记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def sync_legacy_oos_oot_record_to_feishu(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        result = await oos_oot_feishu.sync_oos_oot_record_to_feishu(
            db, record_id=record_id
        )
    except ValueError as exc:
        raise AppException(message=str(exc), status_code=400) from exc
    return success_response(data=result)


@router.get(
    "/oos-oot",
    summary="获取OOS/OOT列表",
    response_model=ApiResponseEnvelope[list[OosOotRecordOut]],
)
async def list_oos_oot(
    record_type: str | None = Query(None, description="记录类型：OOS/OOT"),
    status: str | None = Query(None, description="状态"),
    department: str | None = Query(None, description="责任部门"),
    keyword: str | None = Query(None, description="关键词搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    assert current_user is not None
    from app.platform.identity.data_scope import (
        department_in_clause,
        resolve_user_department_scope,
    )

    scope = await resolve_user_department_scope(db, current_user)
    try:
        base_query = select(OosOotRecord).where(OosOotRecord.is_deleted.is_(False))
        count_query = (
            select(func.count())
            .select_from(OosOotRecord)
            .where(OosOotRecord.is_deleted.is_(False))
        )

        filters = []
        if record_type:
            filters.append(OosOotRecord.record_type == record_type)
        if status:
            filters.append(OosOotRecord.status == status)
        if department:
            filters.append(OosOotRecord.department == department)
        # 部门数据隔离（后台可配置可见部门范围）
        scope_clause = department_in_clause(OosOotRecord.department, scope)
        if scope_clause is not None:
            filters.append(scope_clause)
        if keyword:
            pattern = f"%{_escape_like(keyword)}%"
            filters.append(
                or_(
                    OosOotRecord.record_code.ilike(pattern),
                    OosOotRecord.title.ilike(pattern),
                    OosOotRecord.description.ilike(pattern),
                )
            )

        if filters:
            base_query = base_query.where(*filters)
            count_query = count_query.where(*filters)

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        base_query = (
            base_query.order_by(OosOotRecord.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        items_result = await db.execute(base_query)
        items = items_result.scalars().all()

        return paginated_response(
            data=[
                OosOotRecordOut.model_validate(item).model_dump(mode="json")
                for item in items
            ],
            page=page,
            page_size=page_size,
            total=total,
        )
    except Exception:
        logger.exception("Failed to list OOS/OOT records")
        return error_response(message="获取列表失败，请稍后重试", status_code=500)


@router.get(
    "/oos-oot/{record_id}",
    summary="获取OOS/OOT详情",
    response_model=ApiResponseEnvelope[OosOotRecordOut],
)
async def get_oos_oot(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        result = await db.execute(
            select(OosOotRecord).where(
                OosOotRecord.id == record_id,
                OosOotRecord.is_deleted.is_(False),
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            return error_response(message="记录不存在", status_code=404)
        return success_response(
            data=OosOotRecordOut.model_validate(item).model_dump(mode="json")
        )
    except Exception:
        logger.exception("Failed to get OOS/OOT record")
        return error_response(message="获取详情失败，请稍后重试", status_code=500)


@router.post(
    "/oos-oot",
    summary="创建OOS/OOT记录",
    response_model=ApiResponseEnvelope[OosOotRecordOut],
)
async def create_oos_oot(
    data: CreateOosOotRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        record = OosOotRecord(**data.model_dump())
        db.add(record)
        await db.flush()
        result = await db.execute(
            select(OosOotRecord).where(OosOotRecord.id == record.id)
        )
        record = result.scalar_one()
        return success_response(
            data=OosOotRecordOut.model_validate(record).model_dump(mode="json"),
            message="创建成功",
        )
    except Exception:
        logger.exception("Failed to create OOS/OOT record")
        return error_response(message="创建失败，请稍后重试", status_code=400)


@router.put(
    "/oos-oot/{record_id}",
    summary="更新OOS/OOT记录",
    response_model=ApiResponseEnvelope[OosOotRecordOut],
)
async def update_oos_oot(
    record_id: uuid.UUID,
    data: UpdateOosOotRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        result = await db.execute(
            select(OosOotRecord).where(
                OosOotRecord.id == record_id,
                OosOotRecord.is_deleted.is_(False),
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            return error_response(message="记录不存在", status_code=404)

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(item, key, value)

        await db.flush()
        result = await db.execute(
            select(OosOotRecord).where(OosOotRecord.id == item.id)
        )
        item = result.scalar_one()
        return success_response(
            data=OosOotRecordOut.model_validate(item).model_dump(mode="json"),
            message="更新成功",
        )
    except Exception:
        logger.exception("Failed to update OOS/OOT record")
        return error_response(message="更新失败，请稍后重试", status_code=400)


@router.delete(
    "/oos-oot/{record_id}",
    summary="删除OOS/OOT记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def delete_oos_oot(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        result = await db.execute(
            select(OosOotRecord).where(
                OosOotRecord.id == record_id,
                OosOotRecord.is_deleted.is_(False),
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            return error_response(message="记录不存在", status_code=404)

        item.is_deleted = True
        await db.flush()
        return success_response(message="已删除")
    except Exception:
        logger.exception("Failed to delete OOS/OOT record")
        return error_response(message="删除失败，请稍后重试", status_code=500)


# ─── Former nested-path compatibility routes ───


@router.get(
    "/oos-oot/records/{record_id}",
    summary="兼容旧版 OOS/OOT 记录详情",
    response_model=ApiResponseEnvelope[OosOotRecordOut],
)
async def get_legacy_oos_oot_record(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    record = await oos_oot_service.get_oos_oot_record(db, record_id)
    return success_response(
        data=OosOotRecordOut.model_validate(record).model_dump(mode="json")
    )


@router.put(
    "/oos-oot/records/{record_id}",
    summary="兼容旧版 OOS/OOT 记录更新",
    response_model=ApiResponseEnvelope[OosOotRecordOut],
)
async def update_legacy_oos_oot_record(
    record_id: uuid.UUID,
    payload: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        record = await oos_oot_service.update_oos_oot_record(
            db, record_id, _legacy_oos_payload(payload)
        )
    except ValueError as exc:
        raise AppException(message=str(exc), status_code=400) from exc
    await db.commit()
    return success_response(
        data=OosOotRecordOut.model_validate(record).model_dump(mode="json"),
        message="更新成功",
    )


@router.delete("/oos-oot/records/{record_id}", summary="兼容旧版 OOS/OOT 记录删除")
async def delete_legacy_oos_oot_record(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    await oos_oot_service.delete_oos_oot_record(db, record_id)
    await db.commit()
    return success_response(message="删除成功")


@router.get(
    "/oos-oot/oot-limits/products",
    summary="兼容旧版 OOT 限度产品列表",
    response_model=ApiResponseEnvelope[list[OotLimitProductOut]],
)
async def list_legacy_oot_limit_products(
    keyword: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    products = await oos_oot_service.list_oot_limit_products(db, keyword=keyword)
    return success_response(
        data=[
            OotLimitProductOut.model_validate(item).model_dump(mode="json")
            for item in products
        ]
    )


@router.get(
    "/oos-oot/oot-limits/products/{product_id}",
    summary="兼容旧版 OOT 限度产品详情",
    response_model=ApiResponseEnvelope[OotLimitProductOut],
)
async def get_legacy_oot_limit_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    product = await oos_oot_service.get_oot_limit_product(db, product_id)
    return success_response(
        data=OotLimitProductOut.model_validate(product).model_dump(mode="json")
    )


@router.put(
    "/oos-oot/oot-limits/products/{product_id}",
    summary="兼容旧版 OOT 限度产品更新",
    response_model=ApiResponseEnvelope[OotLimitProductOut],
)
async def update_legacy_oot_limit_product(
    product_id: uuid.UUID,
    payload: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    product = await oos_oot_service.update_oot_limit_product(
        db, product_id, _legacy_product_payload(payload)
    )
    await db.commit()
    return success_response(
        data=OotLimitProductOut.model_validate(product).model_dump(mode="json"),
        message="更新成功",
    )


@router.delete(
    "/oos-oot/oot-limits/products/{product_id}",
    summary="兼容旧版 OOT 限度产品删除",
)
async def delete_legacy_oot_limit_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    await oos_oot_service.delete_oot_limit_product(db, product_id)
    await db.commit()
    return success_response(message="删除成功")


@router.get(
    "/oos-oot/oot-limits/products/{product_id}/items",
    summary="兼容旧版 OOT 限度项目列表",
    response_model=ApiResponseEnvelope[list[OotLimitItemOut]],
)
async def list_legacy_oot_limit_items(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    items = await oos_oot_service.list_oot_limit_items(db, product_id)
    return success_response(
        data=[
            OotLimitItemOut.model_validate(item).model_dump(mode="json")
            for item in items
        ]
    )


@router.put(
    "/oos-oot/oot-limits/items/{item_id}",
    summary="兼容旧版 OOT 限度项目更新",
    response_model=ApiResponseEnvelope[OotLimitItemOut],
)
async def update_legacy_oot_limit_item(
    item_id: uuid.UUID,
    payload: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    item = await oos_oot_service.update_oot_limit_item(
        db, item_id, _legacy_item_payload(payload)
    )
    await db.commit()
    return success_response(
        data=OotLimitItemOut.model_validate(item).model_dump(mode="json"),
        message="更新成功",
    )


@router.delete(
    "/oos-oot/oot-limits/items/{item_id}",
    summary="兼容旧版 OOT 限度项目删除",
)
async def delete_legacy_oot_limit_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    await oos_oot_service.delete_oot_limit_item(db, item_id)
    await db.commit()
    return success_response(message="删除成功")


@router.post(
    "/oos-oot/oot-limits/products/{product_id}/sync-to-feishu",
    summary="兼容旧版推送 OOT 限度产品",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def sync_legacy_oot_limit_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        result = await oos_oot_feishu.sync_oot_limit_product_to_feishu(
            db, product_id=product_id
        )
    except ValueError as exc:
        raise AppException(message=str(exc), status_code=400) from exc
    return success_response(data=result)


@router.post(
    "/oos-oot/oot-limits/items/{item_id}/sync-to-feishu",
    summary="兼容旧版推送 OOT 限度项目",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def sync_legacy_oot_limit_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        result = await oos_oot_feishu.sync_oot_limit_item_to_feishu(db, item_id=item_id)
    except ValueError as exc:
        raise AppException(message=str(exc), status_code=400) from exc
    return success_response(data=result)
