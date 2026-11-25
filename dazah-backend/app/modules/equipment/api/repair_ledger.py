"""设备检修台账（飞书镜像）只读查询、同步与配置 API。"""

from __future__ import annotations

from datetime import UTC, date, datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException
from app.core.response import paginated_response, success_response
from app.modules.equipment.schemas.repair_ledger import (
    RepairConfigDetail,
    RepairConfigTestResult,
    RepairConfigUpdateRequest,
    RepairFilterOptions,
    RepairFrequencyItem,
    RepairRecordResponse,
    RepairSyncStateResponse,
)
from app.modules.equipment.service import repair_ledger as service

router = APIRouter()

# 车间代码形如 101 / 101-1 / dlz（小写字母/数字，可带 -序号）
WORKSHOP_QUERY = Query(
    ...,
    pattern=r"^[a-z0-9][a-z0-9-]{0,8}[a-z0-9]$",
    description="车间代码（如 101-1 / dlz）",
)
WORKSHOP_QUERY_OPTIONAL = Query(
    None,
    pattern=r"^[a-z0-9][a-z0-9-]{0,8}[a-z0-9]$",
    description="车间代码；缺省跨车间查询",
)


def _require_user(current_user: CurrentUser) -> None:
    if current_user is None:
        raise AppException(message="需要登录才能执行此操作", status_code=401)


@router.get("/records", summary="检修记录（飞书镜像）")
async def list_repair_records(
    workshop: str | None = WORKSHOP_QUERY_OPTIONAL,
    date_from: date | None = Query(None, description="维修日期起"),
    date_to: date | None = Query(None, description="维修日期止"),
    keyword: str | None = Query(None, description="设备/故障/人员搜索"),
    equipment: str | None = Query(None, description="设备名称原文（频次榜点入）"),
    person: str | None = Query(None, description="维修人员姓名（结构化或原文）"),
    fault: str | None = Query(None, description="故障描述（模糊匹配）"),
    result_status: str | None = Query(None, description="维修后状态原文"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    items, total = await service.list_records(
        db,
        workshop=workshop,
        date_from=date_from,
        date_to=date_to,
        keyword=keyword,
        equipment=equipment,
        person=person,
        fault=fault,
        result_status=result_status,
        page=page,
        page_size=page_size,
    )
    return paginated_response(
        data=[
            RepairRecordResponse.model_validate(item).model_dump(mode="json")
            for item in items
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/frequency", summary="设备维修频次排行")
async def repair_frequency(
    workshop: str | None = WORKSHOP_QUERY_OPTIONAL,
    date_from: date | None = Query(None, description="统计起点（维修日期）"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    items = await service.frequency(
        db, workshop=workshop, date_from=date_from, limit=limit
    )
    return success_response(
        data=[
            RepairFrequencyItem.model_validate(item).model_dump(mode="json")
            for item in items
        ]
    )


@router.get("/export", summary="导出检修记录 Excel（当前筛选的全部记录）")
async def export_repair_records(
    workshop: str | None = WORKSHOP_QUERY_OPTIONAL,
    date_from: date | None = Query(None, description="维修日期起"),
    date_to: date | None = Query(None, description="维修日期止"),
    keyword: str | None = Query(None, description="设备/故障/人员搜索"),
    equipment: str | None = Query(None, description="设备名称原文"),
    person: str | None = Query(None, description="维修人员姓名"),
    fault: str | None = Query(None, description="故障描述（模糊匹配）"),
    result_status: str | None = Query(None, description="维修后状态原文"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Response:
    _require_user(current_user)
    content, _rows = await service.export_records_xlsx(
        db,
        workshop=workshop,
        date_from=date_from,
        date_to=date_to,
        keyword=keyword,
        equipment=equipment,
        person=person,
        fault=fault,
        result_status=result_status,
    )
    filename = quote(
        f"设备检修_{workshop or '全部车间'}_{datetime.now(UTC):%Y%m%d}.xlsx"
    )
    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.get("/results", summary="维修后状态去重列表（筛选项）")
async def repair_distinct_results(
    workshop: str | None = WORKSHOP_QUERY_OPTIONAL,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    return success_response(data=await service.distinct_results(db, workshop))


@router.get("/filter-options", summary="筛选下拉选项（人员/故障/设备）")
async def repair_filter_options(
    workshop: str | None = WORKSHOP_QUERY_OPTIONAL,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    data = await service.filter_options(db, workshop)
    return success_response(
        data=RepairFilterOptions.model_validate(data).model_dump(mode="json")
    )


@router.get("/sync-status", summary="检修镜像同步状态")
async def repair_sync_status(
    workshop: str = WORKSHOP_QUERY,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    state = await service.get_sync_state(db, workshop)
    return success_response(
        data=RepairSyncStateResponse.model_validate(state).model_dump(mode="json")
    )


@router.post("/sync", summary="手动触发检修镜像同步")
async def trigger_repair_sync(
    workshop: str | None = WORKSHOP_QUERY_OPTIONAL,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    results = await service.sync_enabled(db, workshop)
    return success_response(data=results)


@router.get("/config", summary="获取检修飞书镜像配置")
async def get_repair_config(
    workshop: str = WORKSHOP_QUERY,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    detail = await service.get_config_detail(db, workshop)
    return success_response(
        data=RepairConfigDetail.model_validate(detail).model_dump(mode="json")
    )


@router.put("/config", summary="保存检修飞书镜像配置")
async def update_repair_config(
    payload: RepairConfigUpdateRequest,
    workshop: str = WORKSHOP_QUERY,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    detail = await service.update_config(db, workshop, payload)
    return success_response(
        data=RepairConfigDetail.model_validate(detail).model_dump(mode="json")
    )


@router.post("/config/test", summary="测试检修飞书镜像连接")
async def test_repair_config(
    workshop: str = WORKSHOP_QUERY,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await service.test_config(db, workshop)
    return success_response(
        data=RepairConfigTestResult.model_validate(result).model_dump(mode="json")
    )
