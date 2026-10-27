"""Safety API — 应急处置卡端点。

车间/岗位级事故现场处置卡：种子数据来自各车间应急资料，支持按车间、
岗位、事故类型和关键字检索，以及基本维护（新增/编辑/软删除）。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.exceptions import AppException, NotFoundException
from app.modules.safety.schemas.emergency_cards import (
    EmergencyCardCreate,
    EmergencyCardListResponse,
    EmergencyCardResponse,
    EmergencyCardReviewResponse,
    EmergencyCardStatsResponse,
    EmergencyCardUpdate,
)
from app.modules.safety.service.emergency_card import EmergencyCardService
from app.modules.safety.service.emergency_card_ai import review_emergency_card
from app.shared.schemas import ApiResponseEnvelope

emergency_cards_router = APIRouter()


@emergency_cards_router.get(
    "/emergency-cards",
    response_model=ApiResponseEnvelope[EmergencyCardListResponse],
    summary="应急处置卡分页列表（车间/岗位/类型/关键字）",
)
async def list_emergency_cards(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    workshop: str | None = Query(None, description="车间/部门，如 103车间"),
    position: str | None = Query(None, description="岗位，如 配料"),
    accident_type: str | None = Query(None, description="事故类型，如 泄漏"),
    keyword: str | None = Query(None, description="标题/步骤/电话关键字"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencyCardListResponse]:
    service = EmergencyCardService(db)
    items, total = await service.list_cards(
        page=page,
        page_size=page_size,
        workshop=workshop,
        position=position,
        accident_type=accident_type,
        keyword=keyword,
    )
    return ApiResponseEnvelope(
        data=EmergencyCardListResponse(
            items=[EmergencyCardResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@emergency_cards_router.get(
    "/emergency-cards/stats",
    response_model=ApiResponseEnvelope[EmergencyCardStatsResponse],
    summary="应急处置卡概览（车间分布 + 事故类型）",
)
async def get_emergency_card_stats(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencyCardStatsResponse]:
    service = EmergencyCardService(db)
    return ApiResponseEnvelope(data=await service.get_stats())


@emergency_cards_router.post(
    "/emergency-cards/{card_id}/ai-review",
    response_model=ApiResponseEnvelope[EmergencyCardReviewResponse],
    summary="AI 审阅应急处置卡（完整性检查与完善建议，辅助分析）",
)
async def ai_review_emergency_card(
    card_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencyCardReviewResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = EmergencyCardService(db)
    card = await service.get_card(card_id)
    if card is None:
        raise NotFoundException("应急处置卡")
    return ApiResponseEnvelope(data=await review_emergency_card(card))


@emergency_cards_router.get(
    "/emergency-cards/{card_id}",
    response_model=ApiResponseEnvelope[EmergencyCardResponse],
    summary="应急处置卡详情",
)
async def get_emergency_card(
    card_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencyCardResponse]:
    service = EmergencyCardService(db)
    card = await service.get_card(card_id)
    if card is None:
        raise NotFoundException("应急处置卡")
    return ApiResponseEnvelope(data=EmergencyCardResponse.model_validate(card))


@emergency_cards_router.post(
    "/emergency-cards",
    response_model=ApiResponseEnvelope[EmergencyCardResponse],
    summary="新增应急处置卡",
)
async def create_emergency_card(
    data: EmergencyCardCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencyCardResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = EmergencyCardService(db)
    card = await service.create_card(data, user_id=current_user.id)
    await db.commit()
    await db.refresh(card)
    return ApiResponseEnvelope(data=EmergencyCardResponse.model_validate(card))


@emergency_cards_router.put(
    "/emergency-cards/{card_id}",
    response_model=ApiResponseEnvelope[EmergencyCardResponse],
    summary="更新应急处置卡",
)
async def update_emergency_card(
    card_id: UUID,
    data: EmergencyCardUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencyCardResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = EmergencyCardService(db)
    card = await service.update_card(card_id, data, user_id=current_user.id)
    await db.commit()
    await db.refresh(card)
    return ApiResponseEnvelope(data=EmergencyCardResponse.model_validate(card))


@emergency_cards_router.delete(
    "/emergency-cards/{card_id}",
    response_model=ApiResponseEnvelope[None],
    summary="删除应急处置卡（软删除）",
)
async def delete_emergency_card(
    card_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[None]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = EmergencyCardService(db)
    deleted = await service.delete_card(card_id)
    if not deleted:
        raise NotFoundException("应急处置卡")
    await db.commit()
    return ApiResponseEnvelope(data=None, message="删除成功")
