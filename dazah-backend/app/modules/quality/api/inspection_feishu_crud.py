"""Inspection Feishu record CRUD API (generic, entity-driven).

提供按 entity_code 的通用新增 / 编辑 / 删除 / 单条读取 / 字段元数据 / 回拉能力，
让检验模块所有页面可在页面内直接同步飞书多维表格（含链接/附件字段可点击查看）。
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory, get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException
from app.core.response import success_response
from app.modules.quality.api.deps import (
    QUALITY_QA_SCOPE_PERMISSIONS,
)
from app.modules.quality.api.deps import (
    assert_quality_edit_scope as _assert_quality_edit_scope,
)
from app.modules.quality.api.deps import (
    require_user as _require_user,
)
from app.modules.quality.schemas.inspection_feishu_crud import (
    InspectionFeishuRecordBody,
)
from app.modules.quality.service.inspection_feishu_crud import (
    create_inspection_feishu_record,
    delete_inspection_feishu_record,
    get_inspection_entity_fields,
    get_inspection_feishu_attachment_content,
    get_inspection_feishu_attachment_preview,
    get_inspection_feishu_record,
    pull_inspection_feishu_records,
    update_inspection_feishu_record,
)
from app.modules.quality.service.inspection_finished_mirror import (
    FINISHED_MIRROR_ENTITIES,
    sync_finished_page,
)
from app.modules.quality.service.inspection_items_mirror import (
    ITEMS_MIRROR_PAGES,
    sync_items_page,
)

logger = logging.getLogger(__name__)
router = APIRouter()


async def _maybe_refresh_entity_mirror(entity_code: str) -> None:
    """物品/成品镜像页写飞书成功后顺带增量同步镜像，使列表即时反映改动。

    用独立会话执行：避免在请求事务里中途提交（主会话的写入已完成），
    同步失败不影响已成功的飞书写（写已提交），仅记日志。
    """
    try:
        in_scope = (
            entity_code in ITEMS_MIRROR_PAGES
            or entity_code in FINISHED_MIRROR_ENTITIES
        )
        if not in_scope:
            return
        async with async_session_factory() as sync_db:
            if entity_code in ITEMS_MIRROR_PAGES:
                await sync_items_page(sync_db, entity_code, incremental=True)
            else:
                await sync_finished_page(sync_db, entity_code, incremental=True)
    except AppException as exc:
        logger.info("mirror refresh skipped (%s): %s", entity_code, exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("mirror refresh failed (%s): %s", entity_code, exc)


@router.get(
    "/inspection/feishu/{entity_code}/fields",
    summary="获取检验实体字段元数据",
)
async def api_get_inspection_entity_fields(
    entity_code: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    return success_response(data=await get_inspection_entity_fields(db, entity_code))


@router.get(
    "/inspection/feishu/{entity_code}/records/{record_id}",
    summary="获取检验飞书记录详情",
)
async def api_get_inspection_feishu_record(
    entity_code: str,
    record_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    return success_response(
        data=await get_inspection_feishu_record(db, entity_code, record_id)
    )


@router.post(
    "/inspection/feishu/{entity_code}/records",
    summary="新增检验飞书记录（同步到多维表格）",
)
async def api_create_inspection_feishu_record(
    entity_code: str,
    body: InspectionFeishuRecordBody,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    user_id = _require_user(current_user)
    data = await create_inspection_feishu_record(
        db, entity_code, body.fields, actor_user_id=user_id
    )
    await _maybe_refresh_entity_mirror(entity_code)
    return success_response(data=data, message="创建成功，已同步飞书")


@router.put(
    "/inspection/feishu/{entity_code}/records/{record_id}",
    summary="编辑检验飞书记录（同步到多维表格）",
)
async def api_update_inspection_feishu_record(
    entity_code: str,
    record_id: str,
    body: InspectionFeishuRecordBody,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    user_id = _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["qc"],
    )
    data = await update_inspection_feishu_record(
        db, entity_code, record_id, body.fields, actor_user_id=user_id
    )
    await _maybe_refresh_entity_mirror(entity_code)
    return success_response(data=data, message="更新成功，已同步飞书")


@router.delete(
    "/inspection/feishu/{entity_code}/records/{record_id}",
    summary="删除检验飞书记录（同步到多维表格）",
)
async def api_delete_inspection_feishu_record(
    entity_code: str,
    record_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    user_id = _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["qc"],
    )
    data = await delete_inspection_feishu_record(
        db, entity_code, record_id, actor_user_id=user_id
    )
    await _maybe_refresh_entity_mirror(entity_code)
    return success_response(data=data, message="删除成功，已同步飞书")


@router.post(
    "/inspection/feishu/{entity_code}/pull",
    summary="回拉检验飞书记录",
)
async def api_pull_inspection_feishu_records(
    entity_code: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    return success_response(data=await pull_inspection_feishu_records(db, entity_code))


@router.get(
    "/inspection/feishu/{entity_code}/records/{record_id}/attachments/{file_token}/content",
    summary="下载检验记录附件（后端代理，携带飞书 token）",
)
async def api_get_inspection_feishu_attachment_content(
    entity_code: str,
    record_id: str,
    file_token: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    content, content_type, filename = await get_inspection_feishu_attachment_content(
        db, entity_code, record_id, file_token
    )
    encoded = quote(filename)
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": (
                f"attachment; filename=attachment; filename*=UTF-8''{encoded}"
            )
        },
    )


@router.get(
    "/inspection/feishu/{entity_code}/records/{record_id}/attachments/{file_token}/preview",
    summary="在线预览检验记录附件（图片/PDF 原样，office 转 PDF，inline 响应）",
)
async def api_get_inspection_feishu_attachment_preview(
    entity_code: str,
    record_id: str,
    file_token: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    content, content_type, filename = await get_inspection_feishu_attachment_preview(
        db, entity_code, record_id, file_token
    )
    encoded = quote(filename)
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": (
                f"inline; filename=preview; filename*=UTF-8''{encoded}"
            )
        },
    )
