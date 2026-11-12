"""Safety API — 安全承诺日报与信息卡端点（应急〔2018〕74号 承诺公告制度）。"""

from __future__ import annotations

from datetime import date as date_type
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.exceptions import NotFoundException
from app.modules.safety.models import SafetyCommitmentReport
from app.modules.safety.schemas.safety_commitment import (
    RiskAssessmentResponse,
    SafetyCommitmentCardCreateRequest,
    SafetyCommitmentCardItem,
    SafetyCommitmentCardListResponse,
    SafetyCommitmentCardUpdateRequest,
    SafetyCommitmentPublishRequest,
    SafetyCommitmentReportItem,
    SafetyCommitmentReportResponse,
    SafetyCommitmentUpdateRequest,
)
from app.modules.safety.service import safety_commitment as commitment_service
from app.modules.safety.service import safety_commitment_risk
from app.shared.schemas import ApiResponseEnvelope

safety_commitments_router = APIRouter()


def _current_user_id(current_user: CurrentUser) -> UUID | None:
    return getattr(current_user, "id", None)


@safety_commitments_router.get(
    "/safety-commitments/today",
    response_model=ApiResponseEnvelope[SafetyCommitmentReportResponse],
    summary="取当日安全承诺日报（不存在则惰性初始化并自动 AI 研判）",
)
async def get_today_commitment(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyCommitmentReportResponse]:
    # 日报按北京时间自然日划分（容器为 UTC 时区，不能用 date.today()）
    report, created = await commitment_service.get_or_create_report(
        db,
        commitment_service.shanghai_today(),
        user_id=_current_user_id(current_user),
    )
    payload = SafetyCommitmentReportResponse(
        report=SafetyCommitmentReportItem(
            **commitment_service._to_item(report)
        ),
        created_today=created,
    )
    return ApiResponseEnvelope[SafetyCommitmentReportResponse](data=payload)


@safety_commitments_router.get(
    "/safety-commitments/list",
    response_model=ApiResponseEnvelope[list[SafetyCommitmentReportItem]],
    summary="安全承诺日报历史列表",
)
async def list_commitments(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[list[SafetyCommitmentReportItem]]:
    items = await commitment_service.list_reports(db, limit=limit, offset=offset)
    payload = [SafetyCommitmentReportItem(**item) for item in items]
    return ApiResponseEnvelope[list[SafetyCommitmentReportItem]](data=payload)


@safety_commitments_router.get(
    "/safety-commitments/by-date/{report_date}",
    response_model=ApiResponseEnvelope[SafetyCommitmentReportItem],
    summary="按日期查看安全承诺日报（只读，不初始化）",
)
async def get_commitment_by_date(
    report_date: date_type,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyCommitmentReportItem]:
    item = await commitment_service.get_report_by_date(db, report_date)
    return ApiResponseEnvelope[SafetyCommitmentReportItem](
        data=SafetyCommitmentReportItem(**item)
    )


@safety_commitments_router.put(
    "/safety-commitments/{report_id}",
    response_model=ApiResponseEnvelope[SafetyCommitmentReportItem],
    summary="编辑企业状态 / 企业安全承诺正文",
)
async def update_commitment(
    report_id: UUID,
    data: SafetyCommitmentUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyCommitmentReportItem]:
    item = await commitment_service.update_report(
        db, report_id, data, user_id=_current_user_id(current_user)
    )
    return ApiResponseEnvelope[SafetyCommitmentReportItem](
        data=SafetyCommitmentReportItem(**item)
    )


@safety_commitments_router.post(
    "/safety-commitments/{report_id}/publish",
    response_model=ApiResponseEnvelope[SafetyCommitmentReportItem],
    summary="发布当日承诺公告（主要负责人名义）",
)
async def publish_commitment(
    report_id: UUID,
    data: SafetyCommitmentPublishRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyCommitmentReportItem]:
    item = await commitment_service.publish_report(
        db,
        report_id,
        data.publisher_name,
        user_id=_current_user_id(current_user),
    )
    return ApiResponseEnvelope[SafetyCommitmentReportItem](
        data=SafetyCommitmentReportItem(**item)
    )


@safety_commitments_router.post(
    "/safety-commitments/{report_id}/risk-assessment",
    response_model=ApiResponseEnvelope[RiskAssessmentResponse],
    summary="（重新）生成当日 AI 风险研判",
)
async def regenerate_risk_assessment(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[RiskAssessmentResponse]:
    report = await db.get(SafetyCommitmentReport, report_id)
    if report is None or report.is_deleted:
        raise NotFoundException("安全承诺日报")
    updated, reason = await safety_commitment_risk.generate_risk_assessment(
        db, report
    )
    if updated is None:
        payload = RiskAssessmentResponse(success=False, message=reason or "")
        return ApiResponseEnvelope[RiskAssessmentResponse](data=payload)
    await db.commit()
    # updated_at 为服务端 onupdate 表达式，UPDATE 后属性过期；异步会话
    # 不能懒加载，序列化前显式刷新
    await db.refresh(report)
    payload = RiskAssessmentResponse(
        success=True,
        report=SafetyCommitmentReportItem(
            **commitment_service._to_item(report)
        ),
    )
    return ApiResponseEnvelope[RiskAssessmentResponse](data=payload)


# ==================== 滚动信息卡 ====================


@safety_commitments_router.get(
    "/safety-commitment-cards",
    response_model=ApiResponseEnvelope[SafetyCommitmentCardListResponse],
    summary="滚动信息卡列表（安全承诺信息 / 重大危险源信息）",
)
async def list_commitment_cards(
    card_type: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyCommitmentCardListResponse]:
    cards = await commitment_service.list_cards(db, card_type=card_type)
    payload = SafetyCommitmentCardListResponse(
        cards=[
            SafetyCommitmentCardItem(**commitment_service._card_to_item(card))
            for card in cards
        ]
    )
    return ApiResponseEnvelope[SafetyCommitmentCardListResponse](data=payload)


@safety_commitments_router.post(
    "/safety-commitment-cards",
    response_model=ApiResponseEnvelope[SafetyCommitmentCardItem],
    summary="新增滚动信息卡",
)
async def create_commitment_card(
    data: SafetyCommitmentCardCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyCommitmentCardItem]:
    item = await commitment_service.create_card(
        db, data, user_id=_current_user_id(current_user)
    )
    return ApiResponseEnvelope[SafetyCommitmentCardItem](
        data=SafetyCommitmentCardItem(**item)
    )


@safety_commitments_router.put(
    "/safety-commitment-cards/{card_id}",
    response_model=ApiResponseEnvelope[SafetyCommitmentCardItem],
    summary="编辑滚动信息卡",
)
async def update_commitment_card(
    card_id: UUID,
    data: SafetyCommitmentCardUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyCommitmentCardItem]:
    item = await commitment_service.update_card(db, card_id, data)
    return ApiResponseEnvelope[SafetyCommitmentCardItem](
        data=SafetyCommitmentCardItem(**item)
    )


@safety_commitments_router.delete(
    "/safety-commitment-cards/{card_id}",
    response_model=ApiResponseEnvelope[None],
    summary="删除滚动信息卡（软删除）",
)
async def delete_commitment_card(
    card_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[None]:
    await commitment_service.delete_card(db, card_id)
    return ApiResponseEnvelope[None](data=None)
