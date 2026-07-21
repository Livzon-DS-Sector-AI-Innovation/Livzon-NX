"""对照物质说明表 API 路由"""

from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import NotFoundException
from app.core.response import paginated_response, success_response
from app.modules.registration.service import ReferenceStandardService
from app.shared.schemas import PageParams

router = APIRouter()


def get_service(session: AsyncSession = Depends(get_db)) -> ReferenceStandardService:
    return ReferenceStandardService(session)


@router.post("/parse-coa", summary="解析COA文件提取信息")
async def parse_coa_file(
    coa: UploadFile,
):
    """解析COA PDF文件，自动提取关键信息"""
    coa_data = await coa.read()
    
    from app.modules.registration.reference_standard_generator import parse_coa
    
    result = parse_coa(coa_data)
    
    return success_response(
        data=result,
        message="COA解析成功",
    )


@router.post("/generate", summary="生成对照物质说明表")
async def generate_reference_standard(
    coa: UploadFile,
    drug_name: str = Form(..., description="药品名称"),
    reference_substance_name: str | None = Form(None, description="对照物质名称"),
    batch_number: str | None = Form(None, description="批号"),
    manufacturer: str | None = Form(None, description="生产厂家"),
    english_name: str | None = Form(None, description="英文名"),
    molecular_formula: str | None = Form(None, description="分子式"),
    molecular_weight: str | None = Form(None, description="分子量"),
    cas_number: str | None = Form(None, description="CAS号"),
    content: str | None = Form(None, description="含量"),
    moisture: str | None = Form(None, description="水分/干燥失重"),
    rsd: str | None = Form(None, description="RSD"),
    expiration_date: str | None = Form(None, description="有效期"),
    storage_condition: str | None = Form(None, description="贮存条件"),
    remarks: str | None = Form(None, description="备注"),
    service: ReferenceStandardService = Depends(get_service),
):
    coa_data = await coa.read()
    coa_file_name = coa.filename or "COA.pdf"

    record = await service.generate_document(
        coa_data=coa_data,
        coa_file_name=coa_file_name,
        drug_name=drug_name,
        reference_substance_name=reference_substance_name,
        batch_number=batch_number,
        manufacturer=manufacturer,
        english_name=english_name,
        molecular_formula=molecular_formula,
        molecular_weight=molecular_weight,
        cas_number=cas_number,
        content=content,
        moisture=moisture,
        rsd=rsd,
        expiration_date=expiration_date,
        storage_condition=storage_condition,
        remarks=remarks,
    )
    return success_response(
        data=record.model_dump(mode="json"),
        message="对照物质说明表生成成功",
        status_code=201,
    )


@router.get("", summary="对照物质说明表记录列表")
async def list_reference_standards(
    drug_name: str | None = Query(None, description="药品名称搜索"),
    page_params: PageParams = Depends(),
    service: ReferenceStandardService = Depends(get_service),
):
    records, total = await service.list_records(
        drug_name=drug_name,
        page=page_params.page,
        page_size=page_params.page_size,
    )
    data = [r.model_dump(mode="json") for r in records]
    return paginated_response(
        data=data,
        page=page_params.page,
        page_size=page_params.page_size,
        total=total,
    )


@router.get("/{record_id}", summary="对照物质说明表记录详情")
async def get_reference_standard(
    record_id: UUID,
    service: ReferenceStandardService = Depends(get_service),
):
    record = await service.get_record(record_id)
    return success_response(data=record.model_dump(mode="json"))


@router.get("/{record_id}/download", summary="下载生成的说明表文件")
async def download_reference_standard(
    record_id: UUID,
    service: ReferenceStandardService = Depends(get_service),
):
    record_model = await service.repo.get_by_id(record_id)
    if not record_model:
        raise NotFoundException("对照物质说明表记录", str(record_id))

    file_path = service.get_output_file_path(record_model)
    if not file_path.exists():
        raise NotFoundException("说明表文件")

    return FileResponse(
        path=str(file_path),
        filename=record_model.output_file_name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.delete("/{record_id}", summary="删除对照物质说明表记录")
async def delete_reference_standard(
    record_id: UUID,
    service: ReferenceStandardService = Depends(get_service),
):
    await service.delete_record(record_id)
    return success_response(message="对照物质说明表记录删除成功")
