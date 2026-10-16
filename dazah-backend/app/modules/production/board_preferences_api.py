"""生产看板用户偏好端点：平均单产口径与标签后缀按登录账户持久化。

GET 返回当前账户偏好（无记录时返回默认值）；POST 校验后 upsert。
首次登录默认：含中试口径 + 后缀「含中试」。
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel as PydanticModel
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.modules.production.board_preferences_models import (
    ProductionUserBoardPreference,
)
from app.platform.identity.deps import CurrentUser
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["production"])

DEFAULT_AVG_PILOT_INCL = True
DEFAULT_AVG_NOTE = "含中试"


class BoardPreferenceBody(PydanticModel):
    avg_pilot_incl: bool = Field(
        ...,
        description="平均单产口径：true=含中试（总产量÷大罐批数）",
    )
    avg_note: str = Field(
        "",
        max_length=64,
        description="含中试模式下的平均线标签后缀；空串=无后缀",
    )


async def _get_preference(
    db: AsyncSession, user_id: Any
) -> ProductionUserBoardPreference | None:
    result = await db.execute(
        select(ProductionUserBoardPreference).where(
            ProductionUserBoardPreference.user_id == user_id,
            ProductionUserBoardPreference.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


def _serialize(row: ProductionUserBoardPreference | None) -> dict[str, Any]:
    return {
        "avg_pilot_incl": (
            row.avg_pilot_incl if row is not None else DEFAULT_AVG_PILOT_INCL
        ),
        "avg_note": row.avg_note if row is not None else DEFAULT_AVG_NOTE,
    }


@router.get("/board-preferences", summary="生产看板个人偏好（平均单产口径与标签后缀）")
async def get_board_preferences(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    if current_user is None:
        raise HTTPException(status_code=401, detail="登录后才能查看看板偏好")
    row = await _get_preference(db, current_user.id)
    return success_response(data=_serialize(row))


@router.post("/board-preferences", summary="保存生产看板个人偏好")
async def save_board_preferences(
    body: BoardPreferenceBody,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    if current_user is None:
        raise HTTPException(status_code=401, detail="登录后才能保存看板偏好")
    note = body.avg_note.strip()
    row = await _get_preference(db, current_user.id)
    if row is None:
        row = ProductionUserBoardPreference(
            user_id=current_user.id,
            avg_pilot_incl=body.avg_pilot_incl,
            avg_note=note,
            created_by=current_user.id,
        )
        db.add(row)
    else:
        row.avg_pilot_incl = body.avg_pilot_incl
        row.avg_note = note
        row.updated_by = current_user.id
    await db.commit()
    await db.refresh(row)
    return success_response(data=_serialize(row), message="已保存看板偏好")
