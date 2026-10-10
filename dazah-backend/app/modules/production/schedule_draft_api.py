"""FA 排产草稿生成 API（二期，无状态确定性重算）。

生成目标扎帐周期的排产草稿：结构化预览 + 一期校验报告，
或导出与现行排产表同构的单周期块 Excel。草稿不落库、不生效，
排产员修改后走排产计划页上传通道。
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.response import paginated_response, success_response
from app.modules.production import fermentation_board_service as board
from app.modules.production import schedule_draft_service as draft
from app.modules.production import schedule_validation_service as validation
from app.platform.identity.deps import CurrentUser
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["production"])

BEIJING_TZ = timezone(timedelta(hours=8))
# 排产校验/草稿当前仅支持 FA 产线
DRAFT_PRODUCT = "FA"


class TankBlockBody(BaseModel):
    tank_no: str = Field(..., min_length=1, max_length=32, description="罐号")
    from_date: date = Field(..., description="占用起始日（含）")
    to_date: date = Field(..., description="占用结束日（含）")


class ScheduleDraftBody(BaseModel):
    """草稿生成参数；周期缺省为今天之后的下一个扎帐周期。"""

    period_start: date | None = Field(None, description="周期起始日（27 日）")
    period_end: date | None = Field(None, description="周期结束日（26 日）")
    batch_start_no: int | None = Field(
        None, ge=1, le=999999, description="起始批号数字（缺省自动续号）"
    )
    skip_dates: list[date] = Field(
        default_factory=list, description="跳过进罐日（当日不移种，前一日不接种）"
    )
    tank_blocks: list[TankBlockBody] = Field(
        default_factory=list, description="罐占用窗口（检修/停用，不接新批）"
    )


def _resolve_params(
    body: ScheduleDraftBody, today: date
) -> draft.DraftParams:
    """解析并校验生成参数（周期对齐、窗口顺序、跳过日范围）。

    起始/截止日期各自对齐到所在扎帐周期的边界（27 日～次月 26 日），
    无需精确选择；对齐后跨度最多两个月，跨月时草稿按周期分块输出。
    """
    if body.period_start is None or body.period_end is None:
        if body.period_start is not None or body.period_end is not None:
            raise HTTPException(
                status_code=400, detail="周期起始日与结束日必须同时提供"
            )
        start, end = draft.next_accounting_period(today)
    else:
        start = board.unified_accounting_period(body.period_start)[0]
        end = board.unified_accounting_period(body.period_end)[1]
    if start > end:
        raise HTTPException(status_code=400, detail="周期起始日不能晚于结束日")
    if end - start > timedelta(days=62):
        raise HTTPException(status_code=400, detail="周期跨度不能超过两个月")
    skip_dates = {d for d in body.skip_dates if start <= d <= end}
    tank_blocks: list[draft.TankBlock] = []
    for block in body.tank_blocks:
        if block.tank_no not in board.FERMENT_TANKS:
            raise HTTPException(
                status_code=400,
                detail=f"罐占用窗口的罐号 {block.tank_no} 不在 FA 三罐之列",
            )
        if block.from_date > block.to_date:
            raise HTTPException(
                status_code=400,
                detail=f"罐 {block.tank_no} 的占用窗口起始晚于结束",
            )
        tank_blocks.append(
            draft.TankBlock(
                tank_no=block.tank_no,
                from_date=block.from_date,
                to_date=block.to_date,
            )
        )
    return draft.DraftParams(
        period_start=start,
        period_end=end,
        batch_start_no=body.batch_start_no,
        skip_dates=skip_dates,
        tank_blocks=tank_blocks,
    )


async def _compose_draft(
    db: AsyncSession, body: ScheduleDraftBody, now: datetime
) -> tuple[draft.DraftResult, dict[str, Any], draft.DraftParams]:
    """解析参数 → 加载存档与配置 → 生成草稿 → 一期校验（生成与导出共用）。"""
    params = _resolve_params(body, now.date())
    archive = await board.load_latest_archive(db, DRAFT_PRODUCT)
    if archive is None:
        raise HTTPException(
            status_code=400,
            detail="尚无 FA 排产存档，无法推导期初状态，请先上传排产 Excel",
        )
    setting = await validation.get_constraint_setting(db, DRAFT_PRODUCT)
    constraints = (
        validation.serialize_constraint_setting(setting)
        if setting
        else validation.empty_constraint_setting(DRAFT_PRODUCT)
    )
    maintenance = [
        board.serialize_maintenance(item)
        for item in await board.list_active_maintenance(db)
    ]
    # 进行中的检修标注自动转为默认占用窗口（与手工窗口叠加）：
    # 无预计恢复日期的按整期不排，摘要中可见，提示补填恢复日期
    for item in maintenance:
        if item["tank_no"] not in board.FERMENT_TANKS:
            continue
        started = board._parse_board_time(item.get("started_at"))
        if started is None:
            continue
        recovery = board._parse_board_date(item.get("expected_recovery_date"))
        block_from = max(started.date(), params.period_start)
        block_to = recovery or params.period_end
        if block_to >= block_from:
            params.tank_blocks.append(
                draft.TankBlock(
                    tank_no=item["tank_no"],
                    from_date=block_from,
                    to_date=block_to,
                )
            )
    result = draft.generate_draft(archive.rows, params, constraints=constraints)
    report = draft.validate_draft(
        result,
        archive.rows,
        constraints=constraints,
        maintenance=maintenance,
        now=now,
    )
    return result, report, params


@router.post(
    "/schedule-drafts/generate",
    summary="生成 FA 排产草稿（预览 + 一期校验报告，不落库）",
)
async def generate_schedule_draft(
    body: ScheduleDraftBody,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    now = datetime.now(BEIJING_TZ).replace(tzinfo=None)
    result, report, params = await _compose_draft(db, body, now)
    record = await draft.upsert_draft_record(
        db,
        product_code=DRAFT_PRODUCT,
        params=params,
        result=result,
        validation_report=report,
        operator_id=current_user.id if current_user else None,
    )
    warn_count = int(report.get("summary", {}).get("warn") or 0)
    return success_response(
        data={
            "record_id": str(record.id),
            "days": [
                {
                    "date": entry.date.isoformat(),
                    "seed_batch": entry.seed_batch,
                    "seed_tank": entry.seed_tank,
                    "seed_note": entry.seed_note,
                    "transfer": (
                        {"batch_no": entry.transfer[0], "tank_no": entry.transfer[1]}
                        if entry.transfer
                        else None
                    ),
                    "transfer_note": entry.transfer_note,
                    "dumps": [
                        {"batch_no": batch, "tank_no": tank}
                        for batch, tank in entry.dumps
                    ],
                    "dump_inflight": entry.dump_inflight,
                    "idle_tanks": entry.idle_tanks,
                }
                for entry in result.days
            ],
            "summary": result.summary,
            "validation": report,
        },
        message=(
            "草稿已生成，存在需人工确认的问题"
            if warn_count
            else "草稿已生成"
        ),
    )


@router.post(
    "/schedule-drafts/export",
    summary="导出 FA 排产草稿 Excel（单周期块，与现行排产表同构）",
)
async def export_schedule_draft(
    body: ScheduleDraftBody,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> StreamingResponse:
    now = datetime.now(BEIJING_TZ).replace(tzinfo=None)
    result, report, params = await _compose_draft(db, body, now)
    buffer: BytesIO = draft.build_draft_workbook(result)
    period = result.summary["period"]
    filename = f"FA排产草稿_{period['start']}_{period['end']}.xlsx"
    await draft.upsert_draft_record(
        db,
        product_code=DRAFT_PRODUCT,
        params=params,
        result=result,
        validation_report=report,
        workbook_bytes=buffer.getvalue(),
        file_name=filename,
        operator_id=current_user.id if current_user else None,
    )
    encoded = quote(filename, safe="")
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": f"attachment; filename*=utf-8''{encoded}",
        },
    )


@router.get(
    "/schedule-drafts/records",
    summary="排产草稿生成历史列表（工作台记录，不生效）",
)
async def list_schedule_draft_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> Any:
    items, total = await draft.list_draft_records(
        db, product_code=DRAFT_PRODUCT, page=page, page_size=page_size
    )
    return paginated_response(
        [
            draft.serialize_draft_record_summary(item, created_by_name=name)
            for item, name in items
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/schedule-drafts/records/{record_id}",
    summary="排产草稿历史详情（含逐日事件与校验快照）",
)
async def get_schedule_draft_record(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    item = await draft.get_draft_record(db, record_id)
    if item is None:
        raise HTTPException(status_code=404, detail="草稿记录不存在")
    name = await _record_user_name(db, item)
    return success_response(
        data=draft.serialize_draft_record_detail(item, created_by_name=name)
    )


@router.get(
    "/schedule-drafts/records/{record_id}/file",
    summary="下载草稿历史导出的 Excel 原件",
)
async def download_schedule_draft_record_file(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    item = await draft.get_draft_record(db, record_id)
    if item is None:
        raise HTTPException(status_code=404, detail="草稿记录不存在")
    if not item.original_path or not item.file_name:
        raise HTTPException(status_code=404, detail="该草稿未导出过文件")
    base = Path(get_settings().UPLOAD_DIR).resolve()
    path = (base / item.original_path).resolve()
    if base not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="草稿文件不存在")
    return FileResponse(
        path,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        filename=item.file_name,
    )


@router.delete(
    "/schedule-drafts/records/{record_id}",
    summary="删除草稿历史记录（软删，不影响已上传的排产存档）",
)
async def delete_schedule_draft_record(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    item = await draft.get_draft_record(db, record_id)
    if item is None:
        raise HTTPException(status_code=404, detail="草稿记录不存在")
    await draft.soft_delete_draft_record(
        db, item, deleted_by=current_user.id if current_user else None
    )
    return success_response(data=None, message="草稿记录已删除")


async def _record_user_name(db: AsyncSession, item: Any) -> str | None:
    from app.modules.production.schedule_excel_service import get_user_name

    if not item.created_by:
        return None
    return await get_user_name(db, item.created_by)
