"""仪表盘图表警戒线配置 API。

GET  /production/chart-thresholds?scope_key=...  读取某页面范围的全部警戒线
PUT  /production/chart-thresholds                管理员更新一条（upsert）
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.modules.production.chart_threshold_models import ChartThreshold
from app.platform.identity.deps import CurrentUser

router = APIRouter()


@router.get("/chart-thresholds", summary="读取图表警戒线配置")
async def list_chart_thresholds(
    scope_key: str = Query(..., description="页面范围键"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="登录后才能读取"
        )
    rows = (
        (
            await db.execute(
                select(ChartThreshold).where(
                    ChartThreshold.scope_key == scope_key,
                    ChartThreshold.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    return success_response(
        data={row.chart_key: row.threshold for row in rows}
    )


class ChartThresholdUpsert(PydanticBaseModel):
    scope_key: str
    chart_key: str
    threshold: float


@router.put("/chart-thresholds", summary="更新图表警戒线（管理员）")
async def upsert_chart_threshold(
    payload: ChartThresholdUpsert,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="登录后才能操作"
        )
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅管理员可修改警戒线",
        )
    row = (
        (
            await db.execute(
                select(ChartThreshold).where(
                    ChartThreshold.scope_key == payload.scope_key,
                    ChartThreshold.chart_key == payload.chart_key,
                    ChartThreshold.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        row = ChartThreshold(
            scope_key=payload.scope_key, chart_key=payload.chart_key
        )
        db.add(row)
    row.threshold = payload.threshold
    row.updated_by = current_user.id
    await db.commit()
    return success_response(
        data={
            "scope_key": row.scope_key,
            "chart_key": row.chart_key,
            "threshold": row.threshold,
        }
    )
