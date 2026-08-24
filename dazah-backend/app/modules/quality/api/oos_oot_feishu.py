"""OOS/OOT Feishu page API endpoints.

Provides CRUD + pull endpoints that operate directly on Feishu Bitable.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException
from app.core.response import error_response, paginated_response, success_response
from app.modules.quality.api.deps import require_user as _require_user
from app.modules.quality.service.oos_oot_export import (
    export_oos_ledger,
    export_oot_ledger,
)
from app.modules.quality.service.quality_feishu_pages_oos_oot import (
    create_oos_ledger_record,
    create_oos_oot_investigation_push_record,
    create_oos_oot_report_record,
    create_oot_ledger_record,
    create_product_department_record,
    delete_oos_ledger_record,
    delete_oos_oot_investigation_push_record,
    delete_oos_oot_report_record,
    delete_oot_ledger_record,
    delete_product_department_record,
    list_oos_ledger_records,
    # Investigation push records
    list_oos_oot_investigation_push_records,
    # Report records
    list_oos_oot_report_records,
    # OOT Ledger
    list_oot_ledger_records,
    # Product Department
    list_product_department_records,
    pull_oos_ledger_records,
    pull_oos_oot_investigation_push_records,
    pull_oos_oot_report_records,
    pull_oot_ledger_records,
    pull_product_department_records,
    update_oos_ledger_record,
    update_oos_oot_investigation_push_record,
    update_oos_oot_report_record,
    update_oot_ledger_record,
    update_product_department_record,
)
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/oos-oot")


# ============ OOSOOT Report Records ============


@router.get(
    "/report-records",
    summary="获取OOSOOT报告记录列表",
    response_model=ApiResponseEnvelope[list[dict[str, Any]]],
)
async def api_list_report_records(
    keyword: str | None = Query(None, description="关键词搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        result = await list_oos_oot_report_records(
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
    except Exception:
        logger.exception("Failed to list OOSOOT report records")
        return error_response(message="获取列表失败，请稍后重试", status_code=500)


@router.post(
    "/report-records",
    summary="创建OOSOOT报告记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_create_report_record(
    data: dict[str, Any] = Body(...),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        result = await create_oos_oot_report_record(db, data)
        return success_response(data=result, message="创建成功")
    except AppException:
        raise
    except Exception:
        logger.exception("Failed to create OOSOOT report record")
        return error_response(message="创建失败，请稍后重试", status_code=500)


@router.put(
    "/report-records/{record_id}",
    summary="更新OOSOOT报告记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_update_report_record(
    record_id: str,
    data: dict[str, Any] = Body(...),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        result = await update_oos_oot_report_record(db, record_id, data)
        return success_response(data=result, message="更新成功")
    except AppException:
        raise
    except Exception:
        logger.exception("Failed to update OOSOOT report record")
        return error_response(message="更新失败，请稍后重试", status_code=500)


@router.delete(
    "/report-records/{record_id}",
    summary="删除OOSOOT报告记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_delete_report_record(
    record_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        await delete_oos_oot_report_record(db, record_id)
        return success_response(message="已删除")
    except AppException:
        raise
    except Exception:
        logger.exception("Failed to delete OOSOOT report record")
        return error_response(message="删除失败，请稍后重试", status_code=500)


# ============ Export ============


@router.get("/oos-ledger/export", summary="导出OOS台账为docx")
async def api_export_oos_ledger(
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        output = await export_oos_ledger(db)
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": "attachment; filename=检验结果OOS调查列表.docx"
            },
        )
    except AppException:
        raise
    except Exception:
        logger.exception("Failed to export OOS ledger")
        return error_response(message="操作失败，请稍后重试", status_code=500)


@router.get("/oot-ledger/export", summary="导出OOT台账为docx")
async def api_export_oot_ledger(
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        output = await export_oot_ledger(db)
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": "attachment; filename=检验结果OOT调查列表.docx"
            },
        )
    except AppException:
        raise
    except Exception:
        logger.exception("Failed to export OOT ledger")
        return error_response(message="操作失败，请稍后重试", status_code=500)


@router.post(
    "/report-records/pull",
    summary="从飞书拉取OOSOOT报告记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_pull_report_records(
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        result = await pull_oos_oot_report_records(db)
        return success_response(data=result, message="拉取完成")
    except AppException:
        raise
    except Exception:
        logger.exception("Failed to pull OOSOOT report records")
        return error_response(message="操作失败，请稍后重试", status_code=500)


# ============ OOSOOT Investigation Push Records ============


@router.get(
    "/investigation-push-records",
    summary="获取OOSOOT调查推送记录列表",
    response_model=ApiResponseEnvelope[list[dict[str, Any]]],
)
async def api_list_investigation_push_records(
    oos_oot_code: str | None = Query(None, description="OOS/OOT编号"),
    push_round: str | None = Query(None, description="第N次推送"),
    department_head_result: str | None = Query(None, description="部门负责人审核结果"),
    qa_result: str | None = Query(None, description="QA审核结果"),
    qa_head_result: str | None = Query(None, description="QA负责人审核结果"),
    process_status: str | None = Query(None, description="流程状态"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        result = await list_oos_oot_investigation_push_records(
            db,
            oos_oot_code=oos_oot_code,
            push_round=push_round,
            department_head_result=department_head_result,
            qa_result=qa_result,
            qa_head_result=qa_head_result,
            process_status=process_status,
            page=page,
            page_size=page_size,
        )
        return paginated_response(
            data=result["items"],
            page=result["page"],
            page_size=result["page_size"],
            total=result["total"],
        )
    except AppException:
        raise
    except Exception:
        logger.exception("Failed to list OOSOOT investigation push records")
        return error_response(message="获取列表失败，请稍后重试", status_code=500)


@router.post(
    "/investigation-push-records",
    summary="创建OOSOOT调查推送记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_create_investigation_push_record(
    data: dict[str, Any] = Body(...),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        result = await create_oos_oot_investigation_push_record(db, data)
        return success_response(data=result, message="创建成功")
    except AppException:
        raise
    except Exception:
        logger.exception("Failed to create OOSOOT investigation push record")
        return error_response(message="创建失败，请稍后重试", status_code=500)


@router.put(
    "/investigation-push-records/{record_id}",
    summary="更新OOSOOT调查推送记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_update_investigation_push_record(
    record_id: str,
    data: dict[str, Any] = Body(...),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        result = await update_oos_oot_investigation_push_record(db, record_id, data)
        return success_response(data=result, message="更新成功")
    except AppException:
        raise
    except Exception:
        logger.exception("Failed to update OOSOOT investigation push record")
        return error_response(message="更新失败，请稍后重试", status_code=500)


@router.delete(
    "/investigation-push-records/{record_id}",
    summary="删除OOSOOT调查推送记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_delete_investigation_push_record(
    record_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        await delete_oos_oot_investigation_push_record(db, record_id)
        return success_response(message="已删除")
    except AppException:
        raise
    except Exception:
        logger.exception("Failed to delete OOSOOT investigation push record")
        return error_response(message="删除失败，请稍后重试", status_code=500)


@router.post(
    "/investigation-push-records/pull",
    summary="从飞书拉取OOSOOT调查推送记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_pull_investigation_push_records(
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        result = await pull_oos_oot_investigation_push_records(db)
        return success_response(data=result, message="拉取完成")
    except AppException:
        raise
    except Exception:
        logger.exception("Failed to pull OOSOOT investigation push records")
        return error_response(message="操作失败，请稍后重试", status_code=500)


# ============ OOS Ledger ============


@router.get(
    "/oos-ledger",
    summary="获取OOS台账列表",
    response_model=ApiResponseEnvelope[list[dict[str, Any]]],
)
async def api_list_oos_ledger(
    keyword: str | None = Query(None, description="关键词搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        result = await list_oos_ledger_records(
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
    except Exception:
        logger.exception("Failed to list OOS ledger records")
        return error_response(message="获取列表失败，请稍后重试", status_code=500)


@router.post(
    "/oos-ledger",
    summary="创建OOS台账记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_create_oos_ledger(
    data: dict[str, Any] = Body(...),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        result = await create_oos_ledger_record(db, data)
        return success_response(data=result, message="创建成功")
    except AppException:
        raise
    except Exception:
        logger.exception("Failed to create OOS ledger record")
        return error_response(message="创建失败，请稍后重试", status_code=500)


@router.put(
    "/oos-ledger/{record_id}",
    summary="更新OOS台账记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_update_oos_ledger(
    record_id: str,
    data: dict[str, Any] = Body(...),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        result = await update_oos_ledger_record(db, record_id, data)
        return success_response(data=result, message="更新成功")
    except AppException:
        raise
    except Exception:
        logger.exception("Failed to update OOS ledger record")
        return error_response(message="更新失败，请稍后重试", status_code=500)


@router.delete(
    "/oos-ledger/{record_id}",
    summary="删除OOS台账记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_delete_oos_ledger(
    record_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        await delete_oos_ledger_record(db, record_id)
        return success_response(message="已删除")
    except AppException:
        raise
    except Exception:
        logger.exception("Failed to delete OOS ledger record")
        return error_response(message="删除失败，请稍后重试", status_code=500)


@router.post(
    "/oos-ledger/pull",
    summary="从飞书拉取OOS台账",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_pull_oos_ledger(
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        result = await pull_oos_ledger_records(db)
        return success_response(data=result, message="拉取完成")
    except AppException:
        raise
    except Exception:
        logger.exception("Failed to pull OOS ledger records")
        return error_response(message="操作失败，请稍后重试", status_code=500)


# ============ OOT Ledger ============


@router.get(
    "/oot-ledger",
    summary="获取OOT台账列表",
    response_model=ApiResponseEnvelope[list[dict[str, Any]]],
)
async def api_list_oot_ledger(
    keyword: str | None = Query(None, description="关键词搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        result = await list_oot_ledger_records(
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
    except Exception:
        logger.exception("Failed to list OOT ledger records")
        return error_response(message="获取列表失败，请稍后重试", status_code=500)


@router.post(
    "/oot-ledger",
    summary="创建OOT台账记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_create_oot_ledger(
    data: dict[str, Any] = Body(...),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        result = await create_oot_ledger_record(db, data)
        return success_response(data=result, message="创建成功")
    except AppException:
        raise
    except Exception:
        logger.exception("Failed to create OOT ledger record")
        return error_response(message="创建失败，请稍后重试", status_code=500)


@router.put(
    "/oot-ledger/{record_id}",
    summary="更新OOT台账记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_update_oot_ledger(
    record_id: str,
    data: dict[str, Any] = Body(...),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        result = await update_oot_ledger_record(db, record_id, data)
        return success_response(data=result, message="更新成功")
    except AppException:
        raise
    except Exception:
        logger.exception("Failed to update OOT ledger record")
        return error_response(message="更新失败，请稍后重试", status_code=500)


@router.delete(
    "/oot-ledger/{record_id}",
    summary="删除OOT台账记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_delete_oot_ledger(
    record_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        await delete_oot_ledger_record(db, record_id)
        return success_response(message="已删除")
    except AppException:
        raise
    except Exception:
        logger.exception("Failed to delete OOT ledger record")
        return error_response(message="删除失败，请稍后重试", status_code=500)


@router.post(
    "/oot-ledger/pull",
    summary="从飞书拉取OOT台账",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_pull_oot_ledger(
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        result = await pull_oot_ledger_records(db)
        return success_response(data=result, message="拉取完成")
    except AppException:
        raise
    except Exception:
        logger.exception("Failed to pull OOT ledger records")
        return error_response(message="操作失败，请稍后重试", status_code=500)


# ============ Product Department ============


@router.get(
    "/product-departments",
    summary="获取产品涉及部门列表",
    response_model=ApiResponseEnvelope[list[dict[str, Any]]],
)
async def api_list_product_departments(
    keyword: str | None = Query(None, description="关键词搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        result = await list_product_department_records(
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
    except Exception:
        logger.exception("Failed to list product department records")
        return error_response(message="获取列表失败，请稍后重试", status_code=500)


@router.post(
    "/product-departments",
    summary="创建产品涉及部门记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_create_product_department(
    data: dict[str, Any] = Body(...),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        result = await create_product_department_record(db, data)
        return success_response(data=result, message="创建成功")
    except AppException:
        raise
    except Exception:
        logger.exception("Failed to create product department record")
        return error_response(message="创建失败，请稍后重试", status_code=500)


@router.put(
    "/product-departments/{record_id}",
    summary="更新产品涉及部门记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_update_product_department(
    record_id: str,
    data: dict[str, Any] = Body(...),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        result = await update_product_department_record(db, record_id, data)
        return success_response(data=result, message="更新成功")
    except AppException:
        raise
    except Exception:
        logger.exception("Failed to update product department record")
        return error_response(message="更新失败，请稍后重试", status_code=500)


@router.delete(
    "/product-departments/{record_id}",
    summary="删除产品涉及部门记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_delete_product_department(
    record_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        await delete_product_department_record(db, record_id)
        return success_response(message="已删除")
    except AppException:
        raise
    except Exception:
        logger.exception("Failed to delete product department record")
        return error_response(message="删除失败，请稍后重试", status_code=500)


@router.post(
    "/product-departments/pull",
    summary="从飞书拉取产品涉及部门",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_pull_product_departments(
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        result = await pull_product_department_records(db)
        return success_response(data=result, message="拉取完成")
    except AppException:
        raise
    except Exception:
        logger.exception("Failed to pull product department records")
        return error_response(message="操作失败，请稍后重试", status_code=500)
