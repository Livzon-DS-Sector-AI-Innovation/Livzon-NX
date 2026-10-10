"""设备巡检飞书镜像只读查询与配置 API。"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException
from app.core.response import paginated_response, success_response
from app.modules.equipment.schemas.inspection import (
    EquipmentInspectionFeishuConfigUpdateRequest,
)
from app.modules.equipment.service import inspection_feishu_config as config_service
from app.modules.equipment.service import inspection_feishu_mirror as mirror

router = APIRouter()


def _require_user(current_user: CurrentUser) -> None:
    if current_user is None:
        raise AppException(message="需要登录才能执行此操作", status_code=401)


@router.get("/feishu/records", summary="巡检记录（飞书镜像）")
async def list_feishu_records(
    source: str | None = Query(
        None, description="来源：today=今日巡检 / history=历史记录，缺省全部"
    ),
    date_from: date | None = Query(None, description="日期起"),
    date_to: date | None = Query(None, description="日期止"),
    keyword: str | None = Query(None, description="设备名称/编号搜索"),
    abnormal_only: bool = Query(False, description="只看含异常（×）的记录"),
    process_status: str | None = Query(None, description="处理状态"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    if source is not None and source not in ("today", "history"):
        raise AppException(message="source 仅支持 today / history")
    items, total = await mirror.list_records(
        db,
        source=source,
        date_from=date_from,
        date_to=date_to,
        keyword=keyword,
        abnormal_only=abnormal_only,
        process_status=process_status,
        page=page,
        page_size=page_size,
    )
    return paginated_response(
        data=[
            {
                "id": str(item.id),
                "source": item.source,
                "record_id": item.record_id,
                "record_date": item.record_date,
                "equipment_name": item.equipment_name,
                "equipment_no": item.equipment_no,
                "am_clean": item.am_clean,
                "am_lubrication": item.am_lubrication,
                "am_fastening": item.am_fastening,
                "am_sealing": item.am_sealing,
                "am_vibration": item.am_vibration,
                "am_sound": item.am_sound,
                "am_surface": item.am_surface,
                "pm_clean": item.pm_clean,
                "pm_lubrication": item.pm_lubrication,
                "pm_fastening": item.pm_fastening,
                "pm_sealing": item.pm_sealing,
                "pm_vibration": item.pm_vibration,
                "pm_sound": item.pm_sound,
                "pm_surface": item.pm_surface,
                "anomaly_note": item.anomaly_note,
                "process_status": item.process_status,
                "has_abnormal": item.has_abnormal,
                "raw_fields": item.raw_fields,
                "last_modified_at": item.last_modified_at,
            }
            for item in items
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/feishu/devices", summary="巡检设备清单（飞书镜像 + 台账关联）")
async def list_feishu_devices(
    keyword: str | None = Query(None, description="设备名称/编号搜索"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    return success_response(data=await mirror.list_devices(db, keyword=keyword))


@router.get("/feishu/today-summary", summary="今日巡检进度")
async def feishu_today_summary(
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    return success_response(data=await mirror.today_summary(db))


@router.get("/feishu/sync-status", summary="镜像同步状态")
async def feishu_sync_status(
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    return success_response(
        data={
            "enabled": await config_service.is_mirror_enabled(db),
            "tables": await mirror.get_sync_states(db),
        }
    )


@router.post("/feishu/sync", summary="手动触发飞书同步")
async def feishu_sync_now(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    if not await config_service.is_mirror_enabled(db):
        raise AppException(message="巡检飞书镜像同步未配置（缺少应用凭据或表格 ID）")
    results = await mirror.sync_all(db, incremental=True)
    await db.commit()
    return success_response(data=results)


@router.get("/feishu/config", summary="获取设备巡检飞书镜像配置")
async def get_feishu_config(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    return success_response(data=await config_service.get_config_detail(db))


@router.put("/feishu/config", summary="保存设备巡检飞书镜像配置")
async def save_feishu_config(
    data: EquipmentInspectionFeishuConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    return success_response(data=await config_service.update_config(db, data))


@router.post("/feishu/config/test", summary="测试设备巡检飞书镜像连接")
async def test_feishu_config(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    return success_response(data=await config_service.test_config(db))
