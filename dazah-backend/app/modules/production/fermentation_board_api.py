"""发酵车间生产实时看板 API（一期：计划驱动 + 检修标注）。

数据来源：最新排产 Excel 存档（当前扎帐周期块）推算罐状态/KPI/告警；
检修维护为人工标注，存储于 production.tank_maintenance。
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from datetime import time as datetime_time
from functools import partial
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
    extract_kg: float | None = Field(None, ge=0, description="提炼成品产量(kg)")
    remark: str | None = Field(None, max_length=255, description="备注")


FERM_YIELD_PERMISSION = "production:fermentation-yield"
EXTRACT_YIELD_PERMISSION = "production:extraction-yield"
# 发酵产量组字段：放罐产量及发酵侧台账信息，整体挂发酵权限
_FERM_FIELDS = frozenset({"dump_date", "yield_kg", "remark"})


async def _stage_permissions(
    db: AsyncSession, current_user: CurrentUser
) -> tuple[bool, bool]:
    """解析当前用户的工段产量权限：(发酵可见, 提炼可见)。"""
    if current_user is None:
        return (False, False)
    from app.platform.identity.rbac import resolve_user_permissions

    perms = await resolve_user_permissions(db, current_user.id)
    if "*" in perms:
        return (True, True)
    return (
        FERM_YIELD_PERMISSION in perms,
        EXTRACT_YIELD_PERMISSION in perms,
    )


def _filter_actual_payload(
    item: dict[str, Any], has_ferm: bool, has_extract: bool
) -> dict[str, Any]:
    """按工段权限过滤批次产量字段：无权字段不出接口。"""
    if not has_ferm:
        item.pop("yield_kg", None)
    if not has_extract:
        item.pop("extract_kg", None)
    return item


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
    product: str = Query("FA", description="产品代码（如 FA/MC/DR/LV/MV）"),
    current_user: CurrentUser = None,
) -> Any:
    has_ferm, has_extract = await _stage_permissions(db, current_user)
    now = datetime.now(BEIJING_TZ).replace(tzinfo=None)
    ref_date = date or now.date()
    archive = await board.load_archive_covering(db, ref_date, product)
    if archive is None:
        return success_response(
            data=None,
            message=f"尚未上传覆盖 {ref_date.isoformat()} 所在扎帐周期的排产 Excel",
        )
    # FA / DR / MP(及他汀 LV/MV，复用 MP 管线+103自然月块解析) 排产表
    # 格式不同：块定位与看板组装按产品分派
    if product == "DR":
        find_block = board.find_dr_period_block
        build_board_fn = board.build_dr_board
    elif product in ("MC", "LV", "MV"):
        find_block = partial(board.find_mp_period_block, product=product)
        build_board_fn = partial(board.build_mp_board, product=product)
    else:
        find_block = board.find_period_block
        build_board_fn = board.build_board
    block = find_block(
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
    payload = build_board_fn(
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
    # 「提炼已出成品（仓储成品入库）」：当期仓储成品入库合计（KG），
    # 跟随所选扎帐周期；仅提炼权限返回，仓储侧异常已在 service 内降级为 None
    payload["extract_finished_inbound_kg"] = (
        await board.get_warehouse_finished_inbound_kg(
            db,
            product_code=product,
            period_start=block["start"],
            period_end=block["end"],
        )
        if has_extract
        else None
    )
    # 「提炼已出成品」以成品日报为唯一数据源：合计/天数/实时收率按日报覆盖
    if has_extract:
        daily_quantities = await board.sum_extraction_daily_reports(
            db, block["start"], block["end"], product
        )
        payload["extraction"] = board.apply_daily_extract_source(
            payload.get("extraction"), daily_quantities
        )
    # 工段数据权限：发酵侧模块（KPI/罐状态/产量图表/最近完成）挂发酵权限，
    # 提炼汇总挂提炼权限，收率需双权限（有任一权限缺失时字段不出接口）
    if not has_extract:
        payload["extraction"] = None
        payload["extraction_ledger"] = None
        for item in payload.get("recent") or []:
            item.pop("extract_kg", None)
            item.pop("batch_yield_rate", None)
    if not has_ferm:
        payload["kpis"] = None
        payload["tanks"] = []
        payload["recent"] = []
        payload["trend"] = None
        payload["maintenance"] = []
        payload["month_planned_capacity_kg"] = None
        # 提炼台账仍返回（提炼岗需要），但剥离发酵侧放罐产量
        for row in payload.get("extraction_ledger") or []:
            row.pop("yield_kg", None)
    return success_response(data=payload)


@router.get(
    "/production-summary",
    summary="生产汇总（五产线发酵/提炼关键指标）",
)
async def get_production_summary(
    db: AsyncSession = Depends(get_db),
    date: date | None = Query(
        None, description="参考日期 YYYY-MM-DD，默认今天（按扎帐周期取数）"
    ),
    current_user: CurrentUser = None,
) -> Any:
    has_ferm, has_extract = await _stage_permissions(db, current_user)
    now = datetime.now(BEIJING_TZ).replace(tzinfo=None)
    payload = await board.build_production_summary(
        db,
        ref_date=date or now.date(),
        has_ferm=has_ferm,
        has_extract=has_extract,
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
    product: str = Query("FA", description="产品代码（如 FA/MC/DR/LV/MV）"),
    current_user: CurrentUser = None,
) -> Any:
    has_ferm, has_extract = await _stage_permissions(db, current_user)
    items = await board.list_batch_actuals(
        db,
        period_start=period_start,
        period_end=period_end,
        product_code=product,
    )
    archive = await board.load_latest_archive(db, product)
    tank_map = (
        board.collect_dump_tanks(archive.rows, product) if archive else {}
    )
    data = [
        _filter_actual_payload(
            {
                **board.serialize_batch_actual(item),
                "tank_no": tank_map.get(item.batch_no) or None,
            },
            has_ferm,
            has_extract,
        )
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
    product: str = Query("FA", description="产品代码（如 FA/MC/DR/LV/MV）"),
) -> Any:
    # 字段级工段权限：发酵字段组挂发酵权限，提炼成品挂提炼权限；
    # 仅请求中显式给出的字段参与更新，防止跨工段覆盖对方已录数据
    has_ferm, has_extract = await _stage_permissions(db, current_user)
    provided = set(body.model_fields_set) - {"batch_no", "product_code"}
    if provided & _FERM_FIELDS and not has_ferm:
        raise HTTPException(
            status_code=403, detail="无发酵产量权限，不能修改放罐产量信息"
        )
    if "extract_kg" in provided and not has_extract:
        raise HTTPException(
            status_code=403, detail="无提炼产量权限，不能修改提炼成品产量"
        )
    if not provided & (_FERM_FIELDS | {"extract_kg"}):
        raise HTTPException(status_code=400, detail="没有可保存的产量字段")
    item = await board.upsert_batch_actual(
        db,
        batch_no=body.batch_no.strip(),
        dump_date=body.dump_date,
        yield_kg=body.yield_kg,
        extract_kg=body.extract_kg,
        remark=body.remark,
        product_code=product,
        created_by=current_user.id if current_user else None,
        provided_fields=provided,
    )
    return success_response(
        data=_filter_actual_payload(
            board.serialize_batch_actual(item), has_ferm, has_extract
        ),
        message="已保存批次产量",
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
    product: str = Query("FA", description="产品代码（如 FA/MC/DR/LV/MV）"),
) -> Any:
    archive = await board.load_latest_archive(db, product)
    if archive is None:
        raise HTTPException(
            status_code=400, detail="尚未上传排产 Excel，无法确定当前周期"
        )
    period = board.current_period(
        archive.rows,
        datetime.now(BEIJING_TZ).replace(tzinfo=None),
        product,
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
