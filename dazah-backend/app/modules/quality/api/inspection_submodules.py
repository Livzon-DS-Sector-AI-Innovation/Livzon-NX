"""Inspection sub-module API endpoints.

物品管理 / 仪器管理 / 成品检验 / 固体物料检验 / 液体物料检验
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException, NotFoundException
from app.core.response import paginated_response, success_response
from app.modules.quality.api.deps import (
    QUALITY_QA_SCOPE_PERMISSIONS,
)
from app.modules.quality.api.deps import (
    assert_quality_edit_scope as _assert_quality_edit_scope,
)
from app.modules.quality.api.deps import require_user as _require_user
from app.modules.quality.models.finished_product_inspection import (
    FinishedProductInspection,
)
from app.modules.quality.models.lab_instrument import LabInstrument

# ── Models ──
from app.modules.quality.models.lab_item import LabItem
from app.modules.quality.models.liquid_material_inspection import (
    LiquidMaterialInspection,
)
from app.modules.quality.models.solid_material_inspection import SolidMaterialInspection
from app.modules.quality.schemas.lab_instrument import (
    CreateLabInstrumentRequest,
    LabInstrumentOut,
    UpdateLabInstrumentRequest,
)

# ── Schemas ──
from app.modules.quality.schemas.lab_item import (
    CreateLabItemRequest,
    LabItemOut,
    UpdateLabItemRequest,
)
from app.modules.quality.schemas.material_inspection import (
    CreateFinishedProductInspectionRequest,
    CreateLiquidMaterialInspectionRequest,
    CreateSolidMaterialInspectionRequest,
    FinishedProductInspectionOut,
    LiquidMaterialInspectionOut,
    SolidMaterialInspectionOut,
    UpdateFinishedProductInspectionRequest,
    UpdateLiquidMaterialInspectionRequest,
    UpdateSolidMaterialInspectionRequest,
)
from app.modules.quality.service.inspection_dashboard import (
    get_inspection_dashboard,
    get_inspection_trend,
)
from app.modules.quality.service.inspection_feishu import (
    sync_inspection_record_to_feishu,
)
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)
router = APIRouter()


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ═══════════════════════════════════════════
#  Generic CRUD factory
# ═══════════════════════════════════════════


def _make_crud_routes(
    prefix: str,
    model_cls: Any,
    list_schema: Any,
    create_schema: type,
    update_schema: type,
    search_fields: list[str],
    resource_label: str = "记录",
    dept_field: str | None = None,
) -> Any:
    """Generate standard CRUD endpoints for a given model.

    dept_field: 模型上的部门字段名；提供时列表按当前用户可见部门
    （后台可配置）做行级过滤，None 则不过滤。
    """

    @router.get(
        f"/{prefix}",
        summary=f"获取{resource_label}列表",
        response_model=ApiResponseEnvelope[dict[str, Any]],
    )
    async def list_items(
        current_user: CurrentUser = None,
        keyword: str | None = Query(None, description="关键词搜索"),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=200),
        db: AsyncSession = Depends(get_db),
    ) -> Any:
        _require_user(current_user)
        assert current_user is not None
        # 部门数据隔离（后台可配置可见部门范围）；QA 角色在质量模块内全部可见
        if dept_field:
            from app.modules.quality.api.deps import (
                resolve_quality_list_scope as _resolve_quality_list_scope,
            )
            from app.platform.identity.data_scope import (
                department_in_clause,
            )

            scope = await _resolve_quality_list_scope(db, current_user)
            scope_clause = department_in_clause(getattr(model_cls, dept_field), scope)
        else:
            scope_clause = None
        base_query = select(model_cls).where(model_cls.is_deleted.is_(False))
        count_query = (
            select(func.count())
            .select_from(model_cls)
            .where(model_cls.is_deleted.is_(False))
        )

        filters = []
        if scope_clause is not None:
            filters.append(scope_clause)
        if keyword:
            pattern = f"%{_escape_like(keyword)}%"
            or_conditions = [
                getattr(model_cls, f).ilike(pattern) for f in search_fields
            ]
            filters.append(or_(*or_conditions))

        if filters:
            base_query = base_query.where(*filters)
            count_query = count_query.where(*filters)

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        base_query = (
            base_query.order_by(model_cls.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        items_result = await db.execute(base_query)
        items = items_result.scalars().all()

        return paginated_response(
            data=[
                list_schema.model_validate(item).model_dump(mode="json")
                for item in items
            ],
            page=page,
            page_size=page_size,
            total=total,
        )

    @router.get(
        f"/{prefix}/{{record_id}}",
        summary=f"获取{resource_label}详情",
        response_model=ApiResponseEnvelope[dict[str, Any]],
    )
    async def get_item(
        record_id: uuid.UUID,
        current_user: CurrentUser = None,
        db: AsyncSession = Depends(get_db),
    ) -> Any:
        _require_user(current_user)
        result = await db.execute(
            select(model_cls).where(
                model_cls.id == record_id,
                model_cls.is_deleted.is_(False),
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            raise NotFoundException(resource_label, str(record_id))
        return success_response(
            data=list_schema.model_validate(item).model_dump(mode="json")
        )

    @router.post(
        f"/{prefix}",
        summary=f"创建{resource_label}",
        response_model=ApiResponseEnvelope[dict[str, Any]],
    )
    async def create_item(
        data: Any = Body(...),
        current_user: CurrentUser = None,
        db: AsyncSession = Depends(get_db),
    ) -> Any:
        _require_user(current_user)
        record = model_cls(**data.model_dump())
        db.add(record)
        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            raise AppException(
                message=f"{resource_label}已存在相同唯一编号", status_code=409
            ) from exc
        await db.commit()
        logger.info(f"{resource_label} created", extra={"id": str(record.id)})
        return success_response(
            data=list_schema.model_validate(record).model_dump(mode="json"),
            message="创建成功",
        )

    create_item.__annotations__["data"] = create_schema

    @router.put(
        f"/{prefix}/{{record_id}}",
        summary=f"更新{resource_label}",
        response_model=ApiResponseEnvelope[dict[str, Any]],
    )
    async def update_item(
        record_id: uuid.UUID,
        data: Any = Body(...),
        current_user: CurrentUser = None,
        db: AsyncSession = Depends(get_db),
    ) -> Any:
        _require_user(current_user)
        result = await db.execute(
            select(model_cls).where(
                model_cls.id == record_id,
                model_cls.is_deleted.is_(False),
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            raise NotFoundException(resource_label, str(record_id))
        await _assert_quality_edit_scope(
            db,
            current_user,
            scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["qc"],
            record=item,
        )

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(item, key, value)

        await db.flush()
        await db.commit()

        # UPDATE 后必须 re-fetch（规范要求：禁止 db.refresh）
        re_result = await db.execute(select(model_cls).where(model_cls.id == record_id))
        item = re_result.scalar_one()

        return success_response(
            data=list_schema.model_validate(item).model_dump(mode="json"),
            message="更新成功",
        )

    update_item.__annotations__["data"] = update_schema

    @router.delete(
        f"/{prefix}/{{record_id}}",
        summary=f"删除{resource_label}",
        response_model=ApiResponseEnvelope[dict[str, Any]],
    )
    async def delete_item(
        record_id: uuid.UUID,
        current_user: CurrentUser = None,
        db: AsyncSession = Depends(get_db),
    ) -> Any:
        _require_user(current_user)
        result = await db.execute(
            select(model_cls).where(
                model_cls.id == record_id,
                model_cls.is_deleted.is_(False),
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            raise NotFoundException(resource_label, str(record_id))
        await _assert_quality_edit_scope(
            db,
            current_user,
            scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["qc"],
            record=item,
        )

        item.is_deleted = True
        await db.flush()
        await db.commit()
        return success_response(message="已删除")


# ═══════════════════════════════════════════
#  Register sub-module routes
# ═══════════════════════════════════════════

_make_crud_routes(
    prefix="lab-items",
    model_cls=LabItem,
    list_schema=LabItemOut,
    create_schema=CreateLabItemRequest,
    update_schema=UpdateLabItemRequest,
    search_fields=["name", "specification", "category", "batch_no", "supplier"],
    resource_label="物品",
)

_make_crud_routes(
    prefix="lab-instruments",
    model_cls=LabInstrument,
    list_schema=LabInstrumentOut,
    create_schema=CreateLabInstrumentRequest,
    update_schema=UpdateLabInstrumentRequest,
    search_fields=["name", "model", "serial_no", "manufacturer", "department"],
    resource_label="仪器",
    dept_field="department",
)

_make_crud_routes(
    prefix="inspection-finished",
    model_cls=FinishedProductInspection,
    list_schema=FinishedProductInspectionOut,
    create_schema=CreateFinishedProductInspectionRequest,
    update_schema=UpdateFinishedProductInspectionRequest,
    search_fields=["inspection_no", "product_name", "batch_no", "inspection_item"],
    resource_label="成品检验记录",
)

# Legacy/current clients used the longer resource name; keep it as an alias
# while the migrated UI uses /inspection-finished.
_make_crud_routes(
    prefix="finished-product-inspections",
    model_cls=FinishedProductInspection,
    list_schema=FinishedProductInspectionOut,
    create_schema=CreateFinishedProductInspectionRequest,
    update_schema=UpdateFinishedProductInspectionRequest,
    search_fields=["inspection_no", "product_name", "batch_no", "inspection_item"],
    resource_label="成品检验记录",
)

_make_crud_routes(
    prefix="solid-material-inspections",
    model_cls=SolidMaterialInspection,
    list_schema=SolidMaterialInspectionOut,
    create_schema=CreateSolidMaterialInspectionRequest,
    update_schema=UpdateSolidMaterialInspectionRequest,
    search_fields=[
        "inspection_no",
        "material_name",
        "material_batch",
        "inspection_item",
    ],
    resource_label="固体物料检验记录",
)

_make_crud_routes(
    prefix="liquid-material-inspections",
    model_cls=LiquidMaterialInspection,
    list_schema=LiquidMaterialInspectionOut,
    create_schema=CreateLiquidMaterialInspectionRequest,
    update_schema=UpdateLiquidMaterialInspectionRequest,
    search_fields=[
        "inspection_no",
        "material_name",
        "material_batch",
        "inspection_item",
    ],
    resource_label="液体物料检验记录",
)


@router.get("/inspection-trends", summary="检验趋势分析")
async def get_legacy_inspection_trend(
    resource_code: str = Query(...),
    subject: str | None = Query(None),
    inspection_item: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        result = await get_inspection_trend(
            db,
            resource_code=resource_code,
            subject=subject,
            inspection_item=inspection_item,
            limit=limit,
        )
    except ValueError as exc:
        raise AppException(message=str(exc), status_code=400) from exc
    return result.model_dump(mode="json")


@router.get("/inspection-dashboard", summary="检验资源仪表盘")
async def get_legacy_inspection_dashboard(
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    result = await get_inspection_dashboard(db)
    return result.model_dump(mode="json")


@router.post(
    "/inspection-resources/{resource_code}/{record_id}/sync-to-feishu",
    summary="显式推送检验记录到飞书",
)
async def sync_legacy_inspection_record_to_feishu(
    resource_code: str,
    record_id: uuid.UUID,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        return await sync_inspection_record_to_feishu(
            db,
            resource_code=resource_code,
            record_id=record_id,
        )
    except ValueError as exc:
        raise AppException(message=str(exc), status_code=400) from exc
