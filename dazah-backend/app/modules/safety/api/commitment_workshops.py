"""Safety API — 安全承诺车间分填报：配置管理与当日填报状态。"""

from __future__ import annotations

from datetime import date as date_type
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.modules.safety.service.commitment_workshops import (
    fills_progress,
    list_configs,
    save_configs,
)
from app.modules.safety.service.safety_commitment import shanghai_today
from app.shared.schemas import ApiResponseEnvelope

commitment_workshops_router = APIRouter()


@commitment_workshops_router.get(
    "/safety-commitment-workshops",
    response_model=ApiResponseEnvelope[list[dict[str, Any]]],
    summary="车间填报配置列表（首次访问自动播种 12 车间）",
)
async def list_workshop_configs(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[list[dict[str, Any]]]:
    configs = await list_configs(db, ensure=True)
    payload = [
        {
            "id": str(cfg.id),
            "workshop_name": cfg.workshop_name,
            "reporter_open_id": cfg.reporter_open_id or "",
            "reporter_name": cfg.reporter_name or "",
            "sort_order": cfg.sort_order,
            "is_enabled": cfg.is_enabled,
        }
        for cfg in configs
    ]
    return ApiResponseEnvelope[list[dict[str, Any]]](data=payload)


@commitment_workshops_router.put(
    "/safety-commitment-workshops",
    response_model=ApiResponseEnvelope[list[dict[str, Any]]],
    summary="批量保存车间填报配置（名称/负责人/排序/启停，可增删）",
)
async def save_workshop_configs(
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[list[dict[str, Any]]]:
    items = payload.get("items") or []
    configs = await save_configs(db, items)
    result = [
        {
            "id": str(cfg.id),
            "workshop_name": cfg.workshop_name,
            "reporter_open_id": cfg.reporter_open_id or "",
            "reporter_name": cfg.reporter_name or "",
            "sort_order": cfg.sort_order,
            "is_enabled": cfg.is_enabled,
        }
        for cfg in configs
    ]
    return ApiResponseEnvelope[list[dict[str, Any]]](data=result)


@commitment_workshops_router.get(
    "/safety-commitment-workshops/fills",
    response_model=ApiResponseEnvelope[dict[str, Any]],
    summary="当日各车间填报状态与明细（汇总进度）",
)
async def get_workshop_fills(
    date: date_type | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[dict[str, Any]]:

    progress = await fills_progress(db, date or shanghai_today())
    return ApiResponseEnvelope[dict[str, Any]](data=progress)
