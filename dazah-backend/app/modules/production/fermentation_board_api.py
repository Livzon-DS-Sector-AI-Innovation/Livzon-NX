"""发酵车间生产实时看板 API（一期：计划驱动 + 检修标注）。

数据来源：最新排产 Excel 存档（当前扎帐周期块）推算罐状态/KPI/告警；
检修维护为人工标注，存储于 production.tank_maintenance。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException
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


@router.get("/fermentation-board", summary="发酵车间实时看板（计划驱动）")
async def get_fermentation_board(
    db: AsyncSession = Depends(get_db),
) -> Any:
    archive = await board.load_latest_archive(db)
    if archive is None:
        return success_response(
            data=None, message="尚未上传排产 Excel，看板暂无数据"
        )
    maintenance = await board.list_active_maintenance(db)
    payload = board.build_board(
        archive.rows,
        [board.serialize_maintenance(item) for item in maintenance],
        datetime.now(BEIJING_TZ).replace(tzinfo=None),
    )
    if payload is None:
        return success_response(
            data=None,
            message="排产表未覆盖当前日期，请上传当前扎帐周期的排产 Excel",
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
