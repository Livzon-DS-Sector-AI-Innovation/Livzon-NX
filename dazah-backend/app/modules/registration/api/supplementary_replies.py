"""Supplementary reply API routes."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import NotFoundException
from app.core.response import paginated_response, success_response
from app.core.upload_security import read_upload_secure
from app.modules.registration.service import SupplementaryReplyService
from app.shared.schemas import PageParams

router = APIRouter()


def get_service(session: AsyncSession = Depends(get_db)) -> SupplementaryReplyService:
    return SupplementaryReplyService(session)


@router.post("/generate", summary="生成发补回复文档")
async def generate_supplementary_reply(
    notice: UploadFile,
    template: UploadFile | None = None,
    drug_name: str | None = Form(None, description="药品名称（可选，默认从PDF提取）"),
    registration_number: str | None = Form(None, description="登记号（可选）"),
    acceptance_number: str | None = Form(None, description="受理号（可选）"),
    company_name: str | None = Form(None, description="申请人/公司名称（可选）"),
    remarks: str | None = Form(None, description="备注"),
    service: SupplementaryReplyService = Depends(get_service),
) -> Any:
    notice_file_name, notice_data = await read_upload_secure(
        notice,
        max_bytes=get_settings().MAX_UPLOAD_SIZE_MB * 1024 * 1024,
        allowed_extensions={".pdf"},
        what="CDE通知函",
    )

    template_data = None
    template_file_name = None
    if template:
        template_file_name, template_data = await read_upload_secure(
            template,
            max_bytes=get_settings().MAX_UPLOAD_SIZE_MB * 1024 * 1024,
            allowed_extensions={".doc", ".docx"},
            what="发补回复模板",
        )

    reply = await service.generate_reply(
        notice_data=notice_data,
        notice_file_name=notice_file_name,
        template_data=template_data,
        template_file_name=template_file_name,
        drug_name_override=drug_name,
        registration_number_override=registration_number,
        acceptance_number_override=acceptance_number,
        company_name_override=company_name,
        remarks=remarks,
    )
    return success_response(
        data=reply.model_dump(mode="json"),
        message="发补回复文档生成成功",
        status_code=201,
    )


@router.get("", summary="发补回复记录列表")
async def list_supplementary_replies(
    drug_name: str | None = Query(None, description="药品名称搜索"),
    page_params: PageParams = Depends(),
    service: SupplementaryReplyService = Depends(get_service),
) -> Any:
    replies, total = await service.list_replies(
        drug_name=drug_name,
        page=page_params.page,
        page_size=page_params.page_size,
    )
    data = [reply.model_dump(mode="json") for reply in replies]
    return paginated_response(
        data=data,
        page=page_params.page,
        page_size=page_params.page_size,
        total=total,
    )


@router.get("/{reply_id}", summary="发补回复记录详情")
async def get_supplementary_reply(
    reply_id: UUID,
    service: SupplementaryReplyService = Depends(get_service),
) -> Any:
    reply = await service.get_reply(reply_id)
    return success_response(data=reply.model_dump(mode="json"))


@router.get("/{reply_id}/download", summary="下载生成的发补回复文件")
async def download_supplementary_reply(
    reply_id: UUID,
    service: SupplementaryReplyService = Depends(get_service),
) -> Any:
    reply_model = await service.repo.get_by_id(reply_id)
    if not reply_model:
        raise NotFoundException("发补回复记录", str(reply_id))

    file_path = service.get_output_file_path(reply_model)
    if not file_path.exists():
        raise NotFoundException("发补回复文件")

    return FileResponse(
        path=str(file_path),
        filename=reply_model.output_file_name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.delete("/{reply_id}", summary="删除发补回复记录")
async def delete_supplementary_reply(
    reply_id: UUID,
    service: SupplementaryReplyService = Depends(get_service),
) -> Any:
    await service.delete_reply(reply_id)
    return success_response(message="发补回复记录删除成功")
