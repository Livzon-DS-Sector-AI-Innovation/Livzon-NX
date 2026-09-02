"""Inspection Feishu page API.

All inspection data lives in Feishu Bitable.
These endpoints read/write directly to/from configured Feishu tables.

Route mapping (frontend → backend):
  /api/v1/quality/items/*         → 物品管理
  /api/v1/quality/instruments/*    → 仪器管理
  /api/v1/quality/inspection-finished/* → 成品检验
  /api/v1/quality/inspection-solid/*    → 固体物料
  /api/v1/quality/inspection-liquid/*   → 液体物料

If Feishu is not configured, endpoints return `{"data":[],"meta":{"configured":false}}`.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException
from app.core.response import success_response
from app.modules.quality.api.deps import (
    require_user as _require_user,
)
from app.modules.quality.api.deps import (
    try_acquire_action_lock,
)
from app.modules.quality.schemas.inspection_dashboard import InspectionDashboardResponse
from app.modules.quality.service import (
    ensure_finished_entity_in_group,
    ensure_material_entity_in_group,
    get_bbas_dashboard_data,
    get_dls_dashboard_data,
    get_finished_display_fields,
    get_formulations_dashboard_data,
    get_lft_dashboard_data,
    get_lkms_dashboard_data,
    get_mpa_dashboard_data,
    get_mvt_dashboard_data,
    get_tryptophan_dashboard_data,
    get_water_dashboard_data,
    list_calibrations,
    list_equipment,
    list_finished_by_entity,
    list_finished_subtables,
    list_inbounds,
    list_instr_assets,
    list_instr_changes,
    list_instr_contracts,
    list_instr_plans,
    list_items,
    list_maintenance,
    list_material_records_by_entity,
    list_material_subtables,
    list_outbounds,
    list_repairs,
    pull_calibrations,
    pull_equipment,
    pull_finished_by_entity,
    pull_inbounds,
    pull_instr_assets,
    pull_instr_changes,
    pull_instr_contracts,
    pull_instr_plans,
    pull_items,
    pull_maintenance,
    pull_material_records_by_entity,
    pull_outbounds,
    pull_repairs,
)
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)
router = APIRouter()


def _feishu_response(result: dict[str, Any]) -> Any:
    meta = {
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
    }
    if "fields" in result:
        meta["fields"] = result["fields"]
    return success_response(
        data=result["items"],
        meta=meta,
    )


def _empty_meta(page: Any = 1, page_size: Any = 20) -> Any:
    return success_response(
        data=[],
        meta={"total": 0, "page": page, "page_size": page_size, "configured": False},
    )


def _subtables_response(items: list[dict[str, Any]], configured: bool) -> Any:
    return success_response(
        data=items,
        meta={
            "total": len(items),
            "configured": configured,
        },
    )


async def _safe_list(
    coro: Any, *args: Any, page: Any = 1, page_size: Any = 20, **kwargs: Any
) -> Any:
    try:
        return _feishu_response(
            await coro(*args, page=page, page_size=page_size, **kwargs)
        )
    except AppException as e:
        logger.info("Feishu not configured: %s", e)
        return _empty_meta(page, page_size)
    except Exception as e:
        logger.warning("Feishu error: %s", e)
        return _empty_meta(page, page_size)


async def _safe_pull(coro: Any, *args: Any, **kwargs: Any) -> Any:
    # 幂等守卫：同一数据源的 pull 未完成前不接受重复触发（防连点）
    lock_scope = (
        "pull:"
        + coro.__name__
        + "".join(f":{arg}" for arg in args[1:] if isinstance(arg, str))
    )
    if not await try_acquire_action_lock(lock_scope, timeout=300):
        return success_response(
            data={"synced": 0, "failed": 0, "error": "同步正在进行中，请勿重复操作"}
        )
    try:
        return success_response(data=await coro(*args, **kwargs))
    except AppException as e:
        logger.info("Feishu pull not configured: %s", e)
        return success_response(data={"synced": 0, "failed": 0, "error": "飞书未配置"})
    except Exception as e:
        logger.warning("Feishu pull error: %s", e)
        return success_response(data={"synced": 0, "failed": 0, "error": str(e)})


# ═══════════════════════════════════════
#  物品管理
# ═══════════════════════════════════════


def _parse_filter_params(request: Request | None) -> dict[str, str]:
    """解析 filter_* 查询参数为筛选字典."""
    filters: dict[str, str] = {}
    if request is None:
        return filters
    for key, value in request.query_params.items():
        if key.startswith("filter_") and value:
            filters[key[7:]] = value
    return filters


@router.get(
    "/items/inventory", response_model=ApiResponseEnvelope[list[dict[str, Any]]]
)
async def api_list_items(
    keyword: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    request: Request = cast(Request, None),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_list(
        list_items,
        db,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters=_parse_filter_params(request),
    )


@router.post(
    "/items/inventory/pull", response_model=ApiResponseEnvelope[dict[str, Any]]
)
async def api_pull_items(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_pull(pull_items, db)


@router.get("/items/inbound", response_model=ApiResponseEnvelope[list[dict[str, Any]]])
async def api_list_inbounds(
    keyword: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    request: Request = cast(Request, None),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_list(
        list_inbounds,
        db,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters=_parse_filter_params(request),
    )


@router.post("/items/inbound/pull", response_model=ApiResponseEnvelope[dict[str, Any]])
async def api_pull_inbounds(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_pull(pull_inbounds, db)


@router.get("/items/outbound", response_model=ApiResponseEnvelope[list[dict[str, Any]]])
async def api_list_outbounds(
    keyword: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    request: Request = cast(Request, None),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_list(
        list_outbounds,
        db,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters=_parse_filter_params(request),
    )


@router.post("/items/outbound/pull", response_model=ApiResponseEnvelope[dict[str, Any]])
async def api_pull_outbounds(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_pull(pull_outbounds, db)


# ═══════════════════════════════════════
#  仪器管理
# ═══════════════════════════════════════


@router.get(
    "/instruments/equipment", response_model=ApiResponseEnvelope[list[dict[str, Any]]]
)
async def api_list_equipment(
    keyword: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    request: Request = cast(Request, None),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_list(
        list_equipment,
        db,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters=_parse_filter_params(request),
    )


@router.post(
    "/instruments/equipment/pull", response_model=ApiResponseEnvelope[dict[str, Any]]
)
async def api_pull_equipment(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_pull(pull_equipment, db)


@router.get(
    "/instruments/maintenance", response_model=ApiResponseEnvelope[list[dict[str, Any]]]
)
async def api_list_maintenance(
    keyword: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    request: Request = cast(Request, None),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_list(
        list_maintenance,
        db,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters=_parse_filter_params(request),
    )


@router.post(
    "/instruments/maintenance/pull", response_model=ApiResponseEnvelope[dict[str, Any]]
)
async def api_pull_maintenance(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_pull(pull_maintenance, db)


@router.get(
    "/instruments/calibration", response_model=ApiResponseEnvelope[list[dict[str, Any]]]
)
async def api_list_calibrations(
    keyword: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    request: Request = cast(Request, None),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_list(
        list_calibrations,
        db,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters=_parse_filter_params(request),
    )


@router.post(
    "/instruments/calibration/pull", response_model=ApiResponseEnvelope[dict[str, Any]]
)
async def api_pull_calibrations(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_pull(pull_calibrations, db)


@router.get(
    "/instruments/repair", response_model=ApiResponseEnvelope[list[dict[str, Any]]]
)
async def api_list_repairs(
    keyword: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    request: Request = cast(Request, None),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_list(
        list_repairs,
        db,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters=_parse_filter_params(request),
    )


@router.post(
    "/instruments/repair/pull", response_model=ApiResponseEnvelope[dict[str, Any]]
)
async def api_pull_repairs(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_pull(pull_repairs, db)


@router.get(
    "/instruments/change", response_model=ApiResponseEnvelope[list[dict[str, Any]]]
)
async def api_list_instr_changes(
    keyword: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    request: Request = cast(Request, None),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_list(
        list_instr_changes,
        db,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters=_parse_filter_params(request),
    )


@router.post(
    "/instruments/change/pull", response_model=ApiResponseEnvelope[dict[str, Any]]
)
async def api_pull_instr_changes(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_pull(pull_instr_changes, db)


@router.get(
    "/instruments/contracts", response_model=ApiResponseEnvelope[list[dict[str, Any]]]
)
async def api_list_instr_contracts(
    keyword: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    request: Request = cast(Request, None),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_list(
        list_instr_contracts,
        db,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters=_parse_filter_params(request),
    )


@router.post(
    "/instruments/contracts/pull", response_model=ApiResponseEnvelope[dict[str, Any]]
)
async def api_pull_instr_contracts(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_pull(pull_instr_contracts, db)


@router.get(
    "/instruments/plans", response_model=ApiResponseEnvelope[list[dict[str, Any]]]
)
async def api_list_instr_plans(
    keyword: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    request: Request = cast(Request, None),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_list(
        list_instr_plans,
        db,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters=_parse_filter_params(request),
    )


@router.post(
    "/instruments/plans/pull", response_model=ApiResponseEnvelope[dict[str, Any]]
)
async def api_pull_instr_plans(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_pull(pull_instr_plans, db)


@router.get(
    "/instruments/assets", response_model=ApiResponseEnvelope[list[dict[str, Any]]]
)
async def api_list_instr_assets(
    keyword: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    request: Request = cast(Request, None),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_list(
        list_instr_assets,
        db,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters=_parse_filter_params(request),
    )


@router.post(
    "/instruments/assets/pull", response_model=ApiResponseEnvelope[dict[str, Any]]
)
async def api_pull_instr_assets(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_pull(pull_instr_assets, db)


# ═══════════════════════════════════════
#  成品检验（按子表拆分）
# ═══════════════════════════════════════

# ═══════════════════════════════════════
#  成品检验趋势仪表盘（统一入口）
# ═══════════════════════════════════════

# 产品分组 → 仪表盘数据服务（新增仪表盘只需在此登记）
_DASHBOARD_GROUP_FETCHERS: dict[str, Any] = {
    "mpa": get_mpa_dashboard_data,
    "mvt": get_mvt_dashboard_data,
    "lft": get_lft_dashboard_data,
    "dls": get_dls_dashboard_data,
    "lkms": get_lkms_dashboard_data,
    "bbas": get_bbas_dashboard_data,
    "tryptophan": get_tryptophan_dashboard_data,
    "water": get_water_dashboard_data,
    "formulations": get_formulations_dashboard_data,
}


@router.get(
    "/inspection-dashboard/{product_group}",
    summary="产品组趋势仪表盘（统一入口）",
    response_model=InspectionDashboardResponse,
)
async def api_get_inspection_dashboard(
    product_group: str,
    entity_code: str | None = Query(
        None, description="数据源 entity_code，不传用分组默认值"
    ),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    fetcher = _DASHBOARD_GROUP_FETCHERS.get(product_group)
    if fetcher is None:
        raise AppException(message=f"未知产品分组: {product_group}", status_code=404)
    kwargs: dict[str, Any] = {
        "sender_user_open_id": getattr(current_user, "feishu_open_id", None),
    }
    # mvt 分组只有单一数据源，不接受 entity_code
    if entity_code and product_group != "mvt":
        kwargs["source_entity_code"] = entity_code
    result = await fetcher(db, **kwargs)
    return success_response(
        data={
            "source_entity_code": result["source_entity_code"],
            "source_label": result["source_label"],
            "charts": result["charts"],
            "alerts": result["alerts"],
            "summary": result["summary"],
        },
        meta={
            "configured": result["configured"],
        },
    )


@router.get(
    "/inspection-finished/mpa/dashboard",
    summary="霉酚酸趋势仪表盘",
    response_model=InspectionDashboardResponse,
)
async def api_get_mpa_dashboard(
    entity_code: str = Query(
        "qc_finished_internal", description="霉酚酸仪表盘数据源 entity_code"
    ),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    result = await get_mpa_dashboard_data(
        db,
        source_entity_code=entity_code,
        sender_user_open_id=getattr(current_user, "feishu_open_id", None),
    )
    return success_response(
        data={
            "source_entity_code": result["source_entity_code"],
            "source_label": result["source_label"],
            "charts": result["charts"],
            "alerts": result["alerts"],
            "summary": result["summary"],
        },
        meta={
            "configured": result["configured"],
        },
    )


@router.get(
    "/inspection-finished/mvt/dashboard",
    summary="美伐他汀趋势仪表盘",
    response_model=InspectionDashboardResponse,
)
async def api_get_mvt_dashboard(
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    result = await get_mvt_dashboard_data(
        db,
        sender_user_open_id=getattr(current_user, "feishu_open_id", None),
    )
    return success_response(
        data={
            "source_entity_code": result["source_entity_code"],
            "source_label": result["source_label"],
            "charts": result["charts"],
            "alerts": result["alerts"],
            "summary": result["summary"],
        },
        meta={
            "configured": result["configured"],
        },
    )


@router.get(
    "/inspection-finished/lft/dashboard",
    summary="洛伐他汀趋势仪表盘",
    response_model=InspectionDashboardResponse,
)
async def api_get_lft_dashboard(
    entity_code: str = Query(
        "qc_finished_lft_ep", description="洛伐他汀仪表盘数据源 entity_code"
    ),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    result = await get_lft_dashboard_data(
        db,
        source_entity_code=entity_code,
        sender_user_open_id=getattr(current_user, "feishu_open_id", None),
    )
    return success_response(
        data={
            "source_entity_code": result["source_entity_code"],
            "source_label": result["source_label"],
            "charts": result["charts"],
            "alerts": result["alerts"],
            "summary": result["summary"],
        },
        meta={
            "configured": result["configured"],
        },
    )


@router.get(
    "/inspection-finished/dls/dashboard",
    summary="多拉菌素趋势仪表盘",
    response_model=InspectionDashboardResponse,
)
async def api_get_dls_dashboard(
    entity_code: str = Query(
        "qc_finished_dor_gb", description="多拉菌素仪表盘数据源 entity_code"
    ),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    result = await get_dls_dashboard_data(
        db,
        source_entity_code=entity_code,
        sender_user_open_id=getattr(current_user, "feishu_open_id", None),
    )
    return success_response(
        data={
            "source_entity_code": result["source_entity_code"],
            "source_label": result["source_label"],
            "charts": result["charts"],
            "alerts": result["alerts"],
            "summary": result["summary"],
        },
        meta={
            "configured": result["configured"],
        },
    )


@router.get(
    "/inspection-finished/lkms/dashboard",
    summary="林可霉素趋势仪表盘",
    response_model=InspectionDashboardResponse,
)
async def api_get_lkms_dashboard(
    entity_code: str = Query(
        "qc_finished_lkms_vet", description="林可霉素仪表盘数据源 entity_code"
    ),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    result = await get_lkms_dashboard_data(
        db,
        source_entity_code=entity_code,
        sender_user_open_id=getattr(current_user, "feishu_open_id", None),
    )
    return success_response(
        data={
            "source_entity_code": result["source_entity_code"],
            "source_label": result["source_label"],
            "charts": result["charts"],
            "alerts": result["alerts"],
            "summary": result["summary"],
        },
        meta={
            "configured": result["configured"],
        },
    )


@router.get(
    "/inspection-finished/bbas/dashboard",
    summary="L-苯丙氨酸趋势仪表盘",
    response_model=InspectionDashboardResponse,
)
async def api_get_bbas_dashboard(
    entity_code: str = Query(
        "qc_finished_fcc14", description="苯丙氨酸仪表盘数据源 entity_code"
    ),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    result = await get_bbas_dashboard_data(
        db,
        source_entity_code=entity_code,
        sender_user_open_id=getattr(current_user, "feishu_open_id", None),
    )
    return success_response(
        data={
            "source_entity_code": result["source_entity_code"],
            "source_label": result["source_label"],
            "charts": result["charts"],
            "alerts": result["alerts"],
            "summary": result["summary"],
        },
        meta={
            "configured": result["configured"],
        },
    )


@router.get(
    "/inspection-finished/tryptophan/dashboard",
    summary="色氨酸趋势仪表盘",
    response_model=InspectionDashboardResponse,
)
async def api_get_tryptophan_dashboard(
    entity_code: str = Query(
        "qc_finished_trp_granule", description="色氨酸仪表盘数据源 entity_code"
    ),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    result = await get_tryptophan_dashboard_data(
        db,
        source_entity_code=entity_code,
        sender_user_open_id=getattr(current_user, "feishu_open_id", None),
    )
    return success_response(
        data={
            "source_entity_code": result["source_entity_code"],
            "source_label": result["source_label"],
            "charts": result["charts"],
            "alerts": result["alerts"],
            "summary": result["summary"],
        },
        meta={
            "configured": result["configured"],
        },
    )


@router.get(
    "/inspection-finished/water/dashboard",
    summary="纯化水趋势仪表盘",
    response_model=InspectionDashboardResponse,
)
async def api_get_water_dashboard(
    entity_code: str = Query(
        "qc_finished_pure_water", description="纯化水仪表盘数据源 entity_code"
    ),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    result = await get_water_dashboard_data(
        db,
        source_entity_code=entity_code,
        sender_user_open_id=getattr(current_user, "feishu_open_id", None),
    )
    return success_response(
        data={
            "source_entity_code": result["source_entity_code"],
            "source_label": result["source_label"],
            "charts": result["charts"],
            "alerts": result["alerts"],
            "summary": result["summary"],
        },
        meta={
            "configured": result["configured"],
        },
    )


@router.get(
    "/inspection-finished/formulations/dashboard",
    summary="制剂趋势仪表盘",
    response_model=InspectionDashboardResponse,
)
async def api_get_formulations_dashboard(
    entity_code: str = Query(
        "qc_finished_flu_powder", description="预混剂仪表盘数据源 entity_code"
    ),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    result = await get_formulations_dashboard_data(
        db,
        source_entity_code=entity_code,
        sender_user_open_id=getattr(current_user, "feishu_open_id", None),
    )
    return success_response(
        data={
            "source_entity_code": result["source_entity_code"],
            "source_label": result["source_label"],
            "charts": result["charts"],
            "alerts": result["alerts"],
            "summary": result["summary"],
        },
        meta={
            "configured": result["configured"],
        },
    )


@router.get(
    "/inspection-finished/{product_group}/subtables",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_list_finished_subtables(
    product_group: str,
    current_user: CurrentUser = None,  # optional_user
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await list_finished_subtables(db, product_group)
    except KeyError:
        raise AppException(message=f"未知产品分组: {product_group}", status_code=404)
    return _subtables_response(result["items"], result["configured"])


@router.get(
    "/inspection-finished/{product_group}/records",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_list_finished_records(
    product_group: str,
    entity_code: str = Query(..., description="飞书真实子表 entity_code"),
    keyword: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: CurrentUser = None,  # optional_user
    db: AsyncSession = Depends(get_db),
    request: Request = cast(Request, None),
) -> Any:
    try:
        ensure_finished_entity_in_group(product_group, entity_code)
    except KeyError:
        raise AppException(message=f"未知产品分组: {product_group}", status_code=404)
    try:
        result = await list_finished_by_entity(
            db,
            entity_code,
            keyword=keyword,
            page=page,
            page_size=page_size,
            filters=_parse_filter_params(request),
        )
    except AppException as e:
        logger.info("Feishu not configured: %s", e)
        return _empty_meta(page, page_size)
    except Exception as e:
        logger.warning("Feishu error: %s", e)
        return _empty_meta(page, page_size)
    response_meta = {
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
    }
    field_names = result.get("fields") or []
    if field_names:
        response_meta["fields"] = field_names
    response_meta["display_fields"] = get_finished_display_fields(
        entity_code, field_names
    )
    return success_response(data=result["items"], meta=response_meta)


@router.post(
    "/inspection-finished/{product_group}/pull",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_pull_finished(
    product_group: str,
    entity_code: str = Query(..., description="飞书真实子表 entity_code"),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        ensure_finished_entity_in_group(product_group, entity_code)
    except KeyError:
        raise AppException(message=f"未知产品分组: {product_group}", status_code=404)
    return await _safe_pull(pull_finished_by_entity, db, entity_code)


# ═══════════════════════════════════════
#  固体/液体物料检验（编号段分组）
# ═══════════════════════════════════════


@router.get(
    "/inspection-solid/{group}/subtables",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_list_solid_subtables(
    group: str,
    current_user: CurrentUser = None,  # optional_user
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await list_material_subtables(db, "solid", group)
    except KeyError:
        raise AppException(message=f"未知固体物料分组: {group}", status_code=404)
    return _subtables_response(result["items"], result["configured"])


@router.get(
    "/inspection-solid/{group}/records",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_list_solid_records(
    group: str,
    entity_code: str = Query(..., description="飞书真实子表 entity_code"),
    keyword: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: CurrentUser = None,  # optional_user
    db: AsyncSession = Depends(get_db),
    request: Request = cast(Request, None),
) -> Any:
    try:
        ensure_material_entity_in_group("solid", group, entity_code)
    except KeyError:
        raise AppException(message=f"未知固体物料分组: {group}", status_code=404)
    return await _safe_list(
        list_material_records_by_entity,
        db,
        entity_code,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters=_parse_filter_params(request),
    )


@router.post(
    "/inspection-solid/{group}/pull", response_model=ApiResponseEnvelope[dict[str, Any]]
)
async def api_pull_solid_records(
    group: str,
    entity_code: str = Query(..., description="飞书真实子表 entity_code"),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        ensure_material_entity_in_group("solid", group, entity_code)
    except KeyError:
        raise AppException(message=f"未知固体物料分组: {group}", status_code=404)
    return await _safe_pull(pull_material_records_by_entity, db, entity_code)


@router.get(
    "/inspection-liquid/{group}/subtables",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_list_liquid_subtables(
    group: str,
    current_user: CurrentUser = None,  # optional_user
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await list_material_subtables(db, "liquid", group)
    except KeyError:
        raise AppException(message=f"未知液体物料分组: {group}", status_code=404)
    return _subtables_response(result["items"], result["configured"])


@router.get(
    "/inspection-liquid/{group}/records",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_list_liquid_records(
    group: str,
    entity_code: str = Query(..., description="飞书真实子表 entity_code"),
    keyword: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: CurrentUser = None,  # optional_user
    db: AsyncSession = Depends(get_db),
    request: Request = cast(Request, None),
) -> Any:
    try:
        ensure_material_entity_in_group("liquid", group, entity_code)
    except KeyError:
        raise AppException(message=f"未知液体物料分组: {group}", status_code=404)
    return await _safe_list(
        list_material_records_by_entity,
        db,
        entity_code,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters=_parse_filter_params(request),
    )


@router.post(
    "/inspection-liquid/{group}/pull",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_pull_liquid_records(
    group: str,
    entity_code: str = Query(..., description="飞书真实子表 entity_code"),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        ensure_material_entity_in_group("liquid", group, entity_code)
    except KeyError:
        raise AppException(message=f"未知液体物料分组: {group}", status_code=404)
    return await _safe_pull(pull_material_records_by_entity, db, entity_code)
