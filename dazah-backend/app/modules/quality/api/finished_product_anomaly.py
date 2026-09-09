"""成品异常报告（质量管理-成品异常报告）API endpoints.

成品异常报告按年分表（finished_product_anomaly_2025..2028），复用检验模块的
通用飞书记录读写能力：字段元数据 / 原始记录列表 / 单条详情 / 新增 / 编辑 /
删除 / 附件代理下载。字段名 = 飞书表真实字段名。
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException
from app.core.jobs import get_job_status, is_job_running, submit_job
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
from app.modules.quality.service.finished_product_anomaly_analysis import (
    ANALYSIS_YEARS,
    get_dashboard_aggregation,
    run_analysis_job,
)
from app.modules.quality.service.inspection_feishu_crud import (
    batch_create_record_share_links,
    build_feishu_base_url,
    create_inspection_feishu_record,
    delete_inspection_feishu_record,
    get_bitable_entity_reference,
    get_inspection_entity_fields,
    get_inspection_feishu_attachment_content,
    get_inspection_feishu_attachment_preview,
    get_inspection_feishu_record,
    list_bitable_feishu_records,
    update_inspection_feishu_record,
)

router = APIRouter()

FINISHED_PRODUCT_ANOMALY_YEARS: list[int] = list(range(2025, 2029))


def _anomaly_entity_code(year: int) -> str:
    if year not in FINISHED_PRODUCT_ANOMALY_YEARS:
        first, last = (
            FINISHED_PRODUCT_ANOMALY_YEARS[0],
            FINISHED_PRODUCT_ANOMALY_YEARS[-1],
        )
        raise AppException(
            message=f"不支持的成品异常报告年份: {year}（可选 {first}-{last}）",
            status_code=400,
        )
    return f"finished_product_anomaly_{year}"


@router.get(
    "/finished-product-anomaly/years",
    summary="获取成品异常报告年度表配置状态",
)
async def api_get_anomaly_years(
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    years = []
    for year in FINISHED_PRODUCT_ANOMALY_YEARS:
        entity_code = f"finished_product_anomaly_{year}"
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
    "/finished-product-anomaly/fields",
    summary="获取成品异常报告字段元数据",
)
async def api_get_anomaly_fields(
    year: int = Query(2025, description="成品异常报告年度"),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    return success_response(
        data=await get_inspection_entity_fields(db, _anomaly_entity_code(year))
    )


@router.get(
    "/finished-product-anomaly/records",
    summary="获取成品异常报告记录列表",
)
async def api_list_anomaly_records(
    year: int = Query(2025, description="成品异常报告年度"),
    keyword: str | None = Query(None, description="关键词（按全部字段模糊匹配）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    return success_response(
        data=await list_bitable_feishu_records(
            db,
            _anomaly_entity_code(year),
            keyword=keyword,
            page=page,
            page_size=page_size,
        )
    )


@router.get(
    "/finished-product-anomaly/records/{record_id}",
    summary="获取成品异常报告记录详情",
)
async def api_get_anomaly_record(
    record_id: str,
    year: int = Query(2025, description="成品异常报告年度"),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    return success_response(
        data=await get_inspection_feishu_record(
            db, _anomaly_entity_code(year), record_id
        )
    )


@router.post(
    "/finished-product-anomaly/records",
    summary="新增成品异常报告记录（同步到多维表格）",
)
async def api_create_anomaly_record(
    body: InspectionFeishuRecordBody,
    year: int = Query(2025, description="成品异常报告年度"),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    user_id = _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["product_qa"],
    )
    return success_response(
        data=await create_inspection_feishu_record(
            db, _anomaly_entity_code(year), body.fields, actor_user_id=user_id
        ),
        message="创建成功，已同步飞书",
        status_code=201,
    )


@router.put(
    "/finished-product-anomaly/records/{record_id}",
    summary="编辑成品异常报告记录（同步到多维表格）",
)
async def api_update_anomaly_record(
    record_id: str,
    body: InspectionFeishuRecordBody,
    year: int = Query(2025, description="成品异常报告年度"),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    user_id = _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["product_qa"],
    )
    return success_response(
        data=await update_inspection_feishu_record(
            db,
            _anomaly_entity_code(year),
            record_id,
            body.fields,
            actor_user_id=user_id,
        ),
        message="更新成功，已同步飞书",
    )


@router.delete(
    "/finished-product-anomaly/records/{record_id}",
    summary="删除成品异常报告记录（同步到多维表格）",
)
async def api_delete_anomaly_record(
    record_id: str,
    year: int = Query(2025, description="成品异常报告年度"),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    user_id = _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["product_qa"],
    )
    return success_response(
        data=await delete_inspection_feishu_record(
            db, _anomaly_entity_code(year), record_id, actor_user_id=user_id
        ),
        message="删除成功，已同步飞书",
    )


@router.post(
    "/finished-product-anomaly/records/share-links",
    summary="批量生成成品异常报告记录分享链接（跳转飞书对应行）",
)
async def api_batch_create_anomaly_share_links(
    body: InspectionFeishuRecordBody,
    year: int = Query(2025, description="成品异常报告年度"),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    record_ids_raw = body.fields.get("record_ids")
    record_ids = [
        str(item) for item in record_ids_raw if str(item).strip()
    ] if isinstance(record_ids_raw, list) else []
    links = await batch_create_record_share_links(
        db, _anomaly_entity_code(year), record_ids
    )
    return success_response(
        data={"record_share_links": links},
        message="记录链接已生成",
    )


@router.get(
    "/finished-product-anomaly/records/{record_id}/attachments/{file_token}/content",
    summary="下载成品异常报告记录附件（后端代理，携带飞书 token）",
)
async def api_get_anomaly_attachment_content(
    record_id: str,
    file_token: str,
    year: int = Query(2025, description="成品异常报告年度"),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    content, content_type, filename = await get_inspection_feishu_attachment_content(
        db, _anomaly_entity_code(year), record_id, file_token
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
    "/finished-product-anomaly/dashboard",
    summary="成品异常仪表盘聚合（按产品×异常类型，AI 分类结果关联）",
)
async def api_get_anomaly_dashboard(
    year: int | None = Query(
        None, description="年份；不传则聚合 2025-2028 全部已配置年份"
    ),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    if year is not None and year not in ANALYSIS_YEARS:
        raise AppException(
            message=f"不支持的成品异常报告年份: {year}",
            status_code=400,
        )
    return success_response(data=await get_dashboard_aggregation(db, year))


@router.post(
    "/finished-product-anomaly/analysis/run",
    summary="触发成品异常记录 AI 分类（后台 job，增量去重）",
)
async def api_run_anomaly_analysis(
    year: int | None = Query(None, description="只分析指定年份；不传则分析全部年份"),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    user_id = _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["product_qa"],
    )
    years = [year] if year is not None else list(ANALYSIS_YEARS)
    job_id = f"job:fp-anomaly-analysis:{user_id}"
    if await is_job_running(job_id):
        raise AppException(message="已有分析任务在运行，请稍候", status_code=409)
    job_id = await submit_job(
        run_analysis_job,
        task_id=job_id,
        ttl=1800,
        status_extra={"years": years, "owner": str(user_id)},
        years=years,
        job_id=job_id,
    )
    return success_response(data={"job_id": job_id, "years": years}, status_code=202)


@router.get(
    "/finished-product-anomaly/analysis/status",
    summary="查询成品异常 AI 分类任务进度",
)
async def api_get_anomaly_analysis_status(
    job_id: str = Query(..., description="任务 ID"),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    status = await get_job_status(job_id)
    if status is None:
        raise AppException(message="任务不存在或已过期", status_code=404)
    return success_response(data={"job_id": job_id, **status})


@router.get(
    "/finished-product-anomaly/records/{record_id}/attachments/{file_token}/preview",
    summary="在线预览成品异常报告记录附件（图片/PDF 原样，office 转 PDF，inline 响应）",
)
async def api_get_anomaly_attachment_preview(
    record_id: str,
    file_token: str,
    year: int = Query(2025, description="成品异常报告年度"),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    content, content_type, filename = await get_inspection_feishu_attachment_preview(
        db, _anomaly_entity_code(year), record_id, file_token
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
