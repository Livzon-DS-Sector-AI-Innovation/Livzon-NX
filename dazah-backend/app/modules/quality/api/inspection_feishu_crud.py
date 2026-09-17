"""Inspection Feishu record CRUD API (generic, entity-driven).

提供按 entity_code 的通用新增 / 编辑 / 删除 / 单条读取 / 字段元数据 / 回拉能力，
让检验模块所有页面可在页面内直接同步飞书多维表格（含链接/附件字段可点击查看）。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response
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
from app.modules.quality.service.feishu_attachment_thumbnail import (
    get_attachment_thumbnail,
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
from app.modules.quality.service.inspection_instrument_mirror import (
    INSTRUMENT_MIRROR_ENTITIES,
)
from app.modules.quality.service.inspection_items_mirror import (
    ITEMS_MIRROR_PAGES,
    sync_items_page,
)
from app.modules.quality.service.inspection_material_mirror import (
    MATERIAL_MIRROR_ENTITIES,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# 飞书公式列（如外部校准「下次检定日期」=EDATE(检定日期,12)-1）在记录创建/
# 编辑的瞬间可能尚未算完，单条写穿会把空值存进镜像；而仪器镜像增量按日期/水位
# 过滤未必再覆盖该行。延迟数秒重拉该单条，把公式的迟到值补进镜像（best-effort，
# 失败仅记日志，每日全量兜底）。
_FORMULA_LAG_REFRESH_DELAYS: tuple[float, ...] = (5.0, 30.0)
_MIRROR_REFRESH_TASKS: set[asyncio.Task[None]] = set()


async def _refresh_record_mirror_later(
    entity_code: str,
    record_id: str,
    delays: tuple[float, ...] = _FORMULA_LAG_REFRESH_DELAYS,
) -> None:
    for delay in delays:
        await asyncio.sleep(delay)
        try:
            await _sync_single_record_to_mirror(entity_code, record_id)
        except AppException as exc:
            logger.info("delayed mirror refresh skipped (%s): %s", entity_code, exc)
        except Exception as exc:  # noqa: BLE001 - 补刷失败不影响主流程
            logger.warning(
                "delayed mirror refresh failed (%s/%s): %s",
                entity_code,
                record_id,
                exc,
            )


def _schedule_record_mirror_refresh(entity_code: str, record_id: str) -> None:
    """仪器实体写入飞书后调度后台延迟补刷（持强引用防止任务被 GC）。"""
    task = asyncio.create_task(
        _refresh_record_mirror_later(
            entity_code, record_id, _FORMULA_LAG_REFRESH_DELAYS
        )
    )
    _MIRROR_REFRESH_TASKS.add(task)
    task.add_done_callback(_MIRROR_REFRESH_TASKS.discard)


async def _maybe_refresh_entity_mirror(
    entity_code: str,
    record_id: str | None = None,
    *,
    deleted: bool = False,
) -> None:
    """写飞书成功后同步本地镜像，使列表即时反映改动。

    - 物料/成品：record_id 给定时单条写穿（单条 get_record → upsert 该行，
      删除则软删镜像行），不受增量同步"批号降序 + 整页无变更提前停止"
      的影响，编辑旧批号也即时生效；其它行的漂移由定时增量与每日全量兜底；
    - 物品/仪器：维持整页增量同步（按 last_modified 水位可捕捉编辑）。

    用独立会话执行：避免在请求事务里中途提交（主会话的写入已完成），
    同步失败不影响已成功的飞书写（写已提交），仅记日志。
    """
    from app.modules.quality.service.inspection_instrument_mirror import (
        sync_instrument_page,
    )

    try:
        if record_id is not None and (
            entity_code in MATERIAL_MIRROR_ENTITIES
            or entity_code in FINISHED_MIRROR_ENTITIES
            or entity_code in INSTRUMENT_MIRROR_ENTITIES
        ):
            await _sync_single_record_to_mirror(entity_code, record_id, deleted=deleted)
            if not deleted and entity_code in INSTRUMENT_MIRROR_ENTITIES:
                _schedule_record_mirror_refresh(entity_code, record_id)
            return
        in_scope = (
            entity_code in ITEMS_MIRROR_PAGES
            or entity_code in FINISHED_MIRROR_ENTITIES
            or entity_code in INSTRUMENT_MIRROR_ENTITIES
        )
        if not in_scope:
            return
        async with async_session_factory() as sync_db:
            if entity_code in ITEMS_MIRROR_PAGES:
                await sync_items_page(sync_db, entity_code, incremental=True)
            elif entity_code in FINISHED_MIRROR_ENTITIES:
                await sync_finished_page(sync_db, entity_code, incremental=True)
            else:
                await sync_instrument_page(sync_db, entity_code, incremental=True)
    except AppException as exc:
        logger.info("mirror refresh skipped (%s): %s", entity_code, exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("mirror refresh failed (%s): %s", entity_code, exc)


async def _maybe_spawn_maintenance_next(
    entity_code: str, record_id: str, submitted_fields: dict[str, Any]
) -> None:
    """维保记录填写「维护日期」保存后：自动置完成并生成下一期任务（独立会话）。

    原记录「是否完成」自动置「是」；新任务复制设备信息与通知人（维护人/
    复核人留空待实际维护填写），是否完成=否，下次维保时间=维护日期+周期表
    周期。失败仅记日志，不影响保存结果。
    """
    if entity_code != "qc_instr_maintenance":
        return
    if "维护日期" not in (submitted_fields or {}):
        return
    try:
        from app.modules.quality.service import quality_feishu_sync as fs
        from app.modules.quality.service.maintenance_schedule import (
            spawn_next_for_fields,
        )
        from app.modules.quality.service.quality_feishu_pages import (
            _resolve_runtime_entity,
        )
        from app.platform.integrations.feishu.bitable import BitableClient

        async with async_session_factory() as spawn_db:
            runtime, entity = await _resolve_runtime_entity(
                spawn_db, entity_code, direction="pull"
            )
            client = BitableClient(
                app_token=entity.app_token,
                app_id=runtime.app_id,
                app_secret=runtime.app_secret,
            )
            table_id = fs._require_table_id(entity)
            record = await client.get_record(table_id, record_id)
            if not record or not record.get("record_id"):
                return
            created = await spawn_next_for_fields(
                spawn_db, client, table_id, record_id, record.get("fields") or {}
            )
            if created:
                # 生成的下一期任务立即写穿镜像，页面无需等下一轮同步
                await _sync_single_record_to_mirror(entity_code, created[0])
    except AppException as exc:
        logger.info("maintenance spawn skipped: %s", exc)
    except Exception as exc:
        logger.warning("maintenance spawn failed: %s", exc)


async def _sync_single_record_to_mirror(
    entity_code: str,
    record_id: str,
    *,
    deleted: bool = False,
) -> None:
    """编辑/新增/删除单条记录后把该行写穿到物料/成品/仪器镜像（独立会话）。"""
    if entity_code in MATERIAL_MIRROR_ENTITIES:
        from app.modules.quality.service.inspection_material_mirror import (
            delete_mirror_record,
            upsert_record_by_id,
        )
    elif entity_code in FINISHED_MIRROR_ENTITIES:
        from app.modules.quality.service.inspection_finished_mirror import (
            delete_mirror_record,
            upsert_record_by_id,
        )
    elif entity_code in INSTRUMENT_MIRROR_ENTITIES:
        # 仪器镜像：新增/编辑走单条 upsert（增量水位有漏行竞态），删除走
        # 立即软删（增量不做删除对账，否则被删行残留到次日全量）
        from app.modules.quality.service.inspection_instrument_mirror import (
            delete_instrument_mirror_record,
            upsert_instrument_record_by_id,
        )

        async with async_session_factory() as sync_db:
            if deleted:
                await delete_instrument_mirror_record(sync_db, entity_code, record_id)
            else:
                await upsert_instrument_record_by_id(sync_db, entity_code, record_id)
        return
    else:
        return
    async with async_session_factory() as sync_db:
        if deleted:
            await delete_mirror_record(sync_db, entity_code, record_id)
        else:
            await upsert_record_by_id(sync_db, entity_code, record_id)


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
    await _maybe_refresh_entity_mirror(entity_code, str(data.get("record_id") or ""))
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
    # 维保记录：填写维护日期保存后先生成下一期任务，再刷镜像（新任务随刷新入镜）
    await _maybe_spawn_maintenance_next(entity_code, record_id, body.fields)
    await _maybe_refresh_entity_mirror(entity_code, record_id)
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
    await _maybe_refresh_entity_mirror(entity_code, record_id, deleted=True)
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
    "/inspection/feishu/{entity_code}/records/{record_id}/attachments/{file_token}/thumbnail",
    summary="列表缩略图（PIL 缩放为小图，避免列表页拉取原图全量字节）",
)
async def api_get_inspection_feishu_attachment_thumbnail(
    entity_code: str,
    record_id: str,
    file_token: str,
    max_width: int = Query(200, ge=16, le=512, description="缩略图最大宽度"),
    max_height: int = Query(200, ge=16, le=512, description="缩略图最大高度"),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    result = await get_attachment_thumbnail(
        db, entity_code, record_id, file_token, max_width, max_height
    )
    if result is None:
        raise AppException(
            message="该附件暂不支持生成缩略图，请下载后查看", status_code=400
        )
    content, content_type, filename = result
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": (
                f"inline; filename=thumbnail; filename*=UTF-8''{quote(filename)}"
            ),
            "Cache-Control": "private, max-age=86400",
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
