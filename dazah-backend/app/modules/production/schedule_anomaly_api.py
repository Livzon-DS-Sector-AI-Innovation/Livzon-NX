"""排产异常记录 API。

人工登记计划外异常（延后/减批/补种/染菌/其他）的列表与新增。
权限沿用排产计划页（production:plan:scheduling）：查询需 query，
新增需 operate；产品可见范围与排产页一致（scope_adapter=production.plan）。
"""
from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import quote

from fastapi import Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import paginated_response, success_response
from app.modules.production import schedule_anomaly_service
from app.modules.production.schedule_anomaly_service import AnomalyValidationError
from app.platform.identity.data_scope import (
    current_page_key,
    current_page_visible_sections,
)
from app.platform.identity.deps import CurrentUser
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["production"])


class ScheduleAnomalyBody(BaseModel):
    """排产异常记录写入体（空值/空白由服务层统一校验并转业务 400）。"""

    product_code: str = Field("FA", min_length=1, max_length=32)
    batch_no: str = Field(..., max_length=64, description="批号")
    tank_no: str | None = Field(None, max_length=64, description="罐号（选填）")
    anomaly_type: str = Field(..., min_length=1, max_length=24, description="异常类型")
    event_date: date = Field(..., description="异常发生日期")
    reason: str = Field(..., max_length=255, description="原因（必填）")
    remark: str | None = Field(None, max_length=255, description="备注（选填）")


def _require_visible_product(product_code: str) -> None:
    sections = current_page_visible_sections.get()
    if (
        current_page_key.get() == "production:plan:scheduling"
        and sections is not None
        and product_code not in sections
    ):
        raise HTTPException(403, "未获授权访问排产计划中的该产品")


@router.get("/schedule-anomalies", summary="排产异常记录列表")
async def list_schedule_anomalies(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    product: str = Query("FA", min_length=1, max_length=32, description="产品代码"),
    batch_no: str | None = Query(None, max_length=64, description="按批号筛选"),
    anomaly_type: str | None = Query(
        None, max_length=24, description="按异常类型筛选"
    ),
    date_from: date | None = Query(None, description="发生日期起（含）"),
    date_to: date | None = Query(None, description="发生日期止（含）"),
) -> Any:
    _require_visible_product(product)
    if anomaly_type and anomaly_type not in schedule_anomaly_service.ANOMALY_TYPES:
        raise HTTPException(status_code=400, detail="不支持的异常类型")
    items, total = await schedule_anomaly_service.list_anomalies(
        db,
        product_code=product,
        batch_no=batch_no,
        anomaly_type=anomaly_type,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return paginated_response(
        [
            schedule_anomaly_service.serialize_anomaly(record, created_by_name=name)
            for record, name in items
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/schedule-anomalies/export", summary="导出排产异常记录 Excel")
async def export_schedule_anomalies(
    db: AsyncSession = Depends(get_db),
    product: str = Query("FA", min_length=1, max_length=32, description="产品代码"),
    batch_no: str | None = Query(None, max_length=64, description="按批号筛选"),
    anomaly_type: str | None = Query(
        None, max_length=24, description="按异常类型筛选"
    ),
    date_from: date | None = Query(None, description="发生日期起（含）"),
    date_to: date | None = Query(None, description="发生日期止（含）"),
) -> Response:
    _require_visible_product(product)
    if anomaly_type and anomaly_type not in schedule_anomaly_service.ANOMALY_TYPES:
        raise HTTPException(status_code=400, detail="不支持的异常类型")
    rows = await schedule_anomaly_service.list_anomalies_for_export(
        db,
        product_code=product,
        batch_no=batch_no,
        anomaly_type=anomaly_type,
        date_from=date_from,
        date_to=date_to,
    )
    content = schedule_anomaly_service.build_anomalies_workbook(rows)
    filename = f"排产异常记录_{product}_{date.today().strftime('%Y%m%d')}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            # 中文文件名按 RFC 5987 编码，避免浏览器端乱码
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{quote(filename)}"
            )
        },
    )


@router.post("/schedule-anomalies", summary="登记排产异常")
async def create_schedule_anomaly(
    body: ScheduleAnomalyBody,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_visible_product(body.product_code)
    try:
        record = await schedule_anomaly_service.create_anomaly(
            db,
            product_code=body.product_code,
            batch_no=body.batch_no,
            anomaly_type=body.anomaly_type,
            event_date=body.event_date,
            reason=body.reason,
            tank_no=body.tank_no,
            remark=body.remark,
            created_by=current_user.id if current_user else None,
        )
    except AnomalyValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(record)
    return success_response(
        data=schedule_anomaly_service.serialize_anomaly(record),
        message="异常已登记",
    )
