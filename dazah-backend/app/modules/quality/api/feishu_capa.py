"""Feishu native CAPA API endpoints — direct bitable CRUD."""

import logging
import traceback
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import error_response, paginated_response, success_response
from app.modules.quality.service.feishu_capa import (
    create_capa_ledger_record,
    create_capa_plan_track_record,
    delete_capa_ledger_record,
    delete_capa_plan_track_record,
    get_capa_ledger_record,
    get_capa_plan_track_record,
    list_capa_ledger,
    list_capa_plan_tracks,
    update_capa_ledger_record,
    update_capa_plan_track_record,
)
from app.modules.quality.service.feishu_capa_export import generate_capa_export_docx

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feishu")

# ══════════════════════════════════════════════
#  CAPA 台账
# ══════════════════════════════════════════════


@router.get("/capas", summary="获取飞书CAPA台账列表")
async def api_list_capa_ledger(
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await list_capa_ledger(db, keyword=keyword, page=page, page_size=page_size)
        return paginated_response(
            data=result["items"],
            page=result["page"],
            page_size=result["page_size"],
            total=result["total"],
        )
    except ValueError as e:
        return error_response(message=str(e), status_code=400)


@router.get("/capas/export", summary="导出CAPA台账为Word文档")
async def api_export_capa_ledger(
    keyword: str | None = Query(None),
    department: str | None = Query(None),
    product: str | None = Query(None),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await list_capa_ledger(
            db,
            keyword=keyword,
            department=department,
            product=product,
            status=status,
            page=1,
            page_size=1000,
        )
        docx_bytes = generate_capa_export_docx(result["items"])
        filename = "CAPA登记汇总表.docx"
        encoded = quote(filename)
        return StreamingResponse(
            BytesIO(docx_bytes),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=capa-ledger.docx; filename*=UTF-8''{encoded}"
                )
            },
        )
    except Exception as e:
        logger.exception("CAPA export failed")
        return error_response(message=str(e), status_code=500)


@router.get("/capas/{record_id}", summary="获取飞书CAPA台账详情")
async def api_get_capa_ledger_record(
    record_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await get_capa_ledger_record(db, record_id)
        return success_response(data=result)
    except ValueError as e:
        return error_response(message=str(e), status_code=404)


@router.post("/capas", summary="创建飞书CAPA台账记录")
async def api_create_capa_ledger_record(
    data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await create_capa_ledger_record(db, data)
        return success_response(data=result, message="创建成功")
    except ValueError as e:
        return error_response(message=str(e), status_code=400)


@router.put("/capas/{record_id}", summary="更新飞书CAPA台账记录")
async def api_update_capa_ledger_record(
    record_id: str,
    data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await update_capa_ledger_record(db, record_id, data)
        return success_response(data=result, message="更新成功")
    except ValueError as e:
        detail = str(e)
        status_code = 404 if "不存在" in detail else 400
        return error_response(message=detail, status_code=status_code)


@router.delete("/capas/{record_id}", summary="删除飞书CAPA台账记录")
async def api_delete_capa_ledger_record(
    record_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        await delete_capa_ledger_record(db, record_id)
        return success_response(data={"success": True}, message="删除成功")
    except ValueError as e:
        return error_response(message=str(e), status_code=400)


# ══════════════════════════════════════════════
#  CAPA 计划跟踪
# ══════════════════════════════════════════════


@router.get("/capa-plan-tracks", summary="获取飞书CAPA计划跟踪列表")
async def api_list_capa_plan_tracks(
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await list_capa_plan_tracks(db, keyword=keyword, page=page, page_size=page_size)
        return paginated_response(
            data=result["items"],
            page=result["page"],
            page_size=result["page_size"],
            total=result["total"],
        )
    except ValueError as e:
        return error_response(message=str(e), status_code=400)


@router.get("/capa-plan-tracks/{record_id}", summary="获取飞书CAPA计划跟踪详情")
async def api_get_capa_plan_track_record(
    record_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await get_capa_plan_track_record(db, record_id)
        return success_response(data=result)
    except ValueError as e:
        return error_response(message=str(e), status_code=404)


@router.post("/capa-plan-tracks", summary="创建飞书CAPA计划跟踪记录")
async def api_create_capa_plan_track_record(
    data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await create_capa_plan_track_record(db, data)
        return success_response(data=result, message="创建成功")
    except ValueError as e:
        return error_response(message=str(e), status_code=400)


@router.put("/capa-plan-tracks/{record_id}", summary="更新飞书CAPA计划跟踪记录")
async def api_update_capa_plan_track_record(
    record_id: str,
    data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await update_capa_plan_track_record(db, record_id, data)
        return success_response(data=result, message="更新成功")
    except ValueError as e:
        detail = str(e)
        status_code = 404 if "不存在" in detail else 400
        return error_response(message=detail, status_code=status_code)


@router.delete("/capa-plan-tracks/{record_id}", summary="删除飞书CAPA计划跟踪记录")
async def api_delete_capa_plan_track_record(
    record_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        await delete_capa_plan_track_record(db, record_id)
        return success_response(data={"success": True}, message="删除成功")
    except ValueError as e:
        return error_response(message=str(e), status_code=400)
