"""Authorization letter API routes."""

import json
import logging
import shutil
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import NotFoundException
from app.core.response import paginated_response, success_response
from app.core.upload_security import read_upload_secure
from app.modules.registration.api._common import require_user as _require_user
from app.modules.registration.schemas import (
    AuthorizationFdaEntryCreate,
    AuthorizationFdaEntryUpdate,
    AuthorizationFdaRecord,
    AuthorizationLedgerMainCreate,
    AuthorizationLedgerMainRead,
    AuthorizationLedgerMainUpdate,
    AuthorizationLedgerUpdateCreate,
    AuthorizationLedgerUpdateRead,
    AuthorizationLedgerUpdateUpdate,
    AuthorizationLetterCreate,
    AuthorizationLetterListItem,
    AuthorizationLetterResponse,
    AuthorizationMaterialListItem,
    AuthorizationOverview,
    AuthorizationProductDetail,
    ProductInfo,
)
from app.modules.registration.service import AuthorizationLetterService
from app.shared.schemas import ApiResponseEnvelope, PageParams

logger = logging.getLogger(__name__)

router = APIRouter()


def get_service(session: AsyncSession = Depends(get_db)) -> AuthorizationLetterService:
    return AuthorizationLetterService(session)


def _cleanup_export_dir(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)


