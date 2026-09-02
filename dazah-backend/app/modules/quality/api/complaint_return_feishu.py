"""Complaint and Return/Recall Feishu page API endpoints.

Provides CRUD + pull endpoints that operate directly on Feishu Bitable.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.response import paginated_response, success_response
from app.modules.quality.api.deps import (
    QUALITY_QA_SCOPE_PERMISSIONS,
)
from app.modules.quality.api.deps import (
    assert_quality_edit_scope as _assert_quality_edit_scope,
)
from app.modules.quality.api.deps import require_user as _require_user
from app.modules.quality.service.quality_feishu_pages_complaint_return import (
    create_complaint_ledger_record,
    create_return_application_record,
    create_return_ledger_record,
    delete_complaint_ledger_record,
    delete_return_application_record,
    delete_return_ledger_record,
    list_complaint_ledger_records,
    # Return Application
    list_return_application_records,
    # Return Ledger
    list_return_ledger_records,
    pull_complaint_ledger_records,
    pull_return_application_records,
    pull_return_ledger_records,
    update_complaint_ledger_record,
    update_return_application_record,
    update_return_ledger_record,
)
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)

router = APIRouter()


# ============ Complaint Ledger (投诉台账) ============


@router.get(
    "/complaint-ledger",
    summary="获取投诉台账列表（飞书）",
    response_model=ApiResponseEnvelope[list[dict[str, Any]]],
)
async def api_list_complaint_ledger(
    keyword: str | None = Query(None, description="关键词搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    result = await list_complaint_ledger_records(
        db, keyword=keyword, page=page, page_size=page_size
    )
    return paginated_response(
        data=result["items"],
        page=result["page"],
        page_size=result["page_size"],
        total=result["total"],
    )


@router.post(
    "/complaint-ledger",
    summary="创建投诉台账记录（飞书）",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_create_complaint_ledger(
    data: dict[str, Any],
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    result = await create_complaint_ledger_record(db, data)
    return success_response(data=result)


@router.put(
    "/complaint-ledger/{record_id}",
    summary="更新投诉台账记录（飞书）",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_update_complaint_ledger(
    record_id: str,
    data: dict[str, Any],
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["system_qa"],
    )
    result = await update_complaint_ledger_record(db, record_id, data)
    return success_response(data=result)


@router.delete(
    "/complaint-ledger/{record_id}",
    summary="删除投诉台账记录（飞书）",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_delete_complaint_ledger(
    record_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["system_qa"],
    )
    await delete_complaint_ledger_record(db, record_id)
    return success_response(message="已删除")


@router.post(
    "/complaint-ledger/pull",
    summary="拉取投诉台账记录（飞书->本地）",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_pull_complaint_ledger(
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    result = await pull_complaint_ledger_records(db)
    return success_response(data=result)


# ============ Return Application (退货申请表) ============


@router.get(
    "/return-application",
    summary="获取退货申请表列表（飞书）",
    response_model=ApiResponseEnvelope[list[dict[str, Any]]],
)
async def api_list_return_application(
    keyword: str | None = Query(None, description="关键词搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    result = await list_return_application_records(
        db, keyword=keyword, page=page, page_size=page_size
    )
    return paginated_response(
        data=result["items"],
        page=result["page"],
        page_size=result["page_size"],
        total=result["total"],
    )


@router.post(
    "/return-application",
    summary="创建退货申请记录（飞书）",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_create_return_application(
    data: dict[str, Any],
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    result = await create_return_application_record(db, data)
    return success_response(data=result)


@router.put(
    "/return-application/{record_id}",
    summary="更新退货申请记录（飞书）",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_update_return_application(
    record_id: str,
    data: dict[str, Any],
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    await _assert_quality_edit_scope(db, current_user)
    result = await update_return_application_record(db, record_id, data)
    return success_response(data=result)


@router.delete(
    "/return-application/{record_id}",
    summary="删除退货申请记录（飞书）",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_delete_return_application(
    record_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    await _assert_quality_edit_scope(db, current_user)
    await delete_return_application_record(db, record_id)
    return success_response(message="已删除")


@router.post(
    "/return-application/pull",
    summary="拉取退货申请记录（飞书->本地）",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_pull_return_application(
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    result = await pull_return_application_records(db)
    return success_response(data=result)


# ============ Return Ledger (退回台账) ============


@router.get(
    "/return-ledger",
    summary="获取退回台账列表（飞书）",
    response_model=ApiResponseEnvelope[list[dict[str, Any]]],
)
async def api_list_return_ledger(
    keyword: str | None = Query(None, description="关键词搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    result = await list_return_ledger_records(
        db, keyword=keyword, page=page, page_size=page_size
    )
    return paginated_response(
        data=result["items"],
        page=result["page"],
        page_size=result["page_size"],
        total=result["total"],
    )


@router.post(
    "/return-ledger",
    summary="创建退回台账记录（飞书）",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_create_return_ledger(
    data: dict[str, Any],
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    result = await create_return_ledger_record(db, data)
    return success_response(data=result)


@router.put(
    "/return-ledger/{record_id}",
    summary="更新退回台账记录（飞书）",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_update_return_ledger(
    record_id: str,
    data: dict[str, Any],
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    await _assert_quality_edit_scope(db, current_user)
    result = await update_return_ledger_record(db, record_id, data)
    return success_response(data=result)


@router.delete(
    "/return-ledger/{record_id}",
    summary="删除退回台账记录（飞书）",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_delete_return_ledger(
    record_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    await _assert_quality_edit_scope(db, current_user)
    await delete_return_ledger_record(db, record_id)
    return success_response(message="已删除")


@router.post(
    "/return-ledger/pull",
    summary="拉取退回台账记录（飞书->本地）",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_pull_return_ledger(
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    result = await pull_return_ledger_records(db)
    return success_response(data=result)
