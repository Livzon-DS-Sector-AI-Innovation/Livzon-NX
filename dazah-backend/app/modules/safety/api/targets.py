"""Safety API — 目标责任与绩效端点。

年度安全目标台账 + 考核期进度记录 + 安全目标责任书签订台账 +
安全生产责任制季度考核，支持按年份/部门/状态/等级检索，
统计接口输出部门目标达成、签订率与考核等级分布。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.exceptions import AppException, NotFoundException
from app.modules.safety.schemas.targets import (
    SafetyAgreementImportResultResponse,
    SafetyDutyAssessmentCreate,
    SafetyDutyAssessmentImportResultResponse,
    SafetyDutyAssessmentListResponse,
    SafetyDutyAssessmentResponse,
    SafetyDutyAssessmentStatsResponse,
    SafetyDutyAssessmentUpdate,
    SafetyDutyTemplateResponse,
    SafetyTargetAgreementCreate,
    SafetyTargetAgreementListResponse,
    SafetyTargetAgreementResponse,
    SafetyTargetAgreementStatsResponse,
    SafetyTargetAgreementUpdate,
    SafetyTargetCreate,
    SafetyTargetListResponse,
    SafetyTargetRecordCreate,
    SafetyTargetRecordResponse,
    SafetyTargetRecordUpdate,
    SafetyTargetResponse,
    SafetyTargetStatsResponse,
    SafetyTargetUpdate,
)
from app.modules.safety.service.target import (
    SafetyDutyAssessmentService,
    SafetyTargetAgreementService,
    SafetyTargetService,
    find_assessment_template,
)
from app.modules.safety.service.target_import import (
    AgreementImportService,
    DutyAssessmentImportService,
    build_agreement_template,
    build_assessment_template,
    parse_agreement_template,
    parse_assessment_template,
)
from app.shared.schemas import ApiResponseEnvelope

safety_targets_router = APIRouter()

_XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


@safety_targets_router.get(
    "/safety-targets",
    response_model=ApiResponseEnvelope[SafetyTargetListResponse],
    summary="安全目标分页列表（年份/类别/部门/状态/关键字）",
)
async def list_safety_targets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    year: int | None = Query(None, description="目标年度"),
    category: str | None = Query(None, description="目标类别"),
    department: str | None = Query(None, description="责任部门"),
    status: str | None = Query(
        None, description="状态: in_progress/achieved/not_achieved"
    ),
    keyword: str | None = Query(None, description="目标名称/指标关键字"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyTargetListResponse]:
    service = SafetyTargetService(db)
    items, total = await service.list_targets(
        page=page,
        page_size=page_size,
        year=year,
        category=category,
        department=department,
        status=status,
        keyword=keyword,
    )
    return ApiResponseEnvelope(
        data=SafetyTargetListResponse(
            items=[SafetyTargetResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@safety_targets_router.get(
    "/safety-targets/stats",
    response_model=ApiResponseEnvelope[SafetyTargetStatsResponse],
    summary="安全目标统计（部门达成情况）",
)
async def get_safety_target_stats(
    year: int | None = Query(None, description="目标年度"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyTargetStatsResponse]:
    service = SafetyTargetService(db)
    return ApiResponseEnvelope(data=await service.get_stats(year=year))


@safety_targets_router.get(
    "/safety-targets/{target_id}",
    response_model=ApiResponseEnvelope[SafetyTargetResponse],
    summary="安全目标详情（含进度记录）",
)
async def get_safety_target(
    target_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyTargetResponse]:
    service = SafetyTargetService(db)
    target = await service.get_target(target_id)
    if target is None:
        raise NotFoundException("安全目标")
    return ApiResponseEnvelope(data=SafetyTargetResponse.model_validate(target))


@safety_targets_router.post(
    "/safety-targets",
    response_model=ApiResponseEnvelope[SafetyTargetResponse],
    summary="新增安全目标",
)
async def create_safety_target(
    data: SafetyTargetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyTargetResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = SafetyTargetService(db)
    target = await service.create_target(data, user_id=current_user.id)
    await db.commit()
    await db.refresh(target)
    return ApiResponseEnvelope(data=SafetyTargetResponse.model_validate(target))


@safety_targets_router.put(
    "/safety-targets/{target_id}",
    response_model=ApiResponseEnvelope[SafetyTargetResponse],
    summary="更新安全目标",
)
async def update_safety_target(
    target_id: UUID,
    data: SafetyTargetUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyTargetResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = SafetyTargetService(db)
    target = await service.update_target(target_id, data, user_id=current_user.id)
    await db.commit()
    await db.refresh(target)
    return ApiResponseEnvelope(data=SafetyTargetResponse.model_validate(target))


@safety_targets_router.delete(
    "/safety-targets/{target_id}",
    response_model=ApiResponseEnvelope[None],
    summary="删除安全目标（软删除）",
)
async def delete_safety_target(
    target_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[None]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = SafetyTargetService(db)
    deleted = await service.delete_target(target_id)
    if not deleted:
        raise NotFoundException("安全目标")
    await db.commit()
    return ApiResponseEnvelope(data=None, message="删除成功")


@safety_targets_router.put(
    "/safety-targets/{target_id}/records/{period}",
    response_model=ApiResponseEnvelope[SafetyTargetRecordResponse],
    summary="录入/更新目标进度（按考核期 upsert 语义：存在即更新）",
)
async def upsert_safety_target_record(
    target_id: UUID,
    period: str,
    data: SafetyTargetRecordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyTargetRecordResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = SafetyTargetService(db)
    existing = await service.get_record(target_id, period)
    if existing is None:
        create_data = SafetyTargetRecordCreate(
            period=period,
            actual_value=data.actual_value or "",
            completion_pct=data.completion_pct,
            note=data.note or "",
        )
        record = await service.create_record(
            target_id, create_data, user_id=current_user.id
        )
    else:
        record = await service.update_record(
            target_id, period, data, user_id=current_user.id
        )
    await db.commit()
    await db.refresh(record)
    return ApiResponseEnvelope(data=SafetyTargetRecordResponse.model_validate(record))


@safety_targets_router.delete(
    "/safety-targets/{target_id}/records/{period}",
    response_model=ApiResponseEnvelope[None],
    summary="删除目标进度记录（软删除）",
)
async def delete_safety_target_record(
    target_id: UUID,
    period: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[None]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = SafetyTargetService(db)
    deleted = await service.delete_record(target_id, period)
    if not deleted:
        raise NotFoundException("进度记录")
    await db.commit()
    return ApiResponseEnvelope(data=None, message="删除成功")


# ==================== 安全目标责任书 ====================


@safety_targets_router.get(
    "/safety-target-agreements",
    response_model=ApiResponseEnvelope[SafetyTargetAgreementListResponse],
    summary="责任书分页列表（年度/部门/分类/状态/关键字）",
)
async def list_safety_target_agreements(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    year: int | None = Query(None, description="签订年度"),
    department: str | None = Query(None, description="责任部门/单位"),
    category: str | None = Query(None, description="分类"),
    status: str | None = Query(None, description="状态: unsigned/signed"),
    keyword: str | None = Query(None, description="部门/岗位/签订人关键字"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyTargetAgreementListResponse]:
    service = SafetyTargetAgreementService(db)
    items, total = await service.list_agreements(
        page=page,
        page_size=page_size,
        year=year,
        department=department,
        category=category,
        status=status,
        keyword=keyword,
    )
    return ApiResponseEnvelope(
        data=SafetyTargetAgreementListResponse(
            items=[
                SafetyTargetAgreementResponse.model_validate(item) for item in items
            ],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@safety_targets_router.get(
    "/safety-target-agreements/stats",
    response_model=ApiResponseEnvelope[SafetyTargetAgreementStatsResponse],
    summary="责任书统计（部门签订情况与签订率）",
)
async def get_safety_target_agreement_stats(
    year: int | None = Query(None, description="签订年度"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyTargetAgreementStatsResponse]:
    service = SafetyTargetAgreementService(db)
    return ApiResponseEnvelope(data=await service.get_stats(year=year))


@safety_targets_router.post(
    "/safety-target-agreements",
    response_model=ApiResponseEnvelope[SafetyTargetAgreementResponse],
    summary="新增责任书记录",
)
async def create_safety_target_agreement(
    data: SafetyTargetAgreementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyTargetAgreementResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = SafetyTargetAgreementService(db)
    agreement = await service.create_agreement(data, user_id=current_user.id)
    await db.commit()
    await db.refresh(agreement)
    return ApiResponseEnvelope(
        data=SafetyTargetAgreementResponse.model_validate(agreement)
    )


@safety_targets_router.get(
    "/safety-target-agreements/import-template",
    summary="下载责任书签订登记导入模板（预填台账目录）",
)
async def download_safety_target_agreement_import_template(
    year: int | None = Query(None, description="限定年度（缺省=全部台账）"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Response:
    service = SafetyTargetAgreementService(db)
    items, _total = await service.list_agreements(page=1, page_size=500, year=year)
    content = build_agreement_template(items)
    return Response(
        content=content,
        media_type=_XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": (
                'attachment; filename="agreement-sign-import-template.xlsx"'
            )
        },
    )


@safety_targets_router.post(
    "/safety-target-agreements/import",
    response_model=ApiResponseEnvelope[SafetyAgreementImportResultResponse],
    summary="批量导入责任书签订登记（存在即更新，缺失则新建）",
)
async def import_safety_target_agreements(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyAgreementImportResultResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    content = await file.read()
    rows = parse_agreement_template(content)
    report = await AgreementImportService(db).commit(rows, user_id=current_user.id)
    await db.commit()
    return ApiResponseEnvelope(
        data=SafetyAgreementImportResultResponse(
            updated=report.updated,
            created=report.created,
            errors=report.errors,
        )
    )


@safety_targets_router.put(
    "/safety-target-agreements/{agreement_id}",
    response_model=ApiResponseEnvelope[SafetyTargetAgreementResponse],
    summary="更新责任书（含签订登记：状态/签订日期/甲乙方）",
)
async def update_safety_target_agreement(
    agreement_id: UUID,
    data: SafetyTargetAgreementUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyTargetAgreementResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = SafetyTargetAgreementService(db)
    agreement = await service.update_agreement(
        agreement_id, data, user_id=current_user.id
    )
    await db.commit()
    await db.refresh(agreement)
    return ApiResponseEnvelope(
        data=SafetyTargetAgreementResponse.model_validate(agreement)
    )


@safety_targets_router.delete(
    "/safety-target-agreements/{agreement_id}",
    response_model=ApiResponseEnvelope[None],
    summary="删除责任书记录（软删除）",
)
async def delete_safety_target_agreement(
    agreement_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[None]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = SafetyTargetAgreementService(db)
    deleted = await service.delete_agreement(agreement_id)
    if not deleted:
        raise NotFoundException("责任书记录")
    await db.commit()
    return ApiResponseEnvelope(data=None, message="删除成功")


# ==================== 安全生产责任制考核 ====================


@safety_targets_router.get(
    "/safety-duty-assessments/template",
    response_model=ApiResponseEnvelope[SafetyDutyTemplateResponse],
    summary="按被考核部门匹配责任制考核模板（2026 考核表文档）",
)
async def get_safety_duty_assessment_template(
    department: str = Query(
        min_length=1, max_length=100, description="被考核部门/单位"
    ),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyDutyTemplateResponse]:
    return ApiResponseEnvelope(data=find_assessment_template(department))


@safety_targets_router.get(
    "/safety-duty-assessments",
    response_model=ApiResponseEnvelope[SafetyDutyAssessmentListResponse],
    summary="责任制考核分页列表（年度/季度/部门/等级/关键字）",
)
async def list_safety_duty_assessments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    year: int | None = Query(None, description="考核年度"),
    quarter: int | None = Query(None, ge=1, le=4, description="考核季度"),
    department: str | None = Query(None, description="被考核部门/单位"),
    grade: str | None = Query(None, description="等级: 优秀/良好/合格/不合格"),
    keyword: str | None = Query(None, description="部门/被考核人/考核单位关键字"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyDutyAssessmentListResponse]:
    service = SafetyDutyAssessmentService(db)
    items, total = await service.list_assessments(
        page=page,
        page_size=page_size,
        year=year,
        quarter=quarter,
        department=department,
        grade=grade,
        keyword=keyword,
    )
    return ApiResponseEnvelope(
        data=SafetyDutyAssessmentListResponse(
            items=[
                SafetyDutyAssessmentResponse.model_validate(item) for item in items
            ],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@safety_targets_router.get(
    "/safety-duty-assessments/stats",
    response_model=ApiResponseEnvelope[SafetyDutyAssessmentStatsResponse],
    summary="责任制考核统计（平均分/等级分布/季度与部门维度）",
)
async def get_safety_duty_assessment_stats(
    year: int | None = Query(None, description="考核年度"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyDutyAssessmentStatsResponse]:
    service = SafetyDutyAssessmentService(db)
    return ApiResponseEnvelope(data=await service.get_stats(year=year))


@safety_targets_router.get(
    "/safety-duty-assessments/import-template",
    summary="下载季度考核批量导入模板（按考核表模板一个部门一个 sheet）",
)
async def download_safety_duty_assessment_import_template(
    year: int = Query(ge=2000, le=2100, description="考核年度"),
    quarter: int = Query(ge=1, le=4, description="考核季度"),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Response:
    content = build_assessment_template(year, quarter)
    return Response(
        content=content,
        media_type=_XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": (
                f'attachment; filename="duty-assessment-{year}-Q{quarter}.xlsx"'
            )
        },
    )


@safety_targets_router.post(
    "/safety-duty-assessments/import",
    response_model=ApiResponseEnvelope[SafetyDutyAssessmentImportResultResponse],
    summary="批量导入季度考核（按 年度+季度+部门+被考核人 覆盖更新）",
)
async def import_safety_duty_assessments(
    file: UploadFile,
    year: int = Query(ge=2000, le=2100, description="考核年度"),
    quarter: int = Query(ge=1, le=4, description="考核季度"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyDutyAssessmentImportResultResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    content = await file.read()
    sheets, skipped = parse_assessment_template(content)
    report = await DutyAssessmentImportService(db).commit(
        sheets,
        year=year,
        quarter=quarter,
        default_assessor="安全部",
        skipped_sheets=skipped,
        user_id=current_user.id,
    )
    await db.commit()
    return ApiResponseEnvelope(
        data=SafetyDutyAssessmentImportResultResponse(
            imported=report.imported,
            updated=report.updated,
            skipped_sheets=report.skipped_sheets,
            errors=report.errors,
        )
    )


@safety_targets_router.post(
    "/safety-duty-assessments",
    response_model=ApiResponseEnvelope[SafetyDutyAssessmentResponse],
    summary="新增责任制考核记录（含评分明细，总分与等级自动计算）",
)
async def create_safety_duty_assessment(
    data: SafetyDutyAssessmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyDutyAssessmentResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = SafetyDutyAssessmentService(db)
    assessment = await service.create_assessment(data, user_id=current_user.id)
    await db.commit()
    await db.refresh(assessment)
    return ApiResponseEnvelope(
        data=SafetyDutyAssessmentResponse.model_validate(assessment)
    )


@safety_targets_router.get(
    "/safety-duty-assessments/{assessment_id}",
    response_model=ApiResponseEnvelope[SafetyDutyAssessmentResponse],
    summary="责任制考核详情（含评分明细）",
)
async def get_safety_duty_assessment(
    assessment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyDutyAssessmentResponse]:
    service = SafetyDutyAssessmentService(db)
    assessment = await service.get_assessment(assessment_id)
    if assessment is None:
        raise NotFoundException("考核记录")
    return ApiResponseEnvelope(
        data=SafetyDutyAssessmentResponse.model_validate(assessment)
    )


@safety_targets_router.put(
    "/safety-duty-assessments/{assessment_id}",
    response_model=ApiResponseEnvelope[SafetyDutyAssessmentResponse],
    summary="更新责任制考核（items 提供时整体替换评分明细）",
)
async def update_safety_duty_assessment(
    assessment_id: UUID,
    data: SafetyDutyAssessmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyDutyAssessmentResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = SafetyDutyAssessmentService(db)
    assessment = await service.update_assessment(
        assessment_id, data, user_id=current_user.id
    )
    await db.commit()
    await db.refresh(assessment)
    return ApiResponseEnvelope(
        data=SafetyDutyAssessmentResponse.model_validate(assessment)
    )


@safety_targets_router.delete(
    "/safety-duty-assessments/{assessment_id}",
    response_model=ApiResponseEnvelope[None],
    summary="删除责任制考核记录（软删除）",
)
async def delete_safety_duty_assessment(
    assessment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[None]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = SafetyDutyAssessmentService(db)
    deleted = await service.delete_assessment(assessment_id)
    if not deleted:
        raise NotFoundException("考核记录")
    await db.commit()
    return ApiResponseEnvelope(data=None, message="删除成功")