@router.get(
    "/products",
    summary="获取授权书产品列表",
    response_model=ApiResponseEnvelope[list[ProductInfo]],
)
async def list_products(
    current_user: CurrentUser,
    service: AuthorizationLetterService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    products = await service.get_product_list()
    return success_response(data=products)


@router.get(
    "/overview",
    summary="获取授权书内容总览",
    response_model=ApiResponseEnvelope[AuthorizationOverview],
)
async def get_authorization_overview(
    current_user: CurrentUser,
    service: AuthorizationLetterService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    overview = await service.get_overview()
    return success_response(data=overview)


@router.get(
    "/products/{product_name}",
    summary="获取单个产品的授权书详情",
    response_model=ApiResponseEnvelope[AuthorizationProductDetail],
)
async def get_product_detail(
    product_name: str,
    current_user: CurrentUser,
    service: AuthorizationLetterService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    detail = await service.get_product_detail(product_name)
    return success_response(data=detail)


@router.get(
    "/fda",
    summary="获取 FDA 授权记录",
    response_model=ApiResponseEnvelope[list[AuthorizationFdaRecord]],
)
async def list_authorization_fda(
    current_user: CurrentUser,
    product_name: str | None = Query(None, description="产品名称"),
    keyword: str | None = Query(None, description="关键词"),
    service: AuthorizationLetterService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    records = await service.list_fda_entries(product_name=product_name, keyword=keyword)
    return success_response(data=records)


@router.get("/fda/export", summary="导出 FDA 授权 Word")
async def export_authorization_fda(
    current_user: CurrentUser,
    product_name: str | None = Query(None, description="产品名称"),
    keyword: str | None = Query(None, description="关键词"),
    service: AuthorizationLetterService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    artifact = await service.export_fda_entries(
        product_name=product_name, keyword=keyword
    )
    return FileResponse(
        path=str(artifact.file_path),
        filename=artifact.download_name,
        media_type="application/octet-stream",
        background=BackgroundTask(_cleanup_export_dir, str(artifact.temp_dir)),
    )


@router.post(
    "/fda",
    summary="创建 FDA 授权记录",
    response_model=ApiResponseEnvelope[AuthorizationFdaRecord],
)
async def create_authorization_fda_entry(
    payload: AuthorizationFdaEntryCreate,
    current_user: CurrentUser,
    service: AuthorizationLetterService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    record = await service.create_fda_entry(payload)
    return success_response(data=record, message="创建成功", status_code=201)


@router.put(
    "/fda/{entry_id}",
    summary="更新 FDA 授权记录",
    response_model=ApiResponseEnvelope[AuthorizationFdaRecord],
)
async def update_authorization_fda_entry(
    entry_id: UUID,
    payload: AuthorizationFdaEntryUpdate,
    current_user: CurrentUser,
    service: AuthorizationLetterService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    record = await service.update_fda_entry(entry_id, payload)
    return success_response(data=record, message="更新成功")


@router.delete("/fda/{entry_id}", summary="删除 FDA 授权记录")
async def delete_authorization_fda_entry(
    entry_id: UUID,
    current_user: CurrentUser,
    service: AuthorizationLetterService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    await service.delete_fda_entry(entry_id)
    return success_response(message="删除成功")


@router.get(
    "/ledger",
    summary="获取授权书台账",
    response_model=ApiResponseEnvelope[list[AuthorizationLedgerMainRead]],
)
async def list_authorization_ledger(
    current_user: CurrentUser,
    product_name: str | None = Query(None, description="产品名称"),
    market_name: str | None = Query(None, description="市场/地区"),
    status: str | None = Query(None, description="授权状态"),
    keyword: str | None = Query(None, description="关键词"),
    service: AuthorizationLetterService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    records, overview = await service.list_grouped_ledger_mains(
        product_name=product_name,
        market_name=market_name,
        status=status,
        keyword=keyword,
    )
    return success_response(
        data=records,
        meta={"summary": overview},
    )


@router.get("/ledger/export", summary="导出市场授权 Word")
async def export_authorization_ledger(
    current_user: CurrentUser,
    product_name: str | None = Query(None, description="产品名称"),
    market_name: str | None = Query(None, description="市场/地区"),
    status: str | None = Query(None, description="授权状态"),
    keyword: str | None = Query(None, description="关键词"),
    service: AuthorizationLetterService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    artifact = await service.export_ledger_entries(
        product_name=product_name,
        market_name=market_name,
        status=status,
        keyword=keyword,
    )
    return FileResponse(
        path=str(artifact.file_path),
        filename=artifact.download_name,
        media_type="application/octet-stream",
        background=BackgroundTask(_cleanup_export_dir, str(artifact.temp_dir)),
    )


@router.post(
    "/ledger/mains",
    summary="创建市场授权主记录",
    response_model=ApiResponseEnvelope[AuthorizationLedgerMainRead],
)
async def create_authorization_ledger_main(
    payload: AuthorizationLedgerMainCreate,
    current_user: CurrentUser,
    service: AuthorizationLetterService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    record = await service.create_ledger_main(payload)
    return success_response(data=record, message="创建成功", status_code=201)


@router.post(
    "/ledger/mains/{main_id}/updates",
    summary="创建市场授权更新子行",
    response_model=ApiResponseEnvelope[AuthorizationLedgerUpdateRead],
)
async def create_authorization_ledger_update(
    main_id: UUID,
    payload: AuthorizationLedgerUpdateCreate,
    current_user: CurrentUser,
    service: AuthorizationLetterService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    record = await service.create_ledger_update(main_id, payload)
    return success_response(data=record, message="创建成功", status_code=201)


@router.patch(
    "/ledger/mains/{main_id}",
    summary="编辑市场授权主记录",
    response_model=ApiResponseEnvelope[AuthorizationLedgerMainRead],
)
async def update_authorization_ledger_main(
    main_id: UUID,
    payload: AuthorizationLedgerMainUpdate,
    current_user: CurrentUser,
    service: AuthorizationLetterService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    record = await service.update_ledger_main(main_id, payload)
    return success_response(data=record, message="更新成功")


@router.patch(
    "/ledger/updates/{update_id}",
    summary="编辑市场授权更新子行",
    response_model=ApiResponseEnvelope[AuthorizationLedgerUpdateRead],
)
async def update_authorization_ledger_update(
    update_id: UUID,
    payload: AuthorizationLedgerUpdateUpdate,
    current_user: CurrentUser,
    service: AuthorizationLetterService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    record = await service.update_ledger_update(update_id, payload)
    return success_response(data=record, message="更新成功")


@router.delete("/ledger/mains/{main_id}", summary="删除市场授权主记录")
async def delete_authorization_ledger_main(
    main_id: UUID,
    current_user: CurrentUser,
    service: AuthorizationLetterService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    await service.delete_ledger_main(main_id)
    return success_response(message="删除成功")


@router.delete("/ledger/updates/{update_id}", summary="删除市场授权更新子行")
async def delete_authorization_ledger_update(
    update_id: UUID,
    current_user: CurrentUser,
    service: AuthorizationLetterService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    await service.delete_ledger_update(update_id)
    return success_response(message="删除成功")


@router.get(
    "/materials",
    summary="按本地目录获取授权书资料列表",
    response_model=ApiResponseEnvelope[list[AuthorizationMaterialListItem]],
)
async def list_authorization_materials(
    current_user: CurrentUser,
    product_name: str | None = Query(None, description="产品名称搜索"),
    category: str | None = Query(None, description="资料类别筛选"),
    scope: Literal["all", "fda", "non_fda"] = Query("all", description="资料范围"),
    page_params: PageParams = Depends(),
    service: AuthorizationLetterService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    is_fda: bool | None = None
    if scope == "fda":
        is_fda = True
    elif scope == "non_fda":
        is_fda = False

    materials, total, summary = await service.list_materials(
        product_name=product_name,
        category=category,
        is_fda=is_fda,
        page=page_params.page,
        page_size=page_params.page_size,
    )
    return success_response(
        data=materials,
        meta={
            "page": page_params.page,
            "page_size": page_params.page_size,
            "total": total,
            "summary": summary,
        },
    )


@router.get("/materials/download", summary="下载本地授权书资料")
async def download_authorization_material(
    current_user: CurrentUser,
    file_key: str = Query(..., description="授权书资料相对路径"),
    service: AuthorizationLetterService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    file_path = service.get_material_file_path(file_key)
    media_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if file_path.suffix.lower() == ".docx"
        else "application/msword"
    )
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type=media_type,
    )


@router.get(
    "",
    summary="授权书生成记录列表",
    response_model=ApiResponseEnvelope[list[AuthorizationLetterListItem]],
)
async def list_authorization_letters(
    current_user: CurrentUser,
    product_name: str | None = Query(None, description="产品名称搜索"),
    preparation_unit: str | None = Query(None, description="制剂单位搜索"),
    page_params: PageParams = Depends(),
    service: AuthorizationLetterService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    letters, total = await service.list_letters(
        product_name=product_name,
        preparation_unit=preparation_unit,
        page=page_params.page,
        page_size=page_params.page_size,
    )
    return paginated_response(
        data=letters,
        page=page_params.page,
        page_size=page_params.page_size,
        total=total,
    )


@router.post(
    "/generate",
    summary="生成授权书",
    response_model=ApiResponseEnvelope[AuthorizationLetterResponse],
)
async def generate_authorization_letter(
    template: UploadFile,
    current_user: CurrentUser,
    product_name: str = Form(..., description="产品名称"),
    registration_number: str = Form(..., description="登记号"),
    preparation_unit: str = Form(..., description="制剂单位名称"),
    preparation_name: str = Form(..., description="制剂名称"),
    administration_route: str = Form(..., description="给药途径"),
    remarks: str | None = Form(None, description="备注"),
    replacements: str | None = Form(
        None,
        description='替换规则 JSON，格式: [{"old": "原文本", "new": "新文本"}]',
    ),
    service: AuthorizationLetterService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    template_file_name, template_data = await read_upload_secure(
        template,
        max_bytes=get_settings().MAX_UPLOAD_SIZE_MB * 1024 * 1024,
        allowed_extensions={".doc", ".docx"},
        what="授权书模板",
    )

    template_placeholders = None
    if replacements:
        try:
            rules = json.loads(replacements)
            template_placeholders = {r["old"]: r["new"] for r in rules}
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("解析 replacements JSON 失败，将忽略替换规则: %s", e)

    data = AuthorizationLetterCreate(
        product_name=product_name,
        registration_number=registration_number,
        preparation_unit=preparation_unit,
        preparation_name=preparation_name,
        administration_route=administration_route,
        remarks=remarks,
    )

    letter = await service.generate_letter(
        data=data,
        template_data=template_data,
        template_file_name=template_file_name,
        template_placeholders=template_placeholders,
    )
    return success_response(data=letter, message="授权书生成成功", status_code=201)


@router.get(
    "/{letter_id}",
    summary="授权书记录详情",
    response_model=ApiResponseEnvelope[AuthorizationLetterResponse],
)
async def get_authorization_letter(
    letter_id: UUID,
    current_user: CurrentUser,
    service: AuthorizationLetterService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    letter = await service.get_letter(letter_id)
    return success_response(data=letter)


@router.get("/{letter_id}/download", summary="下载生成的授权书文件")
async def download_authorization_letter(
    letter_id: UUID,
    current_user: CurrentUser,
    service: AuthorizationLetterService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    letter_model = await service.get_letter_model(letter_id)
    if not letter_model:
        raise NotFoundException("授权书记录", str(letter_id))

    file_path = service.get_output_file_path(letter_model)
    if not file_path.exists():
        raise NotFoundException("授权书文件")

    return FileResponse(
        path=str(file_path),
        filename=letter_model.output_file_name,
        media_type="application/msword",
    )


@router.delete("/{letter_id}", summary="删除授权书记录")
async def delete_authorization_letter(
    letter_id: UUID,
    current_user: CurrentUser,
    service: AuthorizationLetterService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    await service.delete_letter(letter_id)
    return success_response(message="授权书记录删除成功")
