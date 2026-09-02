"""HR Feishu settings API routes."""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException
from app.core.response import success_response
from app.modules.hr import feishu_settings_service as service
from app.modules.hr.schemas import (
    UpdateHrFeishuAppSettingsRequest,
    UpdateHrFeishuEntitySettingRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feishu-settings", tags=["人事-飞书设置"])


def _require_user(current_user: CurrentUser) -> None:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")


async def _restart_hr_ws_safely() -> None:
    """人事凭证变更后热重启人事飞书长连接（失败仅记录日志）。"""
    try:
        from app.modules.hr.feishu.ws_client import start_hr_ws_if_configured

        await start_hr_ws_if_configured()
    except Exception:
        logger.exception("人事飞书长连接热重启失败")


@router.get("/app", summary="获取人事模块飞书应用配置")
async def get_hr_feishu_app_settings(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    result = await service.get_hr_feishu_app_settings(db)
    return success_response(data=result.model_dump(mode="json"))


@router.put("/app", summary="保存人事模块飞书应用配置")
async def save_hr_feishu_app_settings(
    data: UpdateHrFeishuAppSettingsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    result = await service.update_hr_feishu_app_settings(db, data)
    asyncio.create_task(_restart_hr_ws_safely())
    return success_response(
        data=result.model_dump(mode="json"), message="飞书应用配置已保存"
    )


@router.post("/app/test", summary="测试人事模块飞书应用连接")
async def test_hr_feishu_app_settings(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    result = await service.test_hr_feishu_app_settings(db)
    return success_response(data=result.model_dump(mode="json"))


@router.get("/entities", summary="获取人事模块飞书实体配置")
async def list_hr_feishu_entity_settings(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    items = await service.list_hr_feishu_entity_settings(db)
    return success_response(data=[i.model_dump(mode="json") for i in items])


@router.put("/entities/{entity_code}", summary="保存人事模块飞书实体配置")
async def save_hr_feishu_entity_setting(
    entity_code: str,
    data: UpdateHrFeishuEntitySettingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    result = await service.update_hr_feishu_entity_setting(db, entity_code, data)
    return success_response(
        data=result.model_dump(mode="json"), message="实体配置已保存"
    )


@router.post("/entities/{entity_code}/test", summary="测试人事模块飞书实体配置")
async def test_hr_feishu_entity_setting(
    entity_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    result = await service.test_hr_feishu_entity_setting(db, entity_code)
    return success_response(data=result.model_dump(mode="json"))


@router.get("/entities/{entity_code}/tables", summary="读取飞书 Base 表列表")
async def list_hr_feishu_entity_tables(
    entity_code: str,
    app_token: str | None = Query(None, description="App Token（可选覆盖）"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    tables = await service.list_hr_feishu_tables(db, entity_code, app_token)
    return success_response(data=[t.model_dump(mode="json") for t in tables])


@router.get("/entities/{entity_code}/field-mapping", summary="获取字段对齐配置")
async def get_hr_feishu_entity_field_mapping(
    entity_code: str,
    app_token: str | None = Query(None),
    table_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    bundle = await service.get_hr_feishu_entity_field_mapping_bundle(
        db, entity_code, app_token, table_id
    )
    return success_response(data=bundle.model_dump(mode="json"))
