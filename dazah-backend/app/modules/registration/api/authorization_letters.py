"""Authorization letter API routes."""

import json
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import NotFoundException
from app.core.response import paginated_response, success_response
from app.modules.registration.schemas import AuthorizationLetterCreate
from app.modules.registration.service import AuthorizationLetterService
from app.shared.schemas import PageParams

router = APIRouter()


def get_service(session: AsyncSession = Depends(get_db)) -> AuthorizationLetterService:
    return AuthorizationLetterService(session)


@router.get("/products", summary="获取品种登记号对照表")
async def list_products(service: AuthorizationLetterService = Depends(get_service)):
    products = service.get_product_list()
    return success_response(data=[p.model_dump() for p in products])


@router.get("", summary="授权书生成记录列表")
async def list_authorization_letters(
    product_name: str | None = Query(None, description="产品名称搜索"),
    preparation_unit: str | None = Query(None, description="制剂单位搜索"),
    page_params: PageParams = Depends(),
    service: AuthorizationLetterService = Depends(get_service),
):
    letters, total = await service.list_letters(
        product_name=product_name,
        preparation_unit=preparation_unit,
        page=page_params.page,
        page_size=page_params.page_size,
    )
    data = [letter.model_dump(mode="json") for letter in letters]
    return paginated_response(
        data=data,
        page=page_params.page,
        page_size=page_params.page_size,
        total=total,
    )


@router.post("/generate", summary="生成授权书")
async def generate_authorization_letter(
    template: UploadFile,
    product_name: str = Form(..., description="产品名称"),
    registration_number: str = Form(..., description="登记号"),
    preparation_unit: str = Form(..., description="制剂单位名称"),
    preparation_name: str = Form(..., description="制剂名称"),
    administration_route: str = Form(..., description="给药途径"),
    remarks: str | None = Form(None, description="备注"),
    replacements: str | None = Form(
        None,
        description="替换规则 JSON，格式: [{\"old\": \"原文本\", \"new\": \"新文本\"}]",
    ),
    service: AuthorizationLetterService = Depends(get_service),
):
    template_data = await template.read()
    template_file_name = template.filename or "模板.doc"

    template_placeholders = None
    if replacements:
        try:
            rules = json.loads(replacements)
            template_placeholders = {r["old"]: r["new"] for r in rules}
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

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
    return success_response(data=letter.model_dump(mode="json"), message="授权书生成成功", status_code=201)


@router.get("/{letter_id}", summary="授权书记录详情")
async def get_authorization_letter(
    letter_id: UUID,
    service: AuthorizationLetterService = Depends(get_service),
):
    letter = await service.get_letter(letter_id)
    return success_response(data=letter.model_dump(mode="json"))


@router.get("/{letter_id}/download", summary="下载生成的授权书文件")
async def download_authorization_letter(
    letter_id: UUID,
    service: AuthorizationLetterService = Depends(get_service),
):
    letter_model = await service.repo.get_by_id(letter_id)
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
    service: AuthorizationLetterService = Depends(get_service),
):
    await service.delete_letter(letter_id)
    return success_response(message="授权书记录删除成功")
