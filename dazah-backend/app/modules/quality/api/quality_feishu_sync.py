"""质量模块飞书同步 API 路由（Q1 拆分自 quality_management.py）。"""

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import (
    AppException,
)
from app.core.response import success_response
from app.modules.quality import service
from app.modules.quality.api.deps import (
    require_user as _require_user,
)
from app.modules.quality.api.deps import (
    try_acquire_action_lock,
)
from app.modules.quality.schemas import (
    QualityFeishuAppSettingsDetail,
    QualityFeishuEntitySettingItem,
    QualityFeishuSettingsTestResult,
    QualityFeishuTableOption,
    UpdateQualityFeishuAppSettingsRequest,
    UpdateQualityFeishuEntitySettingRequest,
)
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/feishu-sync/capas/{capa_id}",
    summary="同步CAPA到飞书Base",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def sync_capa_record_to_feishu(
    capa_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await service.sync_capa_to_feishu(db, capa_id)
    return success_response(data=result)


@router.post(
    "/feishu-sync/deviation-investigation-push-records/{record_id}",
    summary="同步偏差报告记录到飞书Base",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def sync_deviation_investigation_push_record_to_feishu(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await service.sync_deviation_investigation_push_record_to_feishu(
        db, record_id
    )
    return success_response(data=result)


@router.post(
    "/feishu-sync/capa-plan-tracks/{track_id}",
    summary="同步CAPA计划跟踪到飞书Base",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def sync_capa_plan_track_record_to_feishu(
    track_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await service.sync_capa_plan_track_to_feishu(db, track_id)
    return success_response(data=result)


@router.post(
    "/feishu-sync/pull",
    summary="从飞书 Base 回拉质量数据",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def pull_quality_records_from_feishu(
    entity_code: str | None = Query(
        None, description="指定回拉的实体代码，不传则回拉全部"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    if not await try_acquire_action_lock(
        f"feishu-pull:{entity_code or 'all'}", timeout=600
    ):
        raise AppException(message="同步正在进行中，请勿重复操作")
    result = await service.pull_quality_records_from_feishu(db, entity_code=entity_code)
    return success_response(data=result)


@router.get(
    "/feishu-sync/conflicts",
    summary="获取质量模块飞书同步冲突列表",
    response_model=ApiResponseEnvelope[list[dict[str, Any]]],
)
async def list_quality_sync_conflicts(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await service.get_quality_sync_conflicts(db, limit=limit)
    return success_response(
        data=result,
        meta={
            "total": len(result),
            "limit": limit,
        },
    )


@router.get(
    "/feishu-settings/app",
    summary="获取质量模块飞书应用配置",
    response_model=QualityFeishuAppSettingsDetail,
)
async def get_quality_feishu_app_settings(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> QualityFeishuAppSettingsDetail:
    _require_user(current_user)
    result = await service.get_quality_feishu_app_settings(db)
    return result


@router.put(
    "/feishu-settings/app",
    summary="保存质量模块飞书应用配置",
    response_model=QualityFeishuAppSettingsDetail,
)
async def save_quality_feishu_app_settings(
    data: UpdateQualityFeishuAppSettingsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> QualityFeishuAppSettingsDetail:
    _require_user(current_user)
    return await service.update_quality_feishu_app_settings(db, data)


@router.post(
    "/feishu-settings/app/test",
    summary="测试质量模块飞书应用连接",
    response_model=QualityFeishuSettingsTestResult,
)
async def test_quality_feishu_app_settings(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> QualityFeishuSettingsTestResult:
    _require_user(current_user)
    return await service.test_quality_feishu_app_settings(db)


@router.get(
    "/feishu-settings/entities",
    summary="获取质量模块飞书实体配置",
    response_model=list[QualityFeishuEntitySettingItem],
)
async def list_quality_feishu_entity_settings(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> list[QualityFeishuEntitySettingItem]:
    _require_user(current_user)
    items = await service.list_quality_feishu_entity_settings(db)
    # This endpoint predates the module envelope convention and is consumed
    # by the existing settings page as a plain list. Keep that contract while
    # all writes remain authenticated and audited.
    return items


@router.put(
    "/feishu-settings/entities/{entity_code}",
    summary="保存质量模块飞书实体配置",
    response_model=QualityFeishuEntitySettingItem,
)
async def save_quality_feishu_entity_setting(
    entity_code: str,
    data: UpdateQualityFeishuEntitySettingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> QualityFeishuEntitySettingItem:
    _require_user(current_user)
    return await service.update_quality_feishu_entity_setting(db, entity_code, data)


@router.post(
    "/feishu-settings/entities/{entity_code}/test",
    summary="测试质量模块飞书实体配置",
    response_model=QualityFeishuSettingsTestResult,
)
async def test_quality_feishu_entity_setting(
    entity_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> QualityFeishuSettingsTestResult:
    _require_user(current_user)
    return await service.test_quality_feishu_entity_setting(db, entity_code)


@router.get(
    "/feishu-settings/entities/{entity_code}/tables",
    summary="获取质量模块飞书实体的 Base 子表列表",
    response_model=list[QualityFeishuTableOption],
)
async def list_quality_feishu_entity_tables(
    entity_code: str,
    app_token: str | None = Query(
        None, description="可选：指定 App Token，不传则使用实体已保存的"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> list[QualityFeishuTableOption]:
    _require_user(current_user)
    items = await service.list_quality_feishu_tables(db, entity_code, app_token)
    return items
