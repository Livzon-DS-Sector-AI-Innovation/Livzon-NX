"""设备健康档案与月度报告 API 路由."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException
from app.core.response import success_response
from app.modules.equipment.schemas import (
    HealthBoardResponse,
    HealthSnapshotResponse,
    HealthTrendResponse,
    MonthlyReportGenerateRequest,
    MonthlyReportResponse,
    RepairProfileResponse,
)
from app.modules.equipment.service import (
    generate_daily_snapshots,
    generate_monthly_report,
    get_health_board,
    get_health_trend,
    get_latest_health,
    get_monthly_report,
    get_repair_profile,
    list_monthly_reports,
    refresh_repair_profile,
)

router = APIRouter()


@router.get("/equipment/{equipment_id}", summary="设备健康档案（最新快照+趋势）")
async def get_equipment_health(
    equipment_id: uuid.UUID,
    days: int = Query(30, ge=7, le=180, description="趋势天数"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    latest = await get_latest_health(db, equipment_id)
    trend = await get_health_trend(db, equipment_id, days=days)
    return success_response(
        data=HealthTrendResponse(
            equipment_id=equipment_id,
            snapshots=[
                HealthSnapshotResponse.model_validate(s) for s in trend
            ],
        ).model_dump()
        | {
            "latest": (
                HealthSnapshotResponse.model_validate(latest).model_dump()
                if latest
                else None
            ),
        }
    )


@router.get("/board", summary="健康度榜单（按车间/分档筛选）")
async def get_board(
    workshop: str | None = Query(
        None,
        pattern=r"^[a-z0-9][a-z0-9-]{0,8}[a-z0-9]$",
        description="车间代码（如 101-1 / dlz）",
    ),
    grade: str | None = Query(None, pattern="^[GYR]$", description="分档 G/Y/R"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    items = await get_health_board(
        db, workshop_code=workshop, grade=grade
    )
    summary = {"total": len(items), "G": 0, "Y": 0, "R": 0}
    for item in items:
        summary[item["grade"]] = summary.get(item["grade"], 0) + 1
    return success_response(
        data=HealthBoardResponse(
            items=items, summary=summary
        ).model_dump()
    )


@router.get(
    "/repair-profile/{equipment_id}", summary="设备维修病历（聚合档案）"
)
async def get_profile(
    equipment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    profile = await get_repair_profile(db, equipment_id)
    return success_response(
        data=RepairProfileResponse.model_validate(profile).model_dump()
    )


@router.post(
    "/repair-profile/{equipment_id}/refresh",
    summary="手动刷新设备维修病历",
)
async def refresh_profile(
    equipment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    profile = await refresh_repair_profile(db, equipment_id)
    return success_response(
        data=RepairProfileResponse.model_validate(profile).model_dump()
    )


@router.post("/snapshots/run", summary="手动触发健康快照（管理调试用）")
async def run_snapshots(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    if current_user is None:
        raise AppException(message="需要登录后操作")
    stats = await generate_daily_snapshots(db)
    return success_response(data=stats)


# ── 月度报告 ────────────────────────────────────────────────────────


@router.get("/monthly-reports", summary="月度报告列表")
async def list_reports(
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    reports = await list_monthly_reports(db)
    return success_response(
        data=[
            MonthlyReportResponse.model_validate(r).model_dump()
            for r in reports
        ]
    )


@router.post(
    "/monthly-reports/generate", summary="生成/重新生成指定月份报告"
)
async def generate_report(
    data: MonthlyReportGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    if current_user is None:
        raise AppException(message="需要登录后操作")
    report = await generate_monthly_report(
        db, data.report_month, operator_id=current_user.id
    )
    return success_response(
        data=MonthlyReportResponse.model_validate(report).model_dump()
    )


@router.get("/monthly-reports/{report_month}", summary="查看指定月份报告")
async def get_report(
    report_month: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    report = await get_monthly_report(db, report_month)
    return success_response(
        data=MonthlyReportResponse.model_validate(report).model_dump()
    )
