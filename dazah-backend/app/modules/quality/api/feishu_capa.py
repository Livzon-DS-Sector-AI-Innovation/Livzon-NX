"""Feishu native CAPA plan track API endpoints - direct bitable CRUD.

CAPA 台账已本地化，不再提供飞书原生台账路由；此处仅保留 CAPA 计划跟踪。
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException
from app.core.response import paginated_response, success_response
from app.modules.quality.api.deps import require_user as _require_user
from app.modules.quality.schemas.feishu_capa import (
    FeishuCapaPlanTrackCreateRequest,
    FeishuCapaPlanTrackUpdateRequest,
)
from app.modules.quality.service.feishu_capa import (
    create_capa_plan_track_record,
    delete_capa_plan_track_record,
    get_capa_plan_track_record,
    list_capa_plan_tracks,
    update_capa_plan_track_record,
)
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feishu")


# ══════════════════════════════════════════════
#  CAPA 计划跟踪
# ══════════════════════════════════════════════


@router.get(
    "/capa-plan-tracks",
    summary="获取飞书CAPA计划跟踪列表",
    response_model=ApiResponseEnvelope[list[dict[str, Any]]],
)
async def api_list_capa_plan_tracks(
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """获取飞书CAPA计划跟踪列表，支持关键词检索与分页。"""
    _require_user(current_user)
    try:
        result = await list_capa_plan_tracks(
            db, keyword=keyword, page=page, page_size=page_size
        )
        return paginated_response(
            data=result["items"],
            page=result["page"],
            page_size=result["page_size"],
            total=result["total"],
        )
    except AppException:
        raise
    except Exception as e:
        logger.exception("Failed to list CAPA plan tracks")
        raise AppException(status_code=500, message="服务暂时不可用，请稍后重试") from e


@router.get(
    "/capa-plan-tracks/{record_id}",
    summary="获取飞书CAPA计划跟踪详情",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_get_capa_plan_track_record(
    record_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """根据记录 ID 获取单条飞书CAPA计划跟踪详情。"""
    _require_user(current_user)
    try:
        result = await get_capa_plan_track_record(db, record_id)
        return success_response(data=result)
    except AppException:
        raise
    except Exception as e:
        logger.exception("Failed to get CAPA plan track record")
        raise AppException(status_code=500, message="服务暂时不可用，请稍后重试") from e


@router.post(
    "/capa-plan-tracks",
    summary="创建飞书CAPA计划跟踪记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_create_capa_plan_track_record(
    data: FeishuCapaPlanTrackCreateRequest,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """在飞书CAPA计划跟踪表中创建一条新记录。"""
    _require_user(current_user)
    try:
        result = await create_capa_plan_track_record(
            db, data.model_dump(exclude_none=True)
        )
        return success_response(data=result, message="创建成功")
    except AppException:
        raise
    except Exception as e:
        logger.exception("Failed to create CAPA plan track record")
        raise AppException(status_code=500, message="服务暂时不可用，请稍后重试") from e


@router.put(
    "/capa-plan-tracks/{record_id}",
    summary="更新飞书CAPA计划跟踪记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_update_capa_plan_track_record(
    record_id: str,
    data: FeishuCapaPlanTrackUpdateRequest,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """根据记录 ID 更新飞书CAPA计划跟踪字段。"""
    _require_user(current_user)
    try:
        result = await update_capa_plan_track_record(
            db, record_id, data.model_dump(exclude_none=True)
        )
        return success_response(data=result, message="更新成功")
    except AppException:
        raise
    except Exception as e:
        logger.exception("Failed to update CAPA plan track record")
        raise AppException(status_code=500, message="服务暂时不可用，请稍后重试") from e


@router.delete(
    "/capa-plan-tracks/{record_id}",
    summary="删除飞书CAPA计划跟踪记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_delete_capa_plan_track_record(
    record_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    _require_user(current_user)
    try:
        await delete_capa_plan_track_record(db, record_id)
        return success_response(data={"success": True}, message="删除成功")
    except AppException:
        raise
    except Exception as e:
        logger.exception("Failed to delete CAPA plan track record")
        raise AppException(status_code=500, message="服务暂时不可用，请稍后重试") from e
