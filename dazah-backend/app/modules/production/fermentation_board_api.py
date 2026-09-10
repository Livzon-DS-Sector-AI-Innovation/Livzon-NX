"""发酵车间生产实时看板 API（一期：计划驱动 + 检修标注）。

数据来源：最新排产 Excel 存档（当前扎帐周期块）推算罐状态/KPI/告警；
检修维护为人工标注，存储于 production.tank_maintenance。
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from datetime import time as datetime_time
from typing import Any

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.modules.production import fermentation_board_service as board
from app.platform.identity.deps import CurrentUser
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["production"])

# 排产表按北京时间排，容器默认 UTC，统一用北京时间比较
BEIJING_TZ = timezone(timedelta(hours=8))


class MaintenanceBody(BaseModel):
    tank_no: str = Field(..., min_length=1, max_length=32, description="罐号")
    reason: str = Field(..., min_length=1, max_length=255, description="检修原因")


class BatchActualBody(BaseModel):
    batch_no: str = Field(..., min_length=1, max_length=64, description="批次号")
    dump_date: date | None = Field(None, description="放罐日期")
    yield_kg: float | None = Field(None, ge=0, description="放罐产量(kg)")
    remark: str | None = Field(None, max_length=255, description="备注")


class MonthCapacityBody(BaseModel):
    planned_capacity_kg: float | None = Field(
        None, ge=0, description="本月计划产能(kg)"
    )


@router.get("/fermentation-board", summary="发酵车间实时看板（计划驱动，可按周期回看）")
async def get_fermentation_board(
    db: AsyncSession = Depends(get_db),
    date: date | None = Query(
        None, description="查看周期内任意日期（YYYY-MM-DD）；缺省为今天所在周期"
    ),
    product: str = Query("FA", description="产品代码（如 FA/MC/DR）"),
) -> Any:
    now = datetime.now(BEIJING_TZ).replace(tzinfo=None)
    ref_date = date or now.date()
    archive = await board.load_archive_covering(db, ref_date, product)
    if archive is None:
        return success_response(
            data=None,
            message=f"尚未上传覆盖 {ref_date.isoformat()} 所在扎帐周期的排产 Excel",
        )
    block = board.find_period_block(
        archive.rows, datetime.combine(ref_date, datetime_time(12, 0))
    )
    if block is None:
        return success_response(
            data=None,
            message=(
                f"排产表未覆盖 {ref_date.isoformat()}，"
                "请上传对应扎帐周期的排产 Excel"
            ),
        )
    is_current = block["start"] <= now.date() <= block["end"]
    # 统一按真实当前时间计算：历史月用"现在"回看（已过放罐窗口的批次即为已放罐），
    # 不把时间假装回到周期末
    as_of = now
    maintenance: list[dict[str, Any]] = []
    if is_current:
        maintenance = [
            board.serialize_maintenance(item)
            for item in await board.list_active_maintenance(db)
        ]
    actuals = await board.list_batch_actuals(
        db,
        period_start=block["start"],
        period_end=block["end"],
        product_code=product,
    )
    payload = board.build_board(
        archive.rows,
        maintenance,
        as_of,
        actuals=[board.serialize_batch_actual(item) for item in actuals],
        block=block,
    )
    if payload is None:
        return success_response(
            data=None,
            message="排产表未覆盖当前日期，请上传当前扎帐周期的排产 Excel",
        )
    payload["is_current_period"] = is_current
    setting = await board.get_month_setting(db, block["start"], product)
    payload["month_planned_capacity_kg"] = (
        setting.planned_capacity_kg if setting else None
    )
    return success_response(data=payload)


@router.get("/tank-maintenance", summary="发酵罐检修标注列表（进行中）")
async def list_tank_maintenance(
    db: AsyncSession = Depends(get_db),
) -> Any:
    items = await board.list_active_maintenance(db)
    return success_response(
        data=[board.serialize_maintenance(item) for item in items]
    )


@router.post("/tank-maintenance", summary="标记发酵罐检修（同罐进行中则更新）")
async def mark_tank_maintenance(
    body: MaintenanceBody,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    item = await board.upsert_maintenance(
        db,
        tank_no=body.tank_no,
        reason=body.reason,
        created_by=current_user.id if current_user else None,
    )
    return success_response(
        data=board.serialize_maintenance(item), message="已标记检修"
    )


@router.delete("/tank-maintenance/{item_id}", summary="解除发酵罐检修标注")
async def remove_tank_maintenance(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    item = await board.get_maintenance(db, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="检修标注不存在")
    await board.delete_maintenance(
        db, item, deleted_by=current_user.id if current_user else None
    )
    return success_response(data=None, message="已解除检修")


@router.get(
    "/fermentation-batch-actuals",
    summary="发酵批次实际产量列表（可按周期过滤）",
)
async def list_fermentation_batch_actuals(
    db: AsyncSession = Depends(get_db),
    period_start: date | None = Query(None, description="周期起始日（含）"),
    period_end: date | None = Query(None, description="周期结束日（含）"),
    product: str = Query("FA", description="产品代码（如 FA/MC/DR）"),
) -> Any:
    items = await board.list_batch_actuals(
        db,
        period_start=period_start,
        period_end=period_end,
        product_code=product,
    )
    archive = await board.load_latest_archive(db, product)
    tank_map = board.collect_dump_tanks(archive.rows) if archive else {}
    data = [
        {
            **board.serialize_batch_actual(item),
            "tank_no": tank_map.get(item.batch_no) or None,
        }
        for item in items
    ]
    return success_response(data=data)


@router.post(
    "/fermentation-batch-actuals", summary="录入发酵批次实际产量（同批次则更新）"
)
async def upsert_fermentation_batch_actual(
    body: BatchActualBody,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
    product: str = Query("FA", description="产品代码（如 FA/MC/DR）"),
) -> Any:
    item = await board.upsert_batch_actual(
        db,
        batch_no=body.batch_no.strip(),
        dump_date=body.dump_date,
        yield_kg=body.yield_kg,
        remark=body.remark,
        product_code=product,
        created_by=current_user.id if current_user else None,
    )
    return success_response(
        data=board.serialize_batch_actual(item), message="已保存批次产量"
    )


@router.delete("/fermentation-batch-actuals/{item_id}", summary="删除发酵批次实际产量")
async def remove_fermentation_batch_actual(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    item = await board.get_batch_actual(db, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="批次产量记录不存在")
    await board.delete_batch_actual(
        db, item, deleted_by=current_user.id if current_user else None
    )
    return success_response(data=None, message="已删除批次产量记录")


@router.post(
    "/fermentation-month-capacity", summary="设置当前扎帐月计划产能(kg)"
)
async def set_fermentation_month_capacity(
    body: MonthCapacityBody,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
    product: str = Query("FA", description="产品代码（如 FA/MC/DR）"),
) -> Any:
    archive = await board.load_latest_archive(db, product)
    if archive is None:
        raise HTTPException(
            status_code=400, detail="尚未上传排产 Excel，无法确定当前周期"
        )
    period = board.current_period(
        archive.rows, datetime.now(BEIJING_TZ).replace(tzinfo=None)
    )
    if period is None:
        raise HTTPException(
            status_code=400, detail="排产表未覆盖当前日期，无法确定当前周期"
        )
    item = await board.upsert_month_setting(
        db,
        period_start=period[0],
        period_end=period[1],
        planned_capacity_kg=body.planned_capacity_kg,
        product_code=product,
        updated_by=current_user.id if current_user else None,
    )
    return success_response(
        data=board.serialize_month_setting(item), message="已保存本月计划产能"
    )
