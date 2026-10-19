"""提炼工段 — 成品日报 API（提炼工段卡片右侧日报表）。

按日记录成品产量，与批次台账（方案 B）相互独立：
同产品同一天仅一条进行中记录，重复录入即覆盖更新。
读取与写入遵循生产概览页面授权、提炼工段范围和产品可见范围。
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.modules.production.extraction_report_models import ExtractionDailyReport
from app.modules.production.overview_visibility import require_overview_section
from app.platform.identity.data_scope import current_page_data_scope, current_page_key
from app.platform.identity.deps import CurrentUser
from app.platform.identity.public_api import has_current_page_permission
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["production"])


class DailyReportBody(BaseModel):
    report_date: date = Field(..., description="成品日期")
    quantity_kg: float = Field(..., ge=0, description="成品量(kg)")


async def _require_extract_permission(
    db: AsyncSession,
    current_user: CurrentUser,
    permission: Literal["query", "operate"],
    product: str,
) -> None:
    allowed = current_page_key.get() == "production:overview" and (
        await has_current_page_permission(
            db,
            current_user,
            module_code="production",
            permission=permission,
        )
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="未获授权访问生产概览成品日报")
    scope = current_page_data_scope.get()
    if not scope or scope.get("scope_type") not in {"all", "production_extraction"}:
        raise HTTPException(status_code=403, detail="未获授权访问提炼工段")
    require_overview_section(product)


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
    await _require_extract_permission(db, current_user, "query", product)
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


@router.post("/extraction-daily-reports", summary="录入提炼成品日报（同日覆盖更新）")
async def upsert_extraction_daily_report(
    body: DailyReportBody,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
    product: str = Query("FA", description="产品代码（如 FA/MC/DR）"),
) -> Any:
    await _require_extract_permission(db, current_user, "operate", product)
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
