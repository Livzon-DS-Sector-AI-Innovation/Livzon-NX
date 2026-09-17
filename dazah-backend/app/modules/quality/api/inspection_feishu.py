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

import io
import logging
from typing import Any, cast
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException
from app.core.response import success_response
from app.core.upload_security import read_upload_secure
from app.modules.quality.api.deps import (
    QUALITY_QA_SCOPE_PERMISSIONS,
    try_acquire_action_lock,
)
from app.modules.quality.api.deps import (
    assert_quality_edit_scope as _assert_quality_edit_scope,
)
from app.modules.quality.api.deps import (
    require_user as _require_user,
)
from app.modules.quality.schemas.inspection_dashboard import (
    InspectionDashboardResponse,
    TrendAIReanalyzeRequest,
)
from app.modules.quality.schemas.instrument_certificate import (
    CertificateRematchRequest,
    InstrumentCertificateAnalyzeResult,
)
from app.modules.quality.service import (
    ensure_finished_entity_in_group,
    ensure_material_entity_in_group,
    get_bbas_dashboard_data,
    get_dls_dashboard_data,
    get_finished_display_fields,
    get_formulations_dashboard_data,
    get_instruments_dashboard,
    get_lft_dashboard_data,
    get_lkms_dashboard_data,
    get_mpa_dashboard_data,
    get_mvt_dashboard_data,
    get_tryptophan_dashboard_data,
    get_water_dashboard_data,
    list_all_materials,
    list_finished_by_entity,
    list_finished_subtables,
    list_inbounds,
    list_instrument_mirror,
    list_items,
    list_material_records_by_entity,
    list_material_subtables,
    list_outbounds,
    pull_finished_by_entity,
    pull_material_records_by_entity,
    sync_instrument_page,
)
from app.modules.quality.service.inspection_dashboard_calc import reanalyze_trend_ai
from app.modules.quality.service.inspection_helpers import (
    _list_feishu_dynamic,
    resolve_month_range_ms,
)
from app.modules.quality.service.inspection_items_mirror import (
    PAGE_INBOUND,
    PAGE_INVENTORY,
    PAGE_OUTBOUND,
    list_distinct_column_values,
    list_items_mirror,
    sync_items_page,
)
from app.modules.quality.service.instrument_certificate_analyze import (
    CERTIFICATE_ALLOWED_EXTENSIONS,
    CERTIFICATE_MAX_BYTES,
    analyze_calibration_certificate,
    rematch_certificate_fields,
)
from app.modules.quality.service.instrument_import import (
    confirm_instrument_import,
    preview_instrument_import,
)
from app.modules.quality.service.instrument_profile import get_instrument_profile
from app.modules.quality.service.items_dashboard import (
    get_items_dashboard,
    push_low_stock_alert,
)
from app.modules.quality.service.maintenance_export import (
    export_maintenance_summary,
)
from app.modules.quality.service.maintenance_schedule import (
    enrich_maintenance_schedule,
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


def _mirror_response(result: dict[str, Any]) -> Any:
    """镜像页列表响应信封（source=local_mirror，前端据此展示最近同步时间）。"""
    meta = {
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "fields": result.get("fields", []),
        "fieldMeta": result.get("fieldMeta", {}),
        "configured": result.get("configured", True),
        "last_sync_time": result.get("last_sync_time"),
        "source": "local_mirror",
    }
    return success_response(data=result["items"], meta=meta)


async def _items_page_list(
    db: AsyncSession,
    page_key: str,
    *,
    live_coro: Any,
    keyword: str | None,
    filters: dict[str, str],
    page: int,
    page_size: int,
    force: bool,
    incremental: bool,
) -> Any:
    """物品页列表：镜像优先，可选触发同步；空镜像/未镜像降级实时读。"""
    return await _mirror_page_list(
        db,
        page_key,
        list_mirror=list_items_mirror,
        sync_page=sync_items_page,
        live_coro=live_coro,
        keyword=keyword,
        filters=filters,
        page=page,
        page_size=page_size,
        force=force,
        incremental=incremental,
    )


async def _mirror_page_list(
    db: AsyncSession,
    entity_code: str,
    *,
    list_mirror: Any,
    sync_page: Any,
    live_coro: Any,
    keyword: str | None,
    filters: dict[str, str],
    page: int,
    page_size: int,
    force: bool,
    incremental: bool,
    enrich: Any = None,
    month: str | None = None,
    month_field: str = "生成日期",
) -> Any:
    """镜像页通用列表：镜像优先，可选触发同步；空镜像/未镜像降级实时读。

    force=True 强制全量同步后再读；incremental=True 走增量同步。
    未同步（无快照）时降级实时读，保证首次进入不空屏。
    month 传入时列表按 month_field 落月过滤（镜像 SQL 与实时兜底同口径）；
    只传给支持该参数的 list_mirror/live_coro 调用（当前仅仪器镜像）。
    """
    if force or incremental:
        try:
            await sync_page(db, entity_code, incremental=incremental and not force)
        except AppException as exc:
            logger.info("mirror sync skipped (%s): %s", entity_code, exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("mirror sync failed (%s): %s", entity_code, exc)

    month_kwargs: dict[str, Any] = (
        {"month": month, "month_field": month_field} if month else {}
    )
    mirror = await list_mirror(
        db,
        entity_code,
        keyword=keyword,
        filters=filters,
        page=page,
        page_size=page_size,
        **month_kwargs,
    )
    if enrich is not None and mirror.get("configured"):
        mirror["items"] = await enrich(db, mirror["items"])
    # 未同步且未强制刷新 → 降级实时读，保证首次进入不空屏
    if not force and not mirror["configured"]:
        return await _safe_list(
            live_coro,
            db,
            entity_code,
            keyword=keyword,
            page=page,
            page_size=page_size,
            filters=filters,
            **month_kwargs,
        )
    empty_unfiltered = (
        mirror["configured"] and mirror["total"] == 0 and not keyword and not filters
    )
    if not force and empty_unfiltered:
        # 镜像为空可能是尚未首跑：降级实时读探测一次
        live_probe = await _safe_list(
            live_coro,
            db,
            entity_code,
            keyword=keyword,
            page=1,
            page_size=1,
            filters=filters,
            **month_kwargs,
        )
        if _response_has_data(live_probe):
            return live_probe
    return _mirror_response(mirror)


def _response_has_data(envelope: Any) -> bool:
    meta = getattr(envelope, "meta", None) or {}
    return bool(meta.get("total") if isinstance(meta, dict) else 0)


@router.get(
    "/items/inventory", response_model=ApiResponseEnvelope[list[dict[str, Any]]]
)
async def api_list_items(
    keyword: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    force: bool = Query(False),
    incremental: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    request: Request = cast(Request, None),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _items_page_list(
        db,
        PAGE_INVENTORY,
        live_coro=list_items,
        keyword=keyword,
        filters=_parse_filter_params(request),
        page=page,
        page_size=page_size,
        force=force,
        incremental=incremental,
    )


@router.post(
    "/items/inventory/pull", response_model=ApiResponseEnvelope[dict[str, Any]]
)
async def api_pull_items(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_pull_sync_page(PAGE_INVENTORY, db)


@router.get("/items/inbound", response_model=ApiResponseEnvelope[list[dict[str, Any]]])
async def api_list_inbounds(
    keyword: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    force: bool = Query(False),
    incremental: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    request: Request = cast(Request, None),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _items_page_list(
        db,
        PAGE_INBOUND,
        live_coro=list_inbounds,
        keyword=keyword,
        filters=_parse_filter_params(request),
        page=page,
        page_size=page_size,
        force=force,
        incremental=incremental,
    )


@router.post("/items/inbound/pull", response_model=ApiResponseEnvelope[dict[str, Any]])
async def api_pull_inbounds(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_pull_sync_page(PAGE_INBOUND, db)


@router.get("/items/outbound", response_model=ApiResponseEnvelope[list[dict[str, Any]]])
async def api_list_outbounds(
    keyword: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    force: bool = Query(False),
    incremental: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    request: Request = cast(Request, None),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _items_page_list(
        db,
        PAGE_OUTBOUND,
        live_coro=list_outbounds,
        keyword=keyword,
        filters=_parse_filter_params(request),
        page=page,
        page_size=page_size,
        force=force,
        incremental=incremental,
    )


@router.post("/items/outbound/pull", response_model=ApiResponseEnvelope[dict[str, Any]])
async def api_pull_outbounds(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_pull_sync_page(PAGE_OUTBOUND, db)


async def _safe_pull_sync_page(page_key: str, db: AsyncSession) -> Any:
    """手动全量同步物品页到镜像（幂等锁防连点）。"""
    if not await try_acquire_action_lock(f"pull:items_mirror:{page_key}", timeout=300):
        return success_response(
            data={"synced": 0, "failed": 0, "error": "同步正在进行中，请勿重复操作"}
        )
    try:
        result = await sync_items_page(db, page_key, incremental=False)
        return success_response(
            data={"synced": result["synced"], "failed": result.get("failed", 0)}
        )
    except AppException as exc:
        logger.info("items pull not configured (%s): %s", page_key, exc)
        return success_response(data={"synced": 0, "failed": 0, "error": "飞书未配置"})
    except Exception as exc:  # noqa: BLE001
        logger.warning("items pull error (%s): %s", page_key, exc)
        return success_response(data={"synced": 0, "failed": 0, "error": str(exc)})


# ── 物品管理仪表盘 / 库存不足推送 ──


@router.get("/items/dashboard", response_model=ApiResponseEnvelope[dict[str, Any]])
async def api_items_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    result = await get_items_dashboard(db)
    return success_response(data=result.model_dump(mode="json"))


@router.get(
    "/items/inventory/filter-options",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_items_inventory_filter_options(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    """库存台账动态筛选项（存放位置 / 库存报警去重值），供筛选/分类按钮使用。"""
    _require_user(current_user)
    locations = await list_distinct_column_values(db, PAGE_INVENTORY, "存放位置")
    alarms = await list_distinct_column_values(db, PAGE_INVENTORY, "库存报警")
    return success_response(data={"存放位置": locations, "库存报警": alarms})


@router.post(
    "/items/dashboard/push-low-stock",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_push_low_stock(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    user_id = _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["qc"],
    )
    result = await push_low_stock_alert(db)
    logger.info("items low-stock push by user=%s", str(user_id))
    return success_response(data=result.model_dump(mode="json"))


@router.post(
    "/items/dashboard/push-low-stock/test",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_push_low_stock_test(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["qc"],
    )
    result = await push_low_stock_alert(db, test=True)
    return success_response(data=result.model_dump(mode="json"))


# ═══════════════════════════════════════
#  仪器管理（本地镜像优先，8 张飞书子表 / 两个 Base）
# ═══════════════════════════════════════


async def _instrument_page_list(
    db: AsyncSession,
    entity_code: str,
    *,
    keyword: str | None,
    filters: dict[str, str],
    page: int,
    page_size: int,
    force: bool,
    incremental: bool,
    enrich: Any = None,
    month: str | None = None,
) -> Any:
    """仪器子表列表：本地镜像优先，未同步时降级实时读（列跟随飞书真实字段）。"""
    return await _mirror_page_list(
        db,
        entity_code,
        list_mirror=list_instrument_mirror,
        sync_page=sync_instrument_page,
        live_coro=_list_feishu_dynamic,
        keyword=keyword,
        filters=filters,
        page=page,
        page_size=page_size,
        force=force,
        incremental=incremental,
        enrich=enrich,
        month=month,
    )


async def _safe_pull_mirror(sync_page: Any, entity_code: str, db: AsyncSession) -> Any:
    """手动全量同步镜像页（幂等锁防连点）。"""
    if not await try_acquire_action_lock(f"pull:mirror:{entity_code}", timeout=300):
        return success_response(
            data={"synced": 0, "failed": 0, "error": "同步正在进行中，请勿重复操作"}
        )
    try:
        result = await sync_page(db, entity_code, incremental=False)
        return success_response(
            data={
                "synced": result.get("synced", 0),
                "failed": result.get("failed", 0),
            }
        )
    except AppException as exc:
        logger.info("mirror pull not configured (%s): %s", entity_code, exc)
        return success_response(data={"synced": 0, "failed": 0, "error": "飞书未配置"})
    except Exception as exc:  # noqa: BLE001
        logger.warning("mirror pull error (%s): %s", entity_code, exc)
        return success_response(data={"synced": 0, "failed": 0, "error": str(exc)})


@router.get(
    "/instruments/equipment", response_model=ApiResponseEnvelope[list[dict[str, Any]]]
)
async def api_list_equipment(
    keyword: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    force: bool = Query(False),
    incremental: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    request: Request = cast(Request, None),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _instrument_page_list(
        db,
        "qc_instr_equipment",
        keyword=keyword,
        filters=_parse_filter_params(request),
        page=page,
        page_size=page_size,
        force=force,
        incremental=incremental,
    )


@router.post(
    "/instruments/equipment/pull", response_model=ApiResponseEnvelope[dict[str, Any]]
)
async def api_pull_equipment(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_pull_mirror(sync_instrument_page, "qc_instr_equipment", db)


@router.get(
    "/instruments/maintenance", response_model=ApiResponseEnvelope[list[dict[str, Any]]]
)
async def api_list_maintenance(
    keyword: str = Query(None),
    month: str = Query(None, description="按生成日期过滤月份 YYYY-MM；不传=全部"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    force: bool = Query(False),
    incremental: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    request: Request = cast(Request, None),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    if month:
        resolve_month_range_ms(month)  # 格式非法直接 400
    return await _instrument_page_list(
        db,
        "qc_instr_maintenance",
        keyword=keyword,
        filters=_parse_filter_params(request),
        page=page,
        page_size=page_size,
        force=force,
        incremental=incremental,
        enrich=enrich_maintenance_schedule,
        month=month or None,
    )


@router.post(
    "/instruments/maintenance/pull", response_model=ApiResponseEnvelope[dict[str, Any]]
)
async def api_pull_maintenance(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_pull_mirror(sync_instrument_page, "qc_instr_maintenance", db)


@router.get("/instruments/maintenance/export", summary="按月导出维保汇总表 xlsx")
async def api_export_maintenance_summary(
    month: str = Query(..., description="月份 YYYY-MM，如 2026-07"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    """设备年度预防性维护保养汇总表（复刻用户模板格式，维护日期为 YYYY.MM.DD 文本）。"""
    _require_user(current_user)
    content, filename = await export_maintenance_summary(db, month)
    encoded = quote(filename, safe="")
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=utf-8''{encoded}"},
    )


@router.get(
    "/instruments/calibration", response_model=ApiResponseEnvelope[list[dict[str, Any]]]
)
async def api_list_calibrations(
    keyword: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    force: bool = Query(False),
    incremental: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    request: Request = cast(Request, None),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _instrument_page_list(
        db,
        "qc_instr_calibration",
        keyword=keyword,
        filters=_parse_filter_params(request),
        page=page,
        page_size=page_size,
        force=force,
        incremental=incremental,
    )


@router.post(
    "/instruments/calibration/pull", response_model=ApiResponseEnvelope[dict[str, Any]]
)
async def api_pull_calibrations(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_pull_mirror(sync_instrument_page, "qc_instr_calibration", db)


@router.get(
    "/instruments/repair", response_model=ApiResponseEnvelope[list[dict[str, Any]]]
)
async def api_list_repairs(
    keyword: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    force: bool = Query(False),
    incremental: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    request: Request = cast(Request, None),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _instrument_page_list(
        db,
        "qc_instr_repair",
        keyword=keyword,
        filters=_parse_filter_params(request),
        page=page,
        page_size=page_size,
        force=force,
        incremental=incremental,
    )


@router.post(
    "/instruments/repair/pull", response_model=ApiResponseEnvelope[dict[str, Any]]
)
async def api_pull_repairs(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_pull_mirror(sync_instrument_page, "qc_instr_repair", db)


@router.get(
    "/instruments/contracts", response_model=ApiResponseEnvelope[list[dict[str, Any]]]
)
async def api_list_instr_contracts(
    keyword: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    force: bool = Query(False),
    incremental: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    request: Request = cast(Request, None),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _instrument_page_list(
        db,
        "qc_instr_contracts",
        keyword=keyword,
        filters=_parse_filter_params(request),
        page=page,
        page_size=page_size,
        force=force,
        incremental=incremental,
    )


@router.post(
    "/instruments/contracts/pull", response_model=ApiResponseEnvelope[dict[str, Any]]
)
async def api_pull_instr_contracts(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_pull_mirror(sync_instrument_page, "qc_instr_contracts", db)


@router.get(
    "/instruments/plans", response_model=ApiResponseEnvelope[list[dict[str, Any]]]
)
async def api_list_instr_plans(
    keyword: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    force: bool = Query(False),
    incremental: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    request: Request = cast(Request, None),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _instrument_page_list(
        db,
        "qc_instr_plans",
        keyword=keyword,
        filters=_parse_filter_params(request),
        page=page,
        page_size=page_size,
        force=force,
        incremental=incremental,
    )


@router.post(
    "/instruments/plans/pull", response_model=ApiResponseEnvelope[dict[str, Any]]
)
async def api_pull_instr_plans(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_pull_mirror(sync_instrument_page, "qc_instr_plans", db)


@router.get(
    "/instruments/cal-plan", response_model=ApiResponseEnvelope[list[dict[str, Any]]]
)
async def api_list_instr_cal_plans(
    keyword: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    force: bool = Query(False),
    incremental: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    request: Request = cast(Request, None),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _instrument_page_list(
        db,
        "qc_instr_cal_plan",
        keyword=keyword,
        filters=_parse_filter_params(request),
        page=page,
        page_size=page_size,
        force=force,
        incremental=incremental,
    )


@router.post(
    "/instruments/cal-plan/pull", response_model=ApiResponseEnvelope[dict[str, Any]]
)
async def api_pull_instr_cal_plans(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_pull_mirror(sync_instrument_page, "qc_instr_cal_plan", db)


@router.get(
    "/instruments/cal-external",
    response_model=ApiResponseEnvelope[list[dict[str, Any]]],
)
async def api_list_instr_cal_external(
    keyword: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    force: bool = Query(False),
    incremental: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    request: Request = cast(Request, None),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _instrument_page_list(
        db,
        "qc_instr_cal_external",
        keyword=keyword,
        filters=_parse_filter_params(request),
        page=page,
        page_size=page_size,
        force=force,
        incremental=incremental,
    )


@router.post(
    "/instruments/cal-external/pull", response_model=ApiResponseEnvelope[dict[str, Any]]
)
async def api_pull_instr_cal_external(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    return await _safe_pull_mirror(sync_instrument_page, "qc_instr_cal_external", db)


@router.post(
    "/instruments/cal-external/certificate-analyze",
    response_model=ApiResponseEnvelope[InstrumentCertificateAnalyzeResult],
)
async def api_analyze_instrument_certificate(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    """上传校准证书 → AI 识别 → 实时反查 QC 设备目录，返回外部校准表预填字段。

    只做识别与预填，不写飞书记录；记录由前端人工确认后走通用新增接口提交。
    """
    user_id = _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["qc"],
    )
    filename, content = await read_upload_secure(
        file,
        max_bytes=CERTIFICATE_MAX_BYTES,
        allowed_extensions=CERTIFICATE_ALLOWED_EXTENSIONS,
        what="校准证书文件",
    )
    result = await analyze_calibration_certificate(
        db,
        file_name=filename,
        content=content,
        content_type=file.content_type or "",
    )
    logger.info(
        "instrument certificate analyzed by user=%s file=%s", str(user_id), filename
    )
    return success_response(data=result)


@router.post(
    "/instruments/cal-external/certificate-rematch",
    response_model=ApiResponseEnvelope[InstrumentCertificateAnalyzeResult],
)
async def api_rematch_instrument_certificate(
    payload: CertificateRematchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    """人工修正识别字段后重新反查 QC 设备目录（填入表单前的修正闭环）。

    按修正后的出厂编号重新匹配目录、重算下次检定日期、刷新序号；
    证书附件复用首次识别上传的 token，不重复上传。
    """
    _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["qc"],
    )
    result = await rematch_certificate_fields(db, request=payload)
    return success_response(data=result)


# ── 仪器管理仪表盘 / 仪器档案 / 仪器台账批量导入 ──


@router.get(
    "/instruments/dashboard", response_model=ApiResponseEnvelope[dict[str, Any]]
)
async def api_get_instruments_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    """仪器管理仪表盘：概览/校验到期/维保/合同（读本地镜像聚合）。"""
    _require_user(current_user)
    result = await get_instruments_dashboard(db)
    return success_response(data=result)


@router.get(
    "/instruments/equipment/{record_id}/profile",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_get_instrument_profile(
    record_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    """仪器档案：按设备编号匹配维护/维修/校验/合同情况。"""
    _require_user(current_user)
    result = await get_instrument_profile(db, record_id)
    return success_response(data=result)


_IMPORT_MAX_BYTES = 10 * 1024 * 1024


@router.post(
    "/instruments/equipment/import/preview",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_preview_instrument_import(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    """仪器台账批量导入预览：解析 xlsx、识别列头、判新增/更新（不写数据）。"""
    user_id = _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["qc"],
    )
    _filename, content = await read_upload_secure(
        file,
        max_bytes=_IMPORT_MAX_BYTES,
        allowed_extensions={".xlsx"},
        what="仪器台账导入文件",
    )
    logger.info("instrument import preview by user=%s", str(user_id))
    return success_response(data=await preview_instrument_import(db, content))


@router.post(
    "/instruments/equipment/import/confirm",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_confirm_instrument_import(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    """仪器台账批量导入确认：按设备编号新增/更新写飞书并刷镜像。"""
    user_id = _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["qc"],
    )
    _filename, content = await read_upload_secure(
        file,
        max_bytes=_IMPORT_MAX_BYTES,
        allowed_extensions={".xlsx"},
        what="仪器台账导入文件",
    )
    result = await confirm_instrument_import(db, content, operator_user_id=user_id)
    logger.info(
        "instrument import confirmed by user=%s created=%s updated=%s failed=%s",
        str(user_id),
        result.get("created"),
        result.get("updated"),
        result.get("failed"),
    )
    return success_response(data=result, message="导入完成")


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
        "frontend_group": product_group,
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


@router.post(
    "/inspection-dashboard/trend-ai/reanalyze",
    summary="手动再次分析当月趋势 AI（页面刷新不会触发）",
)
async def api_reanalyze_trend_ai(
    request: TrendAIReanalyzeRequest,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    result = await reanalyze_trend_ai(
        db,
        entity_code=request.entity_code,
        metric_key=request.metric_key,
        sender_user_open_id=getattr(current_user, "feishu_open_id", None),
    )
    return success_response(data=result)


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
        # 恢复精简展示列裁剪：批号/批量/规格/检测项目(≤5，优先仪表盘指标)，
        # 其余列通过前端「详情」查看
        response_meta["display_fields"] = get_finished_display_fields(
            entity_code, field_names
        )
    if "configured" in result:
        # 镜像路径：附带同步状态
        response_meta["configured"] = result["configured"]
        response_meta["last_sync_time"] = result.get("last_sync_time")
        response_meta["source"] = "local_mirror"
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
    "/inspection/materials",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_list_all_materials(
    current_user: CurrentUser = None,  # optional_user
) -> Any:
    """全部固体+液体原辅料（代码+名称 label、模块与分组），供新增检验选料。"""
    items = list_all_materials()
    return success_response(
        data=items,
        meta={
            "total": len(items),
            "configured": True,
        },
    )


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
