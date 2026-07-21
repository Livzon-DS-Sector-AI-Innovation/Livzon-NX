"""CPV Import API routes."""

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.response import paginated_response, success_response
from app.modules.quality import service
from app.modules.quality.schemas import (
    CpvImportConfirmRequest,
    CpvImportPreviewResponse,
    CpvImportTaskResponse,
)

router = APIRouter()


@router.post("/import/preview", summary="上传Excel预览")
async def preview_import(
    file: UploadFile = File(...),
    product_id: uuid.UUID = Query(..., description="产品ID"),
    data_type: str = Query(..., description="数据类型: CPP/CQA"),
    import_mode: str = Query("create", description="导入模式: create/update/overwrite"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """上传Excel文件并预览导入数据"""
    if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
        return JSONResponse(
            status_code=400,
            content={"code": 400, "message": "请上传 Excel 文件 (.xlsx, .xls)"},
        )
    
    file_content = await file.read()
    
    preview = await service.preview_import(
        db, file_content, product_id, data_type, import_mode
    )
    
    return success_response(data=preview.model_dump())


@router.post("/import/confirm", summary="确认导入")
async def confirm_import(
    file: UploadFile = File(...),
    product_id: uuid.UUID = Form(..., description="产品ID"),
    data_type: str = Form(..., description="数据类型: CPP/CQA"),
    import_mode: str = Form("create", description="导入模式: create/update/overwrite"),
    file_name: str = Form(..., description="文件名"),
    skip_errors: bool = Form(False, description="跳过错误行"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    """确认导入Excel数据"""
    file_content = await file.read()
    
    current_user_id = None
    if current_user:
        current_user_id = current_user.id
    
    request = CpvImportConfirmRequest(
        product_id=product_id,
        data_type=data_type,
        import_mode=import_mode,
        file_name=file_name,
        skip_errors=skip_errors
    )
    
    task = await service.confirm_import(db, file_content, request, current_user_id)
    
    return success_response(data=task.model_dump())


@router.get("/import/tasks", summary="获取导入任务列表")
async def get_import_tasks(
    product_id: uuid.UUID | None = Query(None, description="产品ID"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=200, description="每页数量"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """获取导入任务列表"""
    tasks, total = await service.get_import_tasks(db, product_id, page, page_size)
    return paginated_response(
        data=[t.model_dump() for t in tasks],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/import/tasks/{task_id}", summary="获取导入任务详情")
async def get_import_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """获取导入任务详情"""
    task = await service.get_import_task_by_id(db, task_id)
    return success_response(data=task.model_dump())
