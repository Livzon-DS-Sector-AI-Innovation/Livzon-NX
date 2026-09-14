"""提炼工段 — 成品日报 API（提炼工段卡片右侧日报表）。

按日记录成品产量，与批次台账（方案 B）相互独立：
同产品同一天仅一条进行中记录，重复录入即覆盖更新。
读取与写入均要求提炼产量权限（production:extraction-yield）。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.modules.production.extraction_report_models import ExtractionDailyReport
from app.modules.production.fermentation_board_api import EXTRACT_YIELD_PERMISSION
from app.platform.identity.deps import CurrentUser
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["production"])


class DailyReportBody(BaseModel):
    report_date: date = Field(..., description="成品日期")
    quantity_kg: float = Field(..., ge=0, description="成品量(kg)")


async def _require_extract_permission(
    db: AsyncSession, current_user: CurrentUser
) -> None:
    if current_user is None:
        raise HTTPException(status_code=403, detail="无提炼产量权限")
    from app.platform.identity.rbac import resolve_user_permissions

    perms = await resolve_user_permissions(db, current_user.id)
    if "*" in perms or EXTRACT_YIELD_PERMISSION in perms:
        return
    raise HTTPException(status_code=403, detail="无提炼产量权限")


def _serialize(item: ExtractionDailyReport) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "report_date": item.report_date.isoformat(),
        "quantity_kg": item.quantity_kg,
    }


@router.get(
    "/extraction-daily-reports",
    summary="提炼成品日报列表（可按日期区间过滤）",
)
async def list_extraction_daily_reports(
    db: AsyncSession = Depends(get_db),
    period_start: date | None = Query(None, description="起始日（含）"),
    period_end: date | None = Query(None, description="结束日（含）"),
    product: str = Query("FA", description="产品代码（如 FA/MC/DR）"),
    current_user: CurrentUser = None,
) -> Any:
    await _require_extract_permission(db, current_user)
    stmt = select(ExtractionDailyReport).where(
        ExtractionDailyReport.is_deleted.is_(False),
        ExtractionDailyReport.product_code == product,
    )
    if period_start is not None:
        stmt = stmt.where(ExtractionDailyReport.report_date >= period_start)
    if period_end is not None:
        stmt = stmt.where(ExtractionDailyReport.report_date <= period_end)
    stmt = stmt.order_by(ExtractionDailyReport.report_date.asc())
    items = list((await db.execute(stmt)).scalars().all())
    return success_response(data=[_serialize(item) for item in items])


@router.post(
    "/extraction-daily-reports", summary="录入提炼成品日报（同日覆盖更新）"
)
async def upsert_extraction_daily_report(
    body: DailyReportBody,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
    product: str = Query("FA", description="产品代码（如 FA/MC/DR）"),
) -> Any:
    await _require_extract_permission(db, current_user)
    result = await db.execute(
        select(ExtractionDailyReport).where(
            ExtractionDailyReport.report_date == body.report_date,
            ExtractionDailyReport.product_code == product,
            ExtractionDailyReport.is_deleted.is_(False),
        )
    )
    item = result.scalar_one_or_none()
    actor = current_user.id if current_user else None
    if item is None:
        item = ExtractionDailyReport(
            report_date=body.report_date,
            quantity_kg=body.quantity_kg,
            product_code=product,
            created_by=actor,
        )
        db.add(item)
    else:
        item.quantity_kg = body.quantity_kg
        item.updated_by = actor
    await db.commit()
    await db.refresh(item)
    return success_response(data=_serialize(item), message="已保存成品日报")
