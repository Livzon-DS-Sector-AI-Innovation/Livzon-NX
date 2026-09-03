"""QC验证（验证与确认-QC验证）API endpoints.

QC验证按年分表（validation_qc_2024..2028），复用检验模块的通用飞书记录
读写能力：字段元数据 / 原始记录列表 / 单条详情 / 新增 / 编辑 / 删除 /
附件代理下载。字段名 = 飞书表真实字段名。
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
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
    batch_create_record_share_links,
    build_feishu_base_url,
    create_inspection_feishu_record,
    delete_inspection_feishu_record,
    get_bitable_entity_reference,
    get_inspection_entity_fields,
    get_inspection_feishu_attachment_content,
    get_inspection_feishu_record,
    list_bitable_feishu_records,
    update_inspection_feishu_record,
)

router = APIRouter()

QC_VALIDATION_YEARS: list[int] = list(range(2024, 2029))


def _qc_entity_code(year: int) -> str:
    if year not in QC_VALIDATION_YEARS:
        first, last = QC_VALIDATION_YEARS[0], QC_VALIDATION_YEARS[-1]
        raise AppException(
            message=f"不支持的QC验证年份: {year}（可选 {first}-{last}）",
            status_code=400,
        )
    return f"validation_qc_{year}"


@router.get(
    "/validation-qc/years",
    summary="获取QC验证年度表配置状态",
)
async def api_get_qc_validation_years(
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    years = []
    for year in QC_VALIDATION_YEARS:
        entity_code = f"validation_qc_{year}"
        reference = await get_bitable_entity_reference(db, entity_code)
        years.append(
            {
                "year": year,
                "entity_code": entity_code,
                "table_configured": reference is not None,
                "feishu_url": (
                    build_feishu_base_url(
                        reference["app_token"], reference["table_id"]
                    )
                    if reference
                    else None
                ),
            }
        )
    return success_response(data={"years": years})


@router.get(
    "/validation-qc/fields",
    summary="获取QC验证字段元数据",
)
async def api_get_qc_validation_fields(
    year: int = Query(2026, description="QC验证年度"),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    return success_response(
        data=await get_inspection_entity_fields(db, _qc_entity_code(year))
    )


@router.get(
    "/validation-qc/records",
    summary="获取QC验证记录列表",
)
async def api_list_qc_validation_records(
    year: int = Query(2026, description="QC验证年度"),
    keyword: str | None = Query(None, description="关键词（按全部字段模糊匹配）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    return success_response(
        data=await list_bitable_feishu_records(
            db, _qc_entity_code(year), keyword=keyword, page=page, page_size=page_size
        )
    )


@router.get(
    "/validation-qc/records/{record_id}",
    summary="获取QC验证记录详情",
)
async def api_get_qc_validation_record(
    record_id: str,
    year: int = Query(2026, description="QC验证年度"),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    return success_response(
        data=await get_inspection_feishu_record(db, _qc_entity_code(year), record_id)
    )


@router.post(
    "/validation-qc/records",
    summary="新增QC验证记录（同步到多维表格）",
)
async def api_create_qc_validation_record(
    body: InspectionFeishuRecordBody,
    year: int = Query(2026, description="QC验证年度"),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    user_id = _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["validation_qa"],
    )
    return success_response(
        data=await create_inspection_feishu_record(
            db, _qc_entity_code(year), body.fields, actor_user_id=user_id
        ),
        message="创建成功，已同步飞书",
        status_code=201,
    )


@router.put(
    "/validation-qc/records/{record_id}",
    summary="编辑QC验证记录（同步到多维表格）",
)
async def api_update_qc_validation_record(
    record_id: str,
    body: InspectionFeishuRecordBody,
    year: int = Query(2026, description="QC验证年度"),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    user_id = _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["validation_qa"],
    )
    return success_response(
        data=await update_inspection_feishu_record(
            db, _qc_entity_code(year), record_id, body.fields, actor_user_id=user_id
        ),
        message="更新成功，已同步飞书",
    )


@router.delete(
    "/validation-qc/records/{record_id}",
    summary="删除QC验证记录（同步到多维表格）",
)
async def api_delete_qc_validation_record(
    record_id: str,
    year: int = Query(2026, description="QC验证年度"),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    user_id = _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["validation_qa"],
    )
    return success_response(
        data=await delete_inspection_feishu_record(
            db, _qc_entity_code(year), record_id, actor_user_id=user_id
        ),
        message="删除成功，已同步飞书",
    )


@router.post(
    "/validation-qc/records/share-links",
    summary="批量生成QC验证记录分享链接（跳转飞书对应行）",
)
async def api_batch_create_qc_validation_share_links(
    body: InspectionFeishuRecordBody,
    year: int = Query(2026, description="QC验证年度"),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    record_ids_raw = body.fields.get("record_ids")
    record_ids = [
        str(item) for item in record_ids_raw if str(item).strip()
    ] if isinstance(record_ids_raw, list) else []
    links = await batch_create_record_share_links(
        db, _qc_entity_code(year), record_ids
    )
    return success_response(
        data={"record_share_links": links},
        message="记录链接已生成",
    )


@router.get(
    "/validation-qc/records/{record_id}/attachments/{file_token}/content",
    summary="下载QC验证记录附件（后端代理，携带飞书 token）",
)
async def api_get_qc_validation_attachment_content(
    record_id: str,
    file_token: str,
    year: int = Query(2026, description="QC验证年度"),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    content, content_type, filename = await get_inspection_feishu_attachment_content(
        db, _qc_entity_code(year), record_id, file_token
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
