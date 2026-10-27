"""设备车间注册表 API（车间管理页与工作台车间数据源）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException
from app.core.response import success_response
from app.modules.equipment.schemas.workshop import (
    WorkshopCreateRequest,
    WorkshopUpdateRequest,
)
from app.modules.equipment.service import workshop as workshop_service

router = APIRouter()


def _require_user(current_user: CurrentUser) -> None:
    if current_user is None:
        raise AppException(message="需要登录才能执行此操作", status_code=401)


WORKSHOP_CODE_PATH = Path(
    ...,
    pattern=r"^[a-z0-9][a-z0-9-]{0,8}[a-z0-9]$",
    description="车间代码（如 101-1 / dlz）",
)


@router.get("", summary="启用车间清单（工作台与飞书配置页数据源）")
async def list_enabled_workshops(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    return success_response(data=await workshop_service.list_enabled(db))


@router.get("/all", summary="车间清单（含停用，车间管理页）")
async def list_all_workshops(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    return success_response(data=await workshop_service.list_all(db))


@router.post("", summary="新增车间")
async def create_workshop(
    data: WorkshopCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    return success_response(data=await workshop_service.create_workshop(db, data))


@router.put("/{code}", summary="更新车间（改名/启停；代码不可改）")
async def update_workshop(
    data: WorkshopUpdateRequest,
    code: str = WORKSHOP_CODE_PATH,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    return success_response(
        data=await workshop_service.update_workshop(db, code, data)
    )
